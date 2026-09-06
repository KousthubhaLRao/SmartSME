# SmartSME → Research Paper: Transformation Roadmap

*A plan for turning the SmartSME codebase into a peer-reviewed conference/journal paper — without changing the existing code — plus proposed new components that raise the research depth and divide across a four-person team.*

---

## 0. The honest starting point (read this first)

SmartSME today is a **competent, non-trivial engineering artifact**: an event-driven ERP for small businesses with an LLM "Business Input Engine," a Postgres transactional-outbox event bus, a workflow rule engine, and business-health analytics. As *software*, it is well above a typical student project.

As a *research paper*, that is not yet enough for a peer-reviewed venue, and it is important to be blunt about why. A reviewer's first question is never "did they build something that works?" — it is **"what do we learn from this that generalizes beyond your one system?"** A paper whose contribution reduces to "we wrapped an ERP with an LLM" gets desk-rejected on novelty, because both ERPs and LLM extraction are known. The system is the *vehicle*; the *contribution* has to be a defensible claim backed by evidence.

There are three ways to clear that bar, and this roadmap uses all three:

1. **Sharpen the research question** so it is about a real, under-studied problem (data-entry as the adoption barrier for informal/semi-formal micro-enterprises), not about the software.
2. **Evaluate empirically** against that question — accuracy benchmarks, a user study, and systems measurements — most of which can be run against the *existing, unchanged* code.
3. **Add two or three genuinely novel components** (entity grounding, code-mixed multilingual input, confidence-aware selective confirmation, forecasting/advisor) that each carry their own sub-contribution and their own evaluation, and that map cleanly onto four people.

The rest of this document is the plan to do exactly that.

---

## 1. The research framing

### 1.1 The problem worth writing about

Micro and small enterprises — the corner shop, the neighbourhood distributor, the single-owner trader — are the backbone of emerging-market economies, yet they overwhelmingly **do not adopt digital bookkeeping or ERP tools**. The dominant reason in the literature is not cost or hardware; it is the **friction of structured data entry**. These businesses run on WhatsApp messages, handwritten slips, verbal transactions, code-mixed language ("Kumar ko 10 rice bags beche"), non-standard product names, and inconsistent units. Traditional ERP forms demand exactly the structure these users don't have time to produce.

**That gap is the paper.** SmartSME's Business Input Engine is a concrete answer to it: it accepts the messy, natural inputs these users already produce (free-text notes, invoice photos, WhatsApp screenshots) and turns them into validated, structured, human-confirmed business events. The event-driven backbone is the mechanism that keeps the resulting data consistent.

### 1.2 The central research questions

Frame the paper around three questions (the chosen contributions were *LLM Business Input Engine* + *whole-system case study*):

- **RQ1 (Accuracy).** How accurately can an LLM-based multimodal input engine convert informal, real-world SME inputs (text, invoices, screenshots; monolingual and code-mixed) into correct structured business events, and how does this vary by input modality, language, provider/model, and a no-LLM heuristic baseline?
- **RQ2 (Human effort & trust).** Does natural-language / image input meaningfully reduce data-entry time and error versus traditional forms for SME users, and does the human-in-the-loop confirmation step reliably catch the errors the model makes without becoming a rubber-stamp?
- **RQ3 (System reliability).** Can a Postgres transactional-outbox event bus (rather than a dedicated message broker) provide the consistency, retry, replay, and idempotency guarantees an SME workload needs, and what are its performance envelope and failure behaviours?

RQ1 and RQ3 can be answered against the **existing code, unchanged**. RQ2 needs participants but no code change. The new components in §4 extend RQ1/RQ2.

### 1.3 The contribution statement (what you claim)

State three contributions explicitly in the intro:

1. **An architecture and open system** for near-zero-friction, multimodal, human-in-the-loop data entry aimed at the informal SME sector, including a design that replaces a message broker with a transactional-outbox event bus.
2. **An empirical evaluation** on a purpose-built benchmark of realistic SME inputs, including a **multi-model comparison** (the provider-agnostic layer lets you evaluate Anthropic / OpenAI / Groq / Gemini and a heuristic baseline on identical data) and a **user study** with real or representative shopkeepers.
3. **A characterization and taxonomy of failure modes** for LLM-based business-event extraction in this setting, with design implications (why confirmation matters, where grounding is needed, where code-mixing breaks things).

That third contribution — the *taxonomy* — is disproportionately valuable: reviewers reward papers that teach the community *where the approach breaks and why*, and it costs only careful analysis of data you already have to collect.

### 1.4 Candidate venues (realistic, tiered)

- **Most realistic / strong fit:** IEEE **COMPSAC**, IEEE **ICSME** (tools/industry track), **ESEM** (empirical SE), ACM/IEEE **ICTD** or journals on **Information Technology for Development** / **Electronic Commerce Research** (the ICT4D + digital-entrepreneurship angle is a genuine strength here). Applied-AI venues: **EMNLP Industry Track**, **NAACL Industry**, or workshops on document AI / information extraction.
- **Stretch:** ACM **CHI** / **CSCW** (only if the user study is strong and the framing is squarely HCI), **FSE/ICSE** SEIP (software engineering in practice) tracks.
- **Journal route (good for a 4-person student team):** IEEE **Access**, Springer **SN Computer Science**, Elsevier journals in information systems / expert systems — these accept solid system-plus-evaluation papers and have predictable review cycles.

Pick the venue *before* writing; it sets the length, the evaluation bar, and how much of the paper is systems vs. HCI vs. NLP.

---

## 2. Mapping what you already have to paper sections

You do not need new code to write most of the paper. Here is the existing material and where it lands.

| Existing artifact in the repo | Paper use |
|---|---|
| `lib/ai/nlp.ts` — structured event extraction from shopkeeper notes, with a dependency-free **heuristic fallback** | The core method (RQ1) **and a ready-made baseline** — the heuristic parser is your no-LLM ablation for free |
| `lib/ai/client.ts` — provider-agnostic layer (Anthropic / OpenAI / Groq / Gemini) | Enables the **multi-model comparison table** with no code change — just swap env vars |
| `lib/ai/ocr.ts` — invoice / screenshot → line items via vision | The multimodal (image) arm of RQ1 |
| Confirmation screen (input console) — human approval before publish | The human-in-the-loop mechanism for RQ2; instrument it to log proposed-vs-confirmed diffs |
| `lib/workflow/engine.ts` — transactional, idempotent, replay-guarded rule engine; chained events in one transaction | The consistency story for RQ3 (atomic effects, retry-safety) |
| `worker/loop.ts` + `events` table + `FOR UPDATE SKIP LOCKED`, retry, dead-letter, replay | The outbox event-bus contribution and RQ3 systems evaluation |
| `lib/analytics.ts` — KPI + business-health scoring | Supporting "so what" — what the structured data enables downstream |
| The two design docs (`README.md`, `SmartSME_Developer_Spec_v2.md`) | Raw material for the Architecture and Design-Rationale sections, incl. the *why-not-RabbitMQ* argument, which is a real design-rationale contribution |

**Instrumentation caveat (no logic change):** RQ2 needs the confirmation screen to record, per input, the AI-proposed event and the user-confirmed event. If the code doesn't already persist that diff, capturing it counts as *adding logging/telemetry*, not changing behaviour — you can also capture it out-of-band during the study (screen recording, a wrapper harness) to honour the "don't change the code" constraint strictly. Decide this deliberately.

---

## 3. The evaluation plan (most of it needs no code change)

This is the heart of the transformation. Four studies; run them against the current system.

### 3.1 Study A — Input-Engine accuracy benchmark (answers RQ1)

**Build a labeled dataset** — this is the single most important artifact you will produce, and it can itself be a released contribution.

- **Text commands:** 300–600 shopkeeper utterances covering sales, purchases, orders, expenses; include the messy realities — missing prices, discounts ("10% off", "₹300 off"), "sell the entire stock", ambiguous party/product names, multiple items, typos. Draw from real WhatsApp/slip language (anonymised) plus synthesised variants.
- **Images:** 150–300 invoice photos, order slips, and WhatsApp screenshots (varying quality, angle, printed vs. handwritten).
- **Labels (gold):** for each input, the correct structured event(s): `eventType`, party, product, quantity, amount, category, discount, line items, total.

**Run** every item through the existing `parseCommand` / `parseInvoiceImage`.

**Metrics:**
- `eventType` classification accuracy (+ confusion matrix — a great figure).
- Entity extraction: exact-match and fuzzy-match (normalized edit distance) precision/recall/F1 for party and product.
- Numeric accuracy for quantity/amount/total (exact and within-tolerance).
- **End-to-end "event correct with zero edits" rate** — the metric users actually feel.

**Comparisons (all free, no code change):**
- LLM vs. the **built-in heuristic** baseline (RQ1's ablation).
- **Across providers/models** — Anthropic vs. OpenAI vs. Groq vs. Gemini on identical inputs (a headline table; also lets you make a **cost/latency vs. accuracy** argument that matters for low-margin SMEs).
- Text vs. image modality.
- (With §4.2) monolingual vs. code-mixed.

### 3.2 Study B — Human-in-the-loop / confirmation study (answers RQ2, trust half)

Using the proposed-vs-confirmed diffs: how often does the model propose a wrong event, how often does the human *catch and fix* it at the confirmation screen, and how often do they wrongly accept a wrong event (**over-trust / automation bias** — a real, publishable risk). Report field-level edit rates and the residual error rate after confirmation. This directly justifies the "never auto-publish an AI-parsed event" design choice.

### 3.3 Study C — Task-time user study (answers RQ2, effort half; anchors the case study)

Within-subjects, N ≈ 12–25 participants (real shopkeepers if you can reach them; small-business owners or realistic proxies otherwise). Each enters the same set of transactions three ways: **(a) traditional form, (b) NLP text, (c) OCR image.** Measure **task completion time, error rate, task load (NASA-TLX), usability (SUS), and stated preference.** This is the evidence that turns "we built a thing" into "the thing measurably helps," and it is what a case-study framing needs. Get **ethics/IRB approval early** — it is the long pole.

### 3.4 Study D — Event-bus systems evaluation (answers RQ3; needs no code change)

Load-test the existing worker and outbox:
- **Throughput/latency:** events/sec the worker drains; end-to-end latency from business write to processed.
- **Recovery:** kill the worker mid-batch; confirm no lost or double-applied effects (the replay guards and `SKIP LOCKED` should hold) — **fault-injection / chaos testing** is a rigorous, reviewer-pleasing method.
- **Idempotency:** deliver duplicate events; confirm exactly-once *effect*.
- **Retry / dead-letter behaviour** under induced failures; **replay correctness** after resetting `status` to `pending`.
- Compare qualitatively (and, if you want, quantitatively on a small rig) against a RabbitMQ baseline to substantiate the *why-not-a-broker* claim.

### 3.5 Study E — Failure taxonomy (the high-value, low-cost contribution)

Qualitatively code every error from Studies A–C into a taxonomy: misclassification, hallucinated/invented products, wrong party matching, unit/currency confusion, code-mixing breakdowns, OCR-layout failures, multi-item under-extraction. Each category → a design implication. This is often the most-cited part of a systems-meets-AI paper.

---

## 4. New components to add depth (for four people)

You asked for more complexity, and you're right that the current scope is thin for four authors at a peer-reviewed venue. Below are **five candidate additions**, each of which (a) is a genuine sub-contribution with its own evaluation, (b) strengthens the central narrative rather than sprawling away from it, and (c) is demo-able. Build **two or three**, not all five. These are *new code* — additive modules that sit on top of the frozen core, not edits to it (so they respect the spirit of "don't change the existing code").

> **On the "don't change the code" instruction:** I read that as *don't refactor or destabilise what already works while you write the paper.* The evaluation in §3 honours it fully. The additions here are new, optional modules — build them only if you want the extra depth. If the constraint is literally "add nothing at all," then skip §4 and lean hard on §3 (a rigorous benchmark + user study + systems study can carry a paper on its own, especially at the journal tier).

### 4.1 Entity grounding / catalog linking *(strongest single addition)*

Right now the NLP emits a *free-text* product/party string ("rice", "kumar traders"). A real research component is a **grounding layer** that links that string to the business's actual catalog and party list — handling aliases, typos, abbreviations, and code-mixed names ("rice" → "Basmati Rice 25kg"; "kumar" → "Kumar Traders Pvt Ltd"). Approach: fuzzy matching + embedding-based retrieval over the tenant's catalog, with a confidence score. **Novelty:** entity linking against *tiny, noisy, per-tenant* catalogs with informal naming is meaningfully different from open-domain entity linking. **Evaluation:** linking accuracy@1/@k on a labeled set; ablation of fuzzy-only vs. embedding vs. hybrid. This is deep enough to be one person's whole workstream.

### 4.2 Code-mixed & multilingual input *(highest real-world relevance)*

Explicitly support and evaluate **Hinglish and regional-language** (Hindi/Kannada/Tamil, transliteration and script-mixing) input — the way SME owners actually type. Add a normalization/transliteration pre-step and language-aware prompting. **Novelty + fit:** directly serves the "informal SME sector" thesis and gives a clean evaluation axis (monolingual vs. code-mixed accuracy). This is a strong differentiator for the exact venues that would take this paper, and it is a natural second workstream.

### 4.3 Confidence-aware selective confirmation *(elegant, evaluable)*

Today every AI-parsed event goes to the confirmation screen. Model **field-level confidence** (via self-consistency across samples, token/logprob signals where available, or an LLM-as-judge) and **only interrupt the human when confidence is low** — an active human-in-the-loop optimization. **Research question:** how much confirmation burden can we remove while keeping post-confirmation error rate below a threshold? **Evaluation:** a burden-vs-error trade-off curve on the Study-A dataset. Ties beautifully to RQ2 and to the over-trust finding in Study B.

### 4.4 Voice input *(demo-friendly, extends multimodality)*

A speech front-end so the shopkeeper *speaks* the transaction (voice → ASR → the existing NLP pipeline). **Contribution:** robustness of the event extraction to ASR noise, and a third input modality alongside text and image. Very compelling in a demo/video and for the accessibility/low-literacy angle. Evaluation: end-to-end accuracy from audio, and ASR-error sensitivity.

### 4.5 LLM business advisor / lightweight forecasting *(uses the spec's stretch goals)*

The spec already lists an AI Advisor and Forecasting as stretch goals. Turn them into a real component: an LLM that reasons over the event history + health scores to produce **grounded recommendations**, and/or a lightweight **cash-flow / stock-out forecasting** model evaluated against held-out history. **Evaluation:** forecast error (MAE/MAPE) on held-out data; a small expert-rating study of advisor recommendations. This adds an ML/analytics dimension and a fourth workstream.

### 4.6 (Optional) Duplicate & anomaly detection

Because inputs arrive from multiple messy channels, the same transaction can be entered twice (typed *and* as a screenshot). A **reconciliation/anomaly** layer that flags likely duplicates and outliers is a natural, evaluable addition and reinforces the "consistency from messy inputs" theme. Keep this as a backup idea if one of the above proves too heavy.

---

## 5. Suggested four-person division of labour

Structure the team so each author owns a contribution they can defend — this also satisfies authorship-contribution statements that many venues now require.

- **Person 1 — Input Engine & benchmark lead.** Owns RQ1: builds the labeled dataset (§3.1), runs Study A, produces the multi-model and modality tables and the failure taxonomy (§3.5). Anchors §4.3 (selective confirmation).
- **Person 2 — Grounding & multilingual lead.** Builds §4.1 (entity grounding) and §4.2 (code-mixed input) and their evaluations. The deepest "new method" workstream.
- **Person 3 — Human factors lead.** Owns RQ2: designs and runs the user study (§3.3) and the confirmation/trust study (§3.2), handles IRB/ethics, SUS/TLX analysis. Optionally owns §4.4 (voice) for the accessibility angle.
- **Person 4 — Systems & analytics lead.** Owns RQ3: the event-bus evaluation and fault-injection (§3.4), the design-rationale/architecture write-up (the outbox-vs-broker argument), and §4.5 (advisor/forecasting).

Everyone contributes to writing; one person (often Person 1) owns the intro/framing and holds the narrative together.

---

## 6. Paper outline (fill-in structure)

A systems-plus-empirical paper, IMRaD-adapted. Target lengths assume an 8–12 page conference paper; expand for a journal.

1. **Abstract** — problem (SME data-entry friction), approach (multimodal human-in-the-loop input engine on an event-driven core), key results (headline accuracy number, user-study time reduction, systems guarantee), one-line significance.
2. **Introduction** — the adoption gap; why structured entry is the barrier; the three contributions (§1.3); a results teaser.
3. **Related work** — (a) NL interfaces to data / semantic parsing / NL2SQL; (b) LLM structured extraction & document/key-information extraction (invoices); (c) transactional outbox & event-driven architecture ("database as a queue"); (d) ICT4D / ERP adoption in SMEs & emerging markets; (e) human-in-the-loop & automation bias. End each with the gap you fill.
4. **System design** — architecture (the outbox event bus, worker, workflow engine), the Business Input Engine pipeline (parse → validate → **confirm** → publish), the design rationale (why not RabbitMQ/Express/a separate AI service), the new components you built (§4).
5. **Implementation** — stack, the provider-agnostic AI layer, idempotency/replay mechanics, multi-tenancy. Brief; point to the open-source repo.
6. **Evaluation** — Method + results for Studies A–E and the new-component evaluations. Lead with RQ1, then RQ2, then RQ3.
7. **Discussion** — the failure taxonomy and its design implications; over-trust; cost/latency trade-offs for low-margin users; when the heuristic is "good enough" offline; threats to validity.
8. **Limitations & future work** — dataset scope, participant representativeness, single-region generalizability.
9. **Conclusion.**
10. **Artifacts** — released dataset + code + evaluation harness (many venues give an artifact badge; this materially helps acceptance).

---

## 7. Artifacts & data to gather (checklist)

- [ ] **Labeled text-command dataset** (with gold structured events) — the flagship releasable artifact.
- [ ] **Labeled image dataset** (invoices/slips/screenshots) — anonymised; watch for PII in real invoices.
- [ ] **Code-mixed subset** with language labels (if doing §4.2).
- [ ] **Evaluation harness** — a script that runs the dataset through `parseCommand`/`parseInvoiceImage` and computes the metrics (this is new *tooling*, not a change to the app).
- [ ] **Provider run logs** — raw model outputs for each provider for reproducibility.
- [ ] **Confirmation diffs** — proposed-vs-confirmed events (via logging or the study harness).
- [ ] **User-study protocol + instruments** — task script, SUS, NASA-TLX, consent forms; **IRB/ethics approval**.
- [ ] **Systems-benchmark rig** — load generator, fault-injection scripts, metrics capture for the worker.
- [ ] **Anonymisation & consent** for any real SME data — do this before collecting, not after.

---

## 8. Suggested timeline (≈ one semester, adjust to your deadline)

- **Weeks 1–2** — Lock the venue and RQs; draft related work; start IRB; freeze the core code and set up the eval harness.
- **Weeks 3–5** — Build and label the datasets (all four help; this is the long pole with IRB); build the two chosen §4 components.
- **Weeks 6–8** — Run Studies A, D, E and the new-component evaluations; iterate on the datasets.
- **Weeks 7–9** — Run the user study (Studies B, C) once IRB clears.
- **Weeks 9–11** — Analysis, tables, figures; write the full draft.
- **Weeks 11–13** — Internal review, polish, artifact packaging, submit.

---

## 9. The three things that most determine acceptance

1. **A real, well-labeled dataset of authentic SME inputs.** It is the paper's spine, the fairest baseline comparison, and a citable artifact. Invest here first.
2. **The multi-model + baseline comparison, and the failure taxonomy.** These convert "we built a system" into "we produced generalizable knowledge about LLM business-event extraction." The provider-agnostic layer hands you the comparison almost for free.
3. **A credible user study.** It is what earns the "case study" framing and answers the reviewer's "so what — does it actually help these users?" Start the IRB now; everything else waits on it.

Do these three well and the added §4 components give four authors enough distinct, defensible depth to clear a peer-reviewed bar.
