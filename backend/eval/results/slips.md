# SmartSME extraction accuracy

Generated 2026-09-15 23:47 - engines: vision, ocrspace

P/R/F1 are percentages. **Exact** is the share of inputs where every scored field was right, which is the share a shopkeeper could accept without editing anything.

### Handwritten order slips (n=12, real photographs)

| Engine | n | Exact | party P/R/F1 | phone P/R/F1 | items P/R/F1 |
|---|---:|---:|---:|---:|---:|
| **vision** | 12 | 100.0% | 100.0/100.0/100.0 | 100.0/100.0/100.0 | 100.0/100.0/100.0 |
| **ocrspace** | 12 |  75.0% | 100.0/100.0/100.0 | 100.0/100.0/100.0 |  89.2/ 94.3/ 91.7 |


### Variants

- `en` - English
- `hi-latn` - Hindi in Latin letters
- `hi` - Hindi (Devanagari)
- `kn-latn` - Kannada in Latin letters
- `kn` - Kannada (Kannada script)
