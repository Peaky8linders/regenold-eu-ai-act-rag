# R461 promotion canary

Endpoint `https://regenold-eu-ai-act-rag-production.up.railway.app` — 8 fixed official hard-board questions, one draw each.
pre commit `ca71879d7059` → post commit `e1fba9733755`.

| row | budget | pre refs | post refs | pre chars | post chars |
| :-- | --: | --: | --: | --: | --: |
| `rg_028` | 2 | 1 | 1 | 402 | 620 |
| `rg_034` | 2 | 2 | 1 | 450 | 252 |
| `rg_040` | 2 | 2 | 2 | 808 | 808 |
| `rg_043` | 2 | 1 | 1 | 846 | 846 |
| `rg_049` | 2 | 1 | 1 | 368 | 376 |
| `rg_052` | 2 | 2 | 4 | 624 | 986 |
| `rg_004` | 2 | 6 | 2 | 652 | 564 |
| `rg_007` | 3 | 5 | 3 | 884 | 890 |

mean refs **2.5 → 1.875**, in budget **6/8 → 7/8**, mean chars 629.2 → 667.8.

Gates: **PASS** — pre `ca71879d7059`, post `e1fba9733755`.

Primary-leg re-run on the round-close merge `7fbd46737548`: see `CANARY-PRIMARY.md` (PASS 5/5, `openai_wrapper` serving).
