# SmartSME extraction accuracy

Generated 2026-09-16 16:00 - engines: heuristic, google

P/R/F1 are percentages. **Exact** is the share of inputs where every scored field was right, which is the share a shopkeeper could accept without editing anything.

### Typed notes (n=70, synthetic)

| Engine | n | Exact | type P/R/F1 | party P/R/F1 | items P/R/F1 | amount P/R/F1 | category P/R/F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **heuristic** | 70 |  85.7% | 100.0/100.0/100.0 | 100.0/ 90.2/ 94.8 |  93.4/ 90.5/ 91.9 | 100.0/ 90.9/ 95.2 | 100.0/100.0/100.0 |
| **google** | 70 |  97.1% | 100.0/100.0/100.0 | 100.0/100.0/100.0 |  98.4/ 95.2/ 96.8 | 100.0/100.0/100.0 | 100.0/100.0/100.0 |


### By variant - heuristic

| Variant | n | Exact |
|---|---:|---:|
| en | 18 |  66.7% |
| hi | 11 | 100.0% |
| hi-latn | 18 |  77.8% |
| kn | 11 | 100.0% |
| kn-latn | 12 | 100.0% |


### By variant - google

| Variant | n | Exact |
|---|---:|---:|
| en | 18 |  94.4% |
| hi | 11 | 100.0% |
| hi-latn | 18 |  94.4% |
| kn | 11 | 100.0% |
| kn-latn | 12 | 100.0% |


### Variants

- `en` - English
- `hi-latn` - Hindi in Latin letters
- `hi` - Hindi (Devanagari)
- `kn-latn` - Kannada in Latin letters
- `kn` - Kannada (Kannada script)
