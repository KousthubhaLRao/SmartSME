# Measuring how accurate the extraction actually is

The test suite proves the code does what it was written to do. It cannot tell
you whether reading "Anita ko 5 kilo chawal becha" produces the right sale,
because "right" is a judgement about meaning and no assertion can hold it. That
is what this is for.

Nothing here runs under `pytest`. It makes real network calls, it is
nondeterministic, and free tiers are rate-limited - none of which belongs in a
suite that has to finish in ten seconds on every save.

## What a gold label is

A **gold label** is the correct answer for one input, written down by a person
before any system sees it.

```
input:  "sold 5 kg rice to Anita Stores"
gold:   { type: sale, party: "Anita Stores",
          items: [ { product: "Rice Bag 25kg", quantity: 5 } ] }
```

Scoring is then just comparing what came out against that, and counting.
Everything in the report is a count of agreements and disagreements.

Two things follow, and both matter:

- **Gold labels cannot be generated.** They are the definition of correct. If a
  model writes them, you are grading the model against itself, which measures
  nothing at all.
- **Gold is a judgement, so it can be wrong.** That is why serious work has two
  people label the same data independently and reports how often they agreed.
  This set has been labelled once, by one person. Say so in any write-up.

## Running it

```powershell
cd backend
.venv\Scripts\python -m eval                                  # everything configured
.venv\Scripts\python -m eval --engines heuristic,google       # pick engines
.venv\Scripts\python -m eval --slips-only --engines vision,ocrspace
.venv\Scripts\python -m eval --limit 10 --delay 0             # fast smoke run
```

`--delay` is the pause between provider calls. **Do not set it to zero for a
real run.** Measured on Gemini's free tier: at one second, sixteen calls went
through and everything else that minute was refused - and because every AI path
in this codebase degrades to the heuristic parser rather than failing, those
refusals came back as *results*. Half the run was silently the regex parser
wearing Gemini's name. 3.2 seconds keeps it inside the allowance.

The harness now detects that on its own and prints how many examples were
produced by a different engine than the one being measured. **If that line
appears, the row is not a measurement.**

Output lands in `results/`: a markdown table, and a JSON file with every
individual prediction. Read the JSON when a number looks wrong - it is usually
the labels or the scorer, not the parser.

## What the numbers mean

- **P / R / F1** per field. A wrong answer counts twice: once as a miss, once
  as a fabrication. That is deliberate - a wrong customer is worse than no
  customer, because an empty dropdown gets filled in and a wrong one gets
  approved.
- **Exact** is the share of inputs where every scored field was right, so it is
  the share a shopkeeper could accept without editing anything. It is the
  number that matters; field F1 can look healthy while nearly every draft still
  needs one correction.

## The data, and how far to trust it

| Set | What it is | Standing |
|---|---|---|
| `data/slips.jsonl` | 12 photographs of real handwritten order slips | Real inputs. Labels transcribed once, by one person. |
| `data/notes.jsonl` | 70 typed notes across five language variants | **Synthetic** - written by the same author as the parser. |
| `data/catalogue.json` | The shop everything is scored against | Fixed, so runs are comparable. |

The synthetic set is honest about being the weak half. The first fifty notes
scored **100% on the heuristic parser**, which says more about who wrote them
than about the parser; twenty messier ones were added afterwards and the score
dropped to 85.7%. Even so, notes written by the person who wrote the parser
cannot measure how the system behaves for a stranger.

**Before any of this is published**, that set needs replacing with notes
collected from actual shopkeepers, labelled by two people, with the agreement
between them reported.

## Results, as of the last run

`results/notes.md` and `results/slips.md` hold the generated tables. The
headline numbers:

### Typed notes (n=70, synthetic - see the caveat above)

| Engine | Exact | party F1 | items F1 |
|---|---:|---:|---:|
| heuristic (offline regex) | 85.7% | 94.8 | 91.9 |
| Gemini 3.5 Flash Lite | **97.1%** | 100.0 | 98.4 |

The gap is concentrated exactly where you would expect: on the messier
English and Hinglish notes (no verb, no capitals, typos, two items in a line)
the offline parser drops to 66.7% and 77.8% while the model holds 94.4%. On
the two native scripts both are at or near 100%, because the normaliser in
`app/ai/lang.py` does that work before either engine sees the text.

### Handwritten order slips (n=12, real photographs)

| Engine | Exact | Clean slips | Slips corrected in place |
|---|---:|---:|---:|
| Vision model (Gemini) | **100%** | 9/9 | **3/3** |
| OCR.space (character OCR) | 75.0% | 9/9 | **0/3** |

This is the result worth writing up. Both engines read the handwriting
accurately - party and phone are 100% for both, and OCR.space gets every clean
slip. The entire difference is the three slips where the customer crossed
something out and wrote a correction:

```
Meena     1 kg  C̶o̶f̶f̶e̶e̶  /  1 kg Coffee     character OCR reads 2 kg, she ordered 1
S. Khan   5 bags  W̶h̶e̶a̶t̶  Atta             reads the product as "Wheat Atta"
A. Sharma 4 bags  P̶r̶o̶d̶u̶c̶t̶ ̶B̶               reads a cancelled item as ordered
```

A strikethrough is not a character, so it cannot survive character recognition;
no amount of post-processing recovers information that never reached the text.
A vision model can be told to ignore cancelled text, and on all three it does.
3 of 12 slips in an *unplanned* sample carried a correction, so this is not an
edge case.

## Things the evaluation found that 364 passing tests did not

1. **The category vocabulary was not pinned.** The regex path answered
   "Electricity", the model answered "Utilities", and the Expenses page grouped
   them as two different things. Fixed in `app/ai/categories.py` - the model now
   picks from a fixed list and whatever it answers is mapped onto it. Worth
   **7 points** of Gemini's exact-match score on its own (90.0% -> 97.1%).
2. **A tab between a label and its value ate the phone number.** Splitting on
   every tab was right for two items merged onto one row and wrong for
   `Ph no:<TAB>9443311220`, which cost two slips their phone.
3. **A name and phone merged onto one line** were read as a very long customer
   name.
4. **A bug in the harness itself.** The amount `300` and the amount `300.0`
   compared unequal as text, so a correct extraction was reported as a failure.
   An evaluation with a bug in it is worse than none, because somebody goes
   looking for the fault in the parser.

## What these numbers are not

- **Not evidence about real users.** The notes are author-written; the slips are
  real but all from one writer, in good light, in neat block capitals.
- **Not a language claim.** Both native scripts score ~100% partly because the
  test sentences follow the grammar the normaliser was built for.
- **Not a latency claim.** The harness records per-call seconds, but paced runs
  and a free tier's queueing make those numbers meaningless as a benchmark.
