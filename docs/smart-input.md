# Smart Input: reading notes and photographs

The NLP engine, three scripts, catalogue matching, and the two OCR engines.

[&larr; Back to the README](../README.md)

---

## Smart Input Engine (NLP + OCR)

`app/ai/client.py` is one provider behind one `complete(prompt, system, image)`
call: **Google Gemini**, chosen because its free tier needs no card and the same
key reads a typed note and a photographed slip. `get_provider()` returns it when
`GOOGLE_API_KEY` is set and `None` otherwise, which is what makes every caller
degrade cleanly instead of failing.

It used to accept Anthropic, any OpenAI-compatible endpoint, and Groq as well.
None was ever configured, and carrying them cost four sets of settings, four
code paths and four pinned model names to go stale — two of which were silently
returning 404 before anyone checked. Swapping providers later is a contained
change: one `complete()` implementation and the settings behind it.

A provider that is failing is dropped rather than retried: after three
consecutive failures it is skipped outright for two minutes and callers fall
straight through to the heuristic parser. At a sixty-second timeout each, a
queue of twenty-five mailed orders would otherwise take twenty-five minutes to
fail one at a time.

### Languages

A note can arrive in English, Hindi or Kannada, in Devanagari or Kannada script
or typed in Latin letters, and often mixes them in one sentence:

| | |
|---|---|
| English | `sold 5 kg rice to Anita Stores` |
| Hinglish | `5 kilo chawal Anita ko becha` |
| Hindi | `अनीता को 5 किलो चावल बेचा` |
| Kannada | `ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ` |
| Kanglish | `Anita ge 5 kilo akki maride` |

With an AI key the model handles the language directly, and the prompt tells it
which ones to expect. Without one, `app/ai/lang.py` rewrites the note into the
English shape the built-in parser already understands, so the fallback speaks
every language too:

```
"ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ"  ->  "to ಅನಿತಾ 5 kg ಅಕ್ಕಿ sold"
```

Two things it does beyond swapping words:

- **Native digits become numbers.** ೫ and ५ are 5; a quantity is useless
  otherwise.
- **Word order is repaired.** Hindi and Kannada mark the recipient *after* the
  name — "Anita ko", "ಅನಿತಾಗೆ" — where English puts a preposition before it.
  Kannada glues it on as a suffix, which is why the vocabulary is applied first:
  ಬಾಡಿಗೆ means "rent" and happens to end in ಗೆ ("to"), and splitting it would
  invent a customer called ಬಾಡಿ.

**A name and a product are left in the script they arrived in.** Rewriting
them would be lossy and pointless: the work of connecting them to the shop's own
catalogue happens at the matching step instead, which reads all three scripts.
See [Matching across scripts](#matching-across-scripts) below.

Hindi कल is both yesterday and tomorrow. A note about something already done
resolves to yesterday; one about something a customer wants resolves to
tomorrow.

### Matching across scripts

A note says चावल. The shop's product list says `Rice Bag 25kg`. Nothing about
those two strings is alike, and until they are connected the confirm screen
shows "Custom item" at a price of zero, which is worth nothing to anybody.

Two different problems are tangled together there, and conflating them is why
this took two attempts:

| | Problem | Solution | Module |
|---|---|---|---|
| **Goods** | चावल *means* rice. A different word, not a different spelling. | A retail vocabulary, looked up | `app/ai/lexicon.py` |
| **Names** | अनीता *is* Anita. There is no dictionary entry for a person. | Transliteration | `app/ai/translit.py` |

On top of both sits a third: romanised Indian words have no fixed spelling.
chawal, chaval and chaawal are one word typed by three people, and Anita and
Anitha are one person choosing between two spellings of her own name. So every
comparison happens on a **folded key** that discards what writers disagree about
- diacritics, doubled letters, aspirates (`th`/`t`), long vowels (`ee`/`i`),
`w`/`v`, and Devanagari's inherent trailing "a":

```
chawal, chaval, chaawal, चावल   ->  caval        (then: concept "rice")
Anita, Anitha, अनीता, ಅನಿತಾ     ->  anit
```

`best_match` then goes from certain to merely likely, in five passes:

1. the same name, exactly
2. the same words, once script and spelling are folded away
3. the same **thing**, by meaning - चावल / chawal / ಅಕ್ಕಿ all reach the concept
   `rice`, and so does the `Rice` in `Rice Bag 25kg`
4. the same words in a different order
5. the same consonants - and only when exactly one row has them

The last pass exists because transliteration cannot recover a vowel the original
script never wrote: स्टोर्स comes back as "storsa" against a catalogue that says
"Stores". `strs` and `strs` are the same. It is lossy enough to be wrong, so it
answers only when there is a single candidate and otherwise declines - a wrong
customer on an invoice is worse than an empty dropdown.

**The lexicon is meant to be extended.** A row is `"english": (variants...)`, in
any script and any spelling, and folding absorbs the rest, so one form per
language is usually enough:

```python
LEXICON = {
    "rice": ("चावल", "ಅಕ್ಕಿ", "chawal", "chaval", "akki"),
    ...
}
```

It ships with about eighty kirana and household lines. A shop selling something
not in it still works - that item is picked from the dropdown once, by hand.

**Why a dictionary and not machine translation.** Translation was the obvious
reach and the wrong tool. It needs a network round trip per note or a few
hundred megabytes of model; it is *worse* at exactly the words that matter here,
which are brand names, local produce names and trade words like "bori"; and its
output would still have to be matched against the shop's catalogue afterwards -
which is the step that actually does the work. The dictionary is offline,
instant, auditable, and correct on the vocabulary a shop uses every day.

### Text (`app/ai/nlp.py`)
1. One prompt asks the model for strict JSON: `eventType`, `party`,
   `lineItems[]`, `amount`, `category`, `allInventory`, `discountType`,
   `discountValue`, `date`.
2. `extract_json()` pulls the first `{…}` out of the reply and `_normalize()`
   validates every field.
3. **With no key, or if the call fails**, it falls back to `heuristic_parse()`, a
   dependency-free regex parser covering the same fields.

Understood today, among others:

| You type | It extracts |
|---|---|
| `Sold 10 rice bags to Kumar Traders` | sale, qty 10, product Rice, party Kumar Traders |
| `Purchase 50 sugar packets from ABC Suppliers` | purchase (party type corrects the direction) |
| `Paid electricity bill 3200` | expense, category Utilities |
| `Sell everything to Anita Stores at a discount of 10%` | one line per in-stock product, 10% discount |
| `Sold 4 litres cooking oil to Shree on 20th August 2026` | date `2026-08-20` |
| `20 tea packets, 40 rice bags and 10 sugar packets from Sunrise Wholesale` | **three** priced lines, purchase |

### More than one item in a note

`lineItems` is a list because notes are lists. It used to be a single `product`,
so a note naming three things silently became one - the model and the regex
parser both, since the shape gave neither anywhere to put the rest.

The regex parser splits on **quantities, not on the word "and"**, and that is
what makes it safe:

```
2 kg salt and pepper     one quantity  -> one item, "Salt and Pepper"
5 rice 2 sugar           two          -> two items
```

Splitting on conjunctions would get both of those backwards. Line breaks and
commas work too, so a slip typed as a list reads as one.

Dates accept `20th August 2026`, `20 aug`, `3 sept`, `August 20 2026`,
`20/08/2026`, `2026-08-20`, `today`, `yesterday`, `day before yesterday`. With no
date stated it defaults to today. Impossible dates (31 Feb) are rejected, and a
bare day+month rolls back a year rather than landing in the future.

### Images — two engines (`app/ai/ocr.py`, `app/ai/ocr_space.py`)

A photographed order slip is read by whichever engine is configured, and both
options are free:

| | Engine | Reads handwriting | Sees a crossed-out line | Cost |
|---|---|---|---|---|
| 1st choice | **Vision model** (`GOOGLE_API_KEY`) | yes | **yes** | free tier, no card |
| fallback | **OCR.space** (`OCR_SPACE_API_KEY`) | yes | **no** | free, 25k pages/month |

Both return the same `ParsedInvoice` — `party`, `phone`, `docType`,
`lineItems`, `total`, `date`, `discount` — so everything downstream is shared.

**The strikethrough is the whole reason for the ordering**, and it is not
hypothetical. Of twelve real slips in `backend/tests/fixtures`, three have an
item corrected in place:

```
Meena     1 kg  C̶o̶f̶f̶e̶e̶  /  1 kg Coffee     read literally: 2 kg billed for 1
S. Khan   5 bags  W̶h̶e̶a̶t̶  Atta             read literally: product "Wheat Atta"
A. Sharma 4 bags  P̶r̶o̶d̶u̶c̶t̶ ̶B̶               read literally: a cancelled item ordered
```

OCR.space reads every one of those slips *accurately* — its text is nearly
perfect, names and numbers included. It simply cannot represent a strikethrough,
because that is not a character. The vision model can be told to ignore
cancelled text, and on all three slips it does.

So when only OCR.space is configured the draft is labelled `OCR.space` on the
confirm screen, as a signal to read the lines before accepting. Nothing is ever
written without that confirmation.

`app/ai/slip.py` turns OCR text back into items, correcting two things measured
on these same photographs: a handwritten **1 read as a capital I**, and **two
short rows merged with a tab**.

Try it against the fixtures:

```powershell
cd backend
.venv\Scripts\python -m app.cli ocr-test                  # all 12 slips
.venv\Scripts\python -m app.cli ocr-test --prepare-only   # no API call
```

### Grounding (`app/smart_input.py`)
Both paths then run the same matching step:

- **Phone matching first** (images only) — an order slip carries a phone
  number, and it is the only exact key on it. `party_by_phone()` compares the
  last ten digits, so `+91 98800 11223` and `098800-11223` are one customer.
  This matters more than it sounds: a slip signed "Latha" belongs to a shop
  filed as "Lathamma Provisions", which no name matching would ever find.
- **Party matching** — `best_match()` then tries exact, whole-word, by meaning,
  and by consonants, across all three scripts. See
  [Matching across scripts](#matching-across-scripts).
- **Direction correction** — a matched party's own type is authoritative, so a
  named customer forces `sale` even if the model guessed `purchase`.
- **Product matching** against the catalogue, falling back to a custom line.
- **"Entire inventory"** expands to one line per in-stock product.

Nothing is written until you confirm.

---

