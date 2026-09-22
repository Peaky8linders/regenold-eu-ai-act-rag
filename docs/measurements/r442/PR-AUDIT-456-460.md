# R442 — audit of PRs #456–#460, by execution

**Date:** 2026-09-23 · **Range:** `c74ca99..1aa09b8` · **Method:** four independent
review lenses (prompt path, legal accuracy, eval harness, performance headroom),
every finding reproduced by running code offline (sockets blocked) before it was
acted on, then re-verified by the lead. Probes: `docs/measurements/r442/*.py`.

## 1. Production-path findings (default flags)

| # | sev | finding | disposition |
| :-- | :-- | :-- | :-- |
| P1 | P1 | **R439's `engaged_coords` head rule was applied to EVERY parent**, so a named paragraph whose content IS the list lost it: "When does the Article 6(3) derogation apply?" dropped 6(3)(a)–(d), "What does Article 9(2) require?" dropped 9(2)(a)–(d) — and the ANSWER SHAPE clause then tells Stage-2 not to enumerate what is outside the engaged set. Bare-head asks it did fix fell to one item: `rg_105` "What is Annex X about?" 825 → **375** chars against a **625**-char reference answer (the R423.1 starvation shape). | **Fixed.** Rule scoped back to heads (the doctrine `_member_gaps` already applies); a whole-head ask with no engaged paragraph takes the R423.1 no-signal floor (650). Measured on the route's real inputs for the official 110 (`engage_fixed.py`): engaged sets identical to R439 on every row; the ONLY answer-shape change is `rg_105` 375 → 650. |
| P1 | P1 | **PR #456's compact REFERENCE MINIMALITY / SUB-PARAGRAPH clauses ship default ON with no gold gate** (AGENTS.md invariant #5): +441 chars on every Stage-2 request vs `c74ca99`; on `rg_080` the SUB-PARAGRAPH "do not enumerate a set the question did not ask for" contradicts the ANSWER SHAPE clause's seven engaged items. | **Documented, not reverted** — the operator merged it as a defect repair, and reverting is itself an ungated production change. Gate before relying on it: `easyhard_ab` with `REGENOLD_USER_REF_MINIMALITY=0 REGENOLD_SUBPARAGRAPH_ATTRIBUTION=0` as the baseline arm. |
| P2 | P2 | On the evidence-contract path `REGENOLD_PROMPT_V2=1` removes both clauses and adds nothing; `REGENOLD_PROMPT_V3=1` and `REGENOLD_PROMPT_COMPACT=1` dispatch a request byte-identical to the default. All three are cache-keyed, so an A/B on them measures noise. | Documented at the call site (the comment claimed "Prompt V3 owns its own consolidated versions"). |
| P3 | P3 | `_shrink_user_for_groq`'s new overflow branch can cut mid-word and treats everything after the first optional clause (incl. CHALLENGE / VALID COORDINATES) as droppable. | **Deferred** — unreachable at default flags: strict transport refuses Groq, and the route's 4,000-char message cap keeps real requests under budget. |

## 2. Default-OFF lever: `REGENOLD_GROUNDED_BRANCH_GUARDS` (PR #457)

| finding | fix |
| :-- | :-- |
| Reads the flattened conversation: in hard mode the fixed preamble fires **all 11 blocks (5,611 chars) on every R440 gate row**; the live question fires 2–5 (`r440_guard_scope_probe.py`). | Reads only the text after the last `Latest question:` marker. |
| Substring triggers: `"article 9"` ⊃ Article 90–99 (rg_049 Art. 95), `"polic"` ⊃ policy, `"annex i"` ⊃ Annex II/III/IV (MEDICAL-DEVICE block, sole trigger on 11 official rows), `annex\s+i(?![ivx])` ⊃ "annex is/in", `"corrective action"` put the Art. 80 block on an Art. 20 question, `"instructions for use"`/`"logging"` put the deployer block on provider questions; missed "deep fake"/"deep-fake". | Word-bounded patterns; deployer block needs Art. 26 or a deployer + logs/instructions ask; Art. 80 block needs Art. 80 or an MSA + non-high-risk ask. |
| Two BIOMETRIC blocks fired together and disagreed: one called Art. 5(1)(g) the ban on categorisation "by sensitive or protected attributes" (Annex III 1(b)'s wording; 5(1)(g) is a closed list — the R410 error). MEDICAL-DEVICE duplicated ANNEX I. | One biometric block (the verified one), one Annex I block. |
| Misstated law, checked against `get_provision_text`: Art. 6(3) "no-significant-risk and no-material-influence conditions" (the gate is *any of* (a)–(d); material influence is part of the risk test; 6(4) documentation + registration omitted); Art. 26(6) "at least six months" (the period is *appropriate to the intended purpose*, of at least six months); Art. 80(2) "prescribes a period" (*may prescribe*, and *without undue delay*); "notified-body" for "third-party conformity assessment". | Rewritten from the verbatim text. |
| Two sentences echoed our reconstructed gold criteria, not the Act ("a new use is not excused merely because…", "resemblance to investigation…"), and a `"supermarket"` trigger that commit 26dc382 had already removed as benchmark overfit came back. | Removed. |

**R440's verdict is void** (correction appended to `docs/measurements/r440/CHECKPOINT.md`):
the harness wrote `"void": ["hard"]` and arm A sample 0 has 13 fallback-served rows,
which PREFLIGHT §4 forbids; without those pairs the binding conciseness cost is
**−0.88 [−4.27, +2.11]** (`r440_drop_fallback.py`, reproducing the published
−3.14 [−6.55, −0.10] with them). Lever stays OFF — unmeasured, not refuted.

## 3. Other default-OFF / offline findings

| finding | disposition |
| :-- | :-- |
| R441 emotion exclusion: comment says emotion questions "are Article 5(1)(f) prohibition questions, not Article 50" — wrong law (5(1)(f) is workplace/education only; Art. 50(3) binds emotion-recognition deployers). The exclusion is still right *for this supplement* (it can only append a bare `Article 50`, which the deepener resolves to 50.1/50.4, and 5 of 7 corpus flips moved toward gold). Trigger lookaheads lacked `re.DOTALL`. | Comment corrected with the real rationale; `re.DOTALL` added (both call sites pass the live question only); test restated + multi-line case. |
| Owner lock (PR #458): `os.kill(pid, 0)` on Windows is `GenerateConsoleCtrlEvent` — with the owner and a second runner in different consoles (two terminals, the R440 incident) the check raised WinError 87 and the second runner **ACQUIRED** over a live draw; `release()` unlinked a successor's lock. | Rebuilt as an OS-held byte-range lock (`evals/regenold/run_lock.py`); two-sided in the cross-console topology (old: ACQUIRED, new: REFUSED), plus hard-kill recovery. |
| `OntologyPatchProposal` accepted `layer="bogus"`, a bare-string `target_ids` (iterated as characters), non-evidence items; `evidence_keys` dropped the version its docstring promises. | Type checks + versioned keys. |
| `branch_cluster_gate.py`: no void/provenance check; refuse rule averages instead of per-row; SHIP and NO WIN both exit 0; "median −5.61" is a difference of medians (paired median +0.00). | Recorded in the R440 correction; the one-off script is not reused. |
| Answer-key coordinate forms: 4 served refkey refs fail `coordinate_exists` (`Annex I.a.11`, `Annex I.a.2`, `Annex VIII.a`, `Article 85.1`); Annex I is numbered 1–20 *continuously* in the adopted text. | Not changed here: an uncommitted scorer-side alias for this (R441, another agent's in-flight work) is in the shared tree. Its Section B mapping (`Annex I.19` → `Annex I.b.7`) assumes restart numbering the corpus does not use; a key-side rewrite to the adopted numbering is the better fix. |

## 4. Performance headroom (hard mode, local instrument)

Replaying today's wire passes over recorded draws reproduces the R419 board's
reference axes exactly and puts the current engine at **Overall ≈ 82.6** locally
(37 rows × 9 draws; reconstructed criteria + Qwen-235B judge — not an official
number). Ref Strict is no longer the gap (R425/R429/R431 already add +7.35 pp);
weighted by geometric-mean leverage, what is left is Ref Conciseness (+1.34 pp
Overall if closed), Speed (+1.01) and Answer Conciseness (+0.40). **No
reference-list transform replayed at HEAD survives hard rule #8.**

The largest measurable lever is **RESERVE**: answer the evaluator's verbatim
pushback with the verified previous answer instead of a fresh generation — Speed
79.0 → 94.8 on the current pool, ≈ +2.1 pp Overall locally (+0.7 to +1.3 pp at
the official point). **It is not built:** it contradicts the standing operator
rule "always Stage-2", and as specified it drops gold heads on two pools (+1, +2),
so it needs an operator ruling first. Spec and replay: SOTA probes, session
scratchpad (`reserve_textrule.py`).

## 5. Opus 5.5

Selectable over the tunnel after upgrading the wrapper host's Claude Code to
2.1.280; live screen shows correctness parity at ~25 % more text. See
[`OPUS55-SCREEN.md`](OPUS55-SCREEN.md).
