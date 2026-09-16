# Every model and AI service this project uses

The short answer: **two hosted APIs, neither required, and no machine learning
model runs anywhere in this codebase.** Nothing is trained here,
nothing is downloaded at runtime, nothing comes from HuggingFace, and there is
no PyTorch, TensorFlow, scikit-learn, spaCy or NLTK in the dependency list.

[&larr; Back to the README](../README.md)

---

## The hosted models

Two services, both free, both optional. With neither configured the app still
runs — text input falls back to a built-in parser and photo reading is
unavailable.

| Where | Service | Default model | Cost |
|---|---|---|---|
| Text notes, and reading photos | **Google Gemini** | `gemini-3.5-flash-lite` | free tier, no card |
| Reading photos, as a fallback | **OCR.space** | OCR Engine **2** | free, 25,000 pages/month |

That is the whole list. The AI layer used to accept Anthropic, any
OpenAI-compatible endpoint, and Groq as well; none was ever configured, and
carrying them meant four sets of settings, four code paths, and four pinned
model names to go stale — two were silently returning 404 before anyone looked.
They were removed rather than left as dead options.

Both model names are configurable — `GEMINI_MODEL`, `OCR_SPACE_ENGINE` —
because pinned names do go stale, and when that happens every call returns 404
at once.

### What they are asked to do

Two prompts, both in this repo, both asking for strict JSON:

- **`app/ai/nlp.py`** — turn one note into `{eventType, party, product, quantity,
  amount, category, allInventory, discountType, discountValue, date}`.
- **`app/ai/ocr.py`** — turn one photograph into `{party, phone, docType,
  lineItems[], total, date, discount}`, and **ignore anything crossed out**.

Nothing is sent except the note or the image the user just supplied. No
customer list, no catalogue, no history — the matching against a shop's own data
happens locally, after the model has answered.

## Everything else is not a model

This is the part worth being precise about, because "AI-assisted" invites the
assumption that a model is behind each of these. None of them is.

| Component | What it actually is |
|---|---|
| `app/ai/lang.py` — Hindi/Kannada normalisation | Hand-written regex and a vocabulary table. Moves postpositions, converts native digits, resolves कल by tense. |
| `app/ai/translit.py` — cross-script name matching | `indic-transliteration`, a deterministic character-mapping library. Devanagari/Kannada → Latin by table lookup. Pure Python, no download. |
| `app/ai/lexicon.py` — product translation | A dictionary, about 90 entries. चावल → rice is a lookup, not an inference. |
| `app/ai/slip.py` — order slip structure | Regex over the lines of OCR text. |
| `app/smart_input.py` — matching to the catalogue | String algorithms: normalisation, whole-word runs, consonant skeletons, phone-number comparison. No embeddings, no vector search, no similarity model. |
| `app/ai/nlp.py` — `heuristic_parse` | Regex. This is what runs when no API key is set. |
| `app/analytics.py`, `app/reports.py` | SQL aggregation. No forecasting, no anomaly detection, no clustering. |
| `app/workflow.py` — the rule engine | WHEN/THEN rules a user writes by hand. |
| Low-stock and alert rules | Threshold comparisons. |
| `app/ai/ocr_space.py` — image preparation | Pillow: rotate, grayscale, contrast, resize. Image processing, not vision. |

**Why it matters that these are not models.** A dictionary and a regex are
auditable, run offline in microseconds, cost nothing, never hallucinate, and
behave identically every run. That last property is why the evaluation can
compare engines at all. Machine translation was considered for the product
vocabulary and rejected: it needs a network round trip or a few hundred
megabytes of model, it is *worse* on the words that matter here — brand names,
local produce names, trade words like "bori" — and its output would still have
to be matched against the shop's own catalogue afterwards, which is the step
that does the real work.

## How well they do

Measured, not asserted — see [Accuracy evaluation](evaluation.md):

| Task | Engine | Result |
|---|---|---|
| Typed notes (n=70) | Gemini 3.5 Flash Lite | 97.1% exact |
| Typed notes (n=70) | the regex fallback, no model | 85.7% exact |
| Handwritten slips (n=12) | Gemini (vision) | 100% exact |
| Handwritten slips (n=12) | OCR.space | 75.0% exact |

The one place the choice genuinely matters: on the three slips where a customer
crossed something out and rewrote it, the vision model got **3/3** and the
character recogniser got **0/3**. A strikethrough is not a character, so it
cannot survive character recognition.

## Data handling, in one line each

- Notes and images go to whichever provider is configured, over HTTPS, one
  request each. Nothing is batched, stored remotely, or used for training by
  this application.
- Retention and training policy is the provider's, not ours — check the terms of
  whichever key you set, especially for a free tier.
- With **no key configured**, nothing leaves the machine: the regex parser and
  the dictionaries handle text entirely offline.
- The tests never call a provider. `conftest.py` clears every key, including
  `OCR_SPACE_API_KEY`, so the suite is free, offline and deterministic.
