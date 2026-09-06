# R387 — make `REGENOLD_REF_GRAIN_DEEPEN` a code default

**Goal.** Flip the R386 grain deepener from opt-in to default ON. The only thing
standing between here and that flip is a 27-test contract migration.

---

## Where things stand

`main` is at `3e2eaf4`, merged via PR #378, pushed. Working tree clean.
Suite baseline: **3 failures**, all pre-existing and unrelated to R386 —
`test_kb_consistency::test_kb_version_bumped_when_content_changes`,
`test_r63c_stub_selection::test_kb_version_unchanged_after_r63c` (both from the
R384 `kb.py` edit), and the long-documented
`test_r365_citable_base_guard::test_default_wire_is_byte_identical_to_pre_r365`.

The lever itself is built, wired, cache-keyed, wire-proven and covered by 23
tests. It is **already gated and already passing**:

| gate | result |
| :--- | :--- |
| our gold-bearing probe corpus, n=129, `evals.bench.metrics` | `gold_dropped_head` 37 → 37 (**+0**), every axis byte-identical, 284 refs changed |
| R386 minimal-gold set, n=99, official-rubric scoring | **Ref Strict 18.3 → 37.3 (+19.0 pp)**, RefLoose and RefConc unchanged, +0 gold |
| live paired A/B, n=60 over the tunnel, 23 zero-variance rows | head set unchanged **23/23** → +0 live; grain 32.8 % → 77.6 %; **Ref Strict +7.9 pp** |

So this is **not** a "prove the lever" session. It is a contract-migration
session.

---

## The one task

`docs/measurements/r386/CONTRACT_MIGRATION_WORKLIST.md` holds the exact 27
failing tests, already derived (a fresh derivation costs a ~20-minute two-arm
suite run — don't redo it).

Every one is a **grain-form assertion**: it compares full reference strings
where the HEAD is what the test means. Two representative cases:

* `test_r365_recall_supplements::test_wire_guard_only_emits_declared_heads`
  fails because `Annex III.7` is not literally a member of a set of declared
  HEADS whose member `Annex III` covers it.
* `test_r95_noise_suppress::test_route_chatbot_disclosure_surfaces_art50` wants
  `Article 50` on a chatbot-disclosure question, where the lever emits
  `Article 50.1` — which *is* the disclosure duty.

The migration is to compare at the grain each assertion actually means, usually
by head-projecting the comparison (`{r.split(".")[0] for r in refs}`) or by
accepting `r == X or r.startswith(X + ".")`.

### Hard constraints

1. **`AGENTS.md`: never alter or suppress a failing test to force a pass.**
   Migrating a contract the code deliberately and measurably changed is
   legitimate. Weakening one to go green is not. If any test turns out NOT to be
   grain-form, that is a real regression — stop and report it, do not migrate it.
2. **Negative assertions stay exactly as strict.** `assert "Article 43" not in
   refs` must not become satisfiable by `Article 43.2`. An exclusion test exists
   to enforce an exclusion; head-projection must be applied to the *positive*
   side only, or the negative must explicitly reject the whole cluster.
3. **Per-test judgement, not a bulk regex.** The blast radius is why this was
   split out of PR #378 in the first place. A `sed` across 17 files is precisely
   the thing that masks a regression.

### Suggested shape

Ultracode is on, so orchestrate it: one agent per test **file** (17 files, not
27 tests — tests in a file share fixtures and idiom), each of which must first
*classify* its failures as grain-form or real, then migrate only the grain-form
ones. Follow with an adversarial verify pass — a second, independent agent per
edited file whose brief is to **refute** that the edit preserved intent, with
special attention to negative assertions. Majority-refute ⇒ revert that edit.

---

## Verification before committing

```bash
git checkout main && git pull
```

1. Flip the default in `app/routes/regenold.py::_ref_grain_deepen_enabled` to
   the **deny-list** form (R379's P2-7 finding: a default-ON gate written with
   allow-list truthiness silently reverts to OFF on `=Y`, `=enabled` or a blank
   value while the cache key still records the variable — an A/B that compares
   OFF to OFF):
   `os.getenv("REGENOLD_REF_GRAIN_DEEPEN", "1").strip().lower() not in ("0","false","no","off")`
2. Re-point `tests/test_r386_ref_grain_deepen.py::TestDefaultOff` at the new
   default, and add the opt-out/non-negative-value cases.
3. **Two-arm full suite IN PLACE**, one flag differing — never a worktree
   baseline, which manufactures phantom regressions:
   ```bash
   REGENOLD_SKIP_DOTENV=1 python -m pytest tests/ -q
   REGENOLD_SKIP_DOTENV=1 REGENOLD_REF_GRAIN_DEEPEN=0 python -m pytest tests/ -q
   ```
   Target: **both arms at the same 3 pre-existing failures, zero new.**
4. Re-run both gates against the production functions:
   ```bash
   python docs/measurements/r386/score_prod.py
   ```
   Target: GATE 1 delta `+0`; GATE 2 Ref Strict `+19.0 pp`, delta `+0`.
5. Run `tests/test_r355_cache_key_complete.py` — `app/routes` is **not** scanned
   by the AST gate, so the registration is by hand and must be re-checked.

---

## Then, in priority order

1. **The 33 missed opportunities.** On the minimal-gold set the deepener leaves
   33 references at head grain where gold names a sub-point. Thresholds are a
   plateau (every `MIN_TOP` 1–6 × `MIN_MARGIN` 1–4 scores 35.5–37.0, none drops
   gold), so more coverage needs a *better signal*, not a looser threshold —
   the Neo4j `Point` nodes carry `.letter` (R380 fixed the Cypher) and would
   give letter-grain (`Article 5.1.f`), which the current paragraph-only pass
   cannot reach.
2. **`REGENOLD_QREL_PRUNE` is now an operator decision.** Against minimal gold
   it costs **1** gold head (not the 19 our non-minimal probe gold claimed)
   while gaining +4.7 RefLoose and +7.2 RefConc. Hard rule #8 is literally
   "drop ZERO more", so it needs an explicit operator call, not an agent's.
3. **Widen the minimal-gold set.** 11 of 110 rows have no stable key. Three
   draws instead of two, or majority-of-three instead of intersection-of-two,
   would recover most of them.
4. **The probe's known bias.** It reads RefConc **38.5 against the printed
   50.4** on the run the report graded — it under-recalls the *second* expected
   reference (validation recall 5/7). It is a **relative** instrument; never
   quote its absolutes as official-scale.

---

## Artifacts

All under `docs/measurements/r386/`:

| file | what it is |
| :--- | :--- |
| `minimal-gold-probe-set-n110.jsonl` | the gold set — 99 stable keys, 11 marked `unstable` |
| `mingold.py` | how it was built (question-only, two passes, pass 2 double-sampled and intersected) |
| `score_prod.py` | **both gates against the production functions** — run this, not a copy |
| `live-paired-ab-n60.json` | the live A/B capture, per-row transport attribution |
| `live_ab_analyse.py` | reads that run on the zero-variance subset |
| `gold-bearing-probe-live-capture-n129.json` | the corpus that rejected the R381 cap and R385 prune |
| `CONTRACT_MIGRATION_WORKLIST.md` | **the 27 tests** |

Context to read first: `CLAUDE.md` § R386 (both findings, and the honest limits).
