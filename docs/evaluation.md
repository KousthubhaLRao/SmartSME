# How accurate the extraction actually is

Measured numbers, not impressions. The test suite proves the code does what it
was written to do; it cannot say whether reading "Anita ko 5 kilo chawal becha"
produces the *right* sale. This page is that second question.

[&larr; Back to the README](../README.md) &nbsp;·&nbsp;
Harness, data format and how to run it: [backend/eval](../backend/eval/README.md)

---

## Method in one paragraph

Every input has a **gold label** — the correct answer, written down by a person
before any system saw it. The harness runs each input through the same functions
the application uses, compares the result to its label, and counts. Per-field
precision, recall and F1; plus **exact**, the share of inputs where every field
was right, which is the share a shopkeeper could accept without editing
anything. A wrong answer costs twice — once as a miss, once as a fabrication —
because a wrong customer is worse than no customer.

Last run: 2026-09-16. Regenerate with `python -m eval` from `backend`.

## Typed notes (n = 70)

| Engine | Exact | type F1 | party F1 | items F1 | amount F1 | category F1 |
|---|---:|---:|---:|---:|---:|---:|
| Heuristic (offline regex) | 85.7% | 100.0 | 94.8 | 91.9 | 95.2 | 100.0 |
| Gemini 3.5 Flash Lite | **97.1%** | 100.0 | **100.0** | **98.4** | **100.0** | 100.0 |

By language variant, exact-match:

| Variant | n | Heuristic | Gemini |
|---|---:|---:|---:|
| English | 18 | 66.7% | **94.4%** |
| Hindi, Latin letters | 18 | 77.8% | **94.4%** |
| Hindi, Devanagari | 11 | 100.0% | 100.0% |
| Kannada, Latin letters | 12 | 100.0% | 100.0% |
| Kannada script | 11 | 100.0% | 100.0% |

**What this says.** The offline parser is competitive on well-formed notes and
falls behind on messy ones — no verb, no capitals, typos, two items on a line —
which is where English and Hinglish lose their points. Both native scripts score
at or near 100% for both engines, because [`app/ai/lang.py`](../backend/app/ai/lang.py)
normalises the sentence before either engine sees it; that work is shared, so it
does not distinguish them.

**What this does not say.** These notes are **synthetic** — written by the same
author as the parser. The first fifty scored 100% on the heuristic, which says
more about who wrote them than about the parser; twenty deliberately messier
ones brought it to 85.7%. Numbers from author-written data cannot tell you how
the system behaves for a stranger.

## Handwritten order slips (n = 12, real photographs)

| Engine | Exact | party F1 | phone F1 | items F1 |
|---|---:|---:|---:|---:|
| Vision model (Gemini) | **100.0%** | 100.0 | 100.0 | 100.0 |
| OCR.space (character OCR) | 75.0% | 100.0 | 100.0 | 91.7 |

Split by whether the customer corrected something on the paper:

| Engine | Clean slips | Slips with an in-place correction |
|---|---:|---:|
| Vision model | 9 / 9 | **3 / 3** |
| OCR.space | 9 / 9 | **0 / 3** |

**This is the finding.** Both engines read the handwriting accurately — party
and phone are perfect for both, and character OCR gets every clean slip. The
entire difference is the three slips where something was struck out and
rewritten:

```
Meena      1 kg  C̶o̶f̶f̶e̶e̶  /  1 kg Coffee    read literally: 2 kg billed for 1
S. Khan    5 bags  W̶h̶e̶a̶t̶  Atta            read literally: product "Wheat Atta"
A. Sharma  4 bags  P̶r̶o̶d̶u̶c̶t̶ ̶B̶              read literally: a cancelled item ordered
```

A strikethrough is not a character, so it cannot survive character recognition.
No post-processing recovers information that never entered the text — the
failure is structural, not a tuning problem. A vision model can be *told* to
ignore cancelled text, and on all three it is.

Three of twelve slips in an **unplanned** sample carried a correction, so this
is not an edge case; correcting an order in place is just how people write on
paper. It is also the reason the vision path is tried first and the free OCR
path is labelled by name on the confirm screen — so whoever reviews a draft
knows a cancelled line could be sitting in it.

## Consistency: does the same note give the same draft?

An LLM is sampled, so identical input can produce different output. That matters
more here than in a chat: the same order typed twice must not become two
different sales.

Measured on five notes, three runs each:

| | Same draft every run |
|---|---|
| Before, at the model's default temperature | **3 / 5** |
| After pinning `temperature: 0` | **5 / 5** |

The two that varied failed in ways a shopkeeper would have noticed:

```
ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ    party was sometimes "ಅನಿತಾಗೆ" - the name with its
                                Kannada case-ending still attached, which then
                                matched no customer at all
anita stores 5 rice 2 sugar    items were sometimes [Rice Bag 25kg x5] and
                                sometimes [Item x1] - the whole order lost
```

Extraction is not writing: there is no value in sampling. Accuracy was unchanged
at 97.1% after the switch, so determinism here was free.

## Latency

| Path | Median | Notes |
|---|---|---|
| Text note → draft (Gemini) | **2.2 s** | end to end, including the catalogue match |
| Photograph → draft (Gemini vision) | **1.4 s** | 12 real slips |
| Photograph → draft (OCR.space) | **1.9 s** | includes re-encoding the image |

The p90 for text notes reads 16.8 s, but that is the *harness* rather than the
model: it retries with backoff when the free tier refuses, and those waits are
inside the measurement. A single uncontended call is ~1-2 s.

## Four bugs the evaluation found that 364 passing tests did not

1. **The expense category vocabulary was not pinned.** The regex path answered
   "Electricity", the model answered "Utilities", and the Expenses page grouped
   them as two different things. Fixed by
   [`app/ai/categories.py`](../backend/app/ai/categories.py). Worth 7 points of
   exact-match on its own: 90.0% → 97.1%.
2. **A tab between a label and its value ate the phone number.** Splitting on
   every tab was right for two items merged onto one row and wrong for
   `Ph no:⇥9443311220`.
3. **A name and a phone merged onto one line** were read as one very long
   customer name.
4. **A bug in the harness itself** — `300` and `300.0` compared unequal as text,
   so a correct extraction was reported as a failure.

The harness also caught itself being misled: on the first real run, **38 of 70
examples silently fell back to the heuristic** because the free tier stops at
about sixteen calls a minute, and every AI path here degrades rather than fails.
Without that check, the regex parser's score would have been published under
Gemini's name. Runs now report how many examples a different engine produced,
and a row with that warning is not a measurement.

## What is still missing

- **Real users.** The slips are real photographs but come from one writer, in
  good light, in neat block capitals. The notes are author-written. Neither is
  evidence about shopkeepers.
- **A second annotator.** Every gold label here was written once, by one person.
  Serious work has two people label independently and reports how often they
  agreed.
- **Latency under concurrency.** The figures above are single calls on an idle
  machine. Nobody has measured what happens when twenty shopkeepers submit a
  note in the same minute - and the binding constraint there is not this app but
  the free tier's ~15 requests a minute.
