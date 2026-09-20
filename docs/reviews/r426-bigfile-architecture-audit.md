# R426 — big-file architecture audit: where the 25.7 kLOC actually goes

Status: **audit complete, plan agreed, first tranche not yet shipped.** Everything
below is measured; the two instruments are committed and re-runnable:

```
.venv/Scripts/python.exe -m docs.measurements.r426.bigfile_audit --top 20 --json
.venv/Scripts/python.exe -m docs.measurements.r426.flag_inventory --json
```

## 0. What was asked

"Optimise the big LOC files, analyse the end-to-end architecture, find the best
design and interfaces so we can simplify and reduce, plus dead code, repeated or
broken code."

## 1. The headline finding: dead code is not the problem

The audit looks for every top-level definition in the repo's largest 20 modules
that is referenced nowhere else — neither again inside its own module nor in any
other file, test, script or root doc. It finds **two**, totalling 14 lines:

| module | name | lines |
| :-- | :-- | --: |
| `app/main.py` | `_redact_probe_payload` | 5 |
| `app/integrations/regenold/grounded_prose.py` | `_format_lead_citation_list` | 9 |

Every other top-level definition in `regenold.py` (150) and
`_graph_rag_impl.py` (161) is reachable. So the "there must be thousands of lines
of dead code" hypothesis is **false**, and any plan that promises LOC reduction by
deleting dead code is promising something that does not exist. That is worth
knowing before spending a week on it.

Same result for same-named duplication: no top-level name is defined in two of the
top-20 modules. The repetition that *does* exist is not name-identical (see §3.3).

## 2. The real structure: 25 functions hold 14,807 lines

```
functions >= 150 lines: 25 holding 14,807 LOC
   3660  app/routes/regenold.py:regenold_eu_ai_act_ask
   1083  app/engines/_graph_rag_impl.py:_deterministic_answer
    986  app/routes/regenold.py:_engine_cache_key
    953  app/engines/_graph_rag_impl.py:_claude_max_enhance_answer
    854  app/engines/_graph_rag_impl.py:_openai_wrapper_complete_for_graph_rag
    812  app/engines/_graph_rag_impl.py:_deterministic_parse
    574  app/integrations/regenold/models.py:normalise_answer_for_regenold
    540  app/engines/_graph_rag_impl.py:ask_compliance_question
    478  scripts/seed_neo4j_kb.py:build_payload
    406  app/engines/_graph_rag_impl.py:_two_stage_generate_inner
    364  app/integrations/regenold/scope.py:classify_conversation
```

`regenold_eu_ai_act_ask` alone is **3,660 lines** — 28 % of its module, and larger
than most files in the repo. `_engine_cache_key` is **986 lines** to compute a
cache key. Both files are 12.8 kLOC with ~150 defs each, i.e. the file size is not
"many small functions", it is "a few functions that swallowed their modules".

Configuration is the other half of the story:

| | route | engine |
| :-- | --: | --: |
| top-level defs | 150 | 161 |
| `*_enabled()` predicates | 39 | 29 |
| reference/citation-named defs | 46 | 13 |
| distinct `REGENOLD_*` flags READ | 85 | 44 |

**128 distinct flags are read on the critical path and only 18 of them have a row
in `CLAUDE.md`** (110 have no record at all; 1, `REGENOLD_WIRE_REF_CAP`, is
documented as permanently rejected). A switch that a measurement round has
rejected is not a switch: it is an untakeable branch plus the code it guards.

## 3. The three concrete defects

### 3.1 The route re-implements the engine's reference pipeline
46 reference/citation helpers in the route against 13 in the engine, with **zero
name overlap** — two parallel implementations of the same concept, and the route's
copy is the one that decides what the evaluator grades. Every reference-layer
lever this project has shipped (R133, R325/R366, R381, R386/R388, R397, R425) had
to be reasoned about in *both* layers, and the R424 §7 finding ("the wire ships a
limb the prose never names") was exactly a failure of the route's copy to agree
with the engine's.

### 3.2 `_engine_cache_key` is a transcription, not logic
986 lines whose only job is to return a tuple of ~300 literals. Its correctness
depends on nobody forgetting a line, which is why the repo needs an AST gate
(`tests/test_r355_cache_key_complete.py`) to catch omissions — a structural
admission that the shape is wrong. A derived key would need no such gate.

### 3.3 The stage-2 transport exists twice
`_openai_wrapper_complete_for_graph_rag` (854) and `_claude_max_enhance_answer`
(953) each carry request shaping, the Cloudflare-Access headers, a retry policy,
the degenerate/one-token-completion guard, the fallback decision and the
`stage2_served_by` bookkeeping. The R420/R425 rounds each had to patch *both* the
serve-marking and the fallback policy, and the R419 outage (the wrapper returning
one-token completions while the Bedrock leg was dead) was diagnosed by hand across
both.

## 4. Target design and interfaces

Four extractions, each a **pure move** behind a named interface, ordered by
value/risk. None of them is a rewrite; none of them changes behaviour.

### T1 — `app/llm/stage2.py`: one transport interface  *(highest value)*
```python
@dataclass(frozen=True)
class Stage2Request:
    system: str
    user: str
    max_tokens: int
    context: dict[str, Any]      # row id, history, purpose (turn-1 vs pushback)

@dataclass(frozen=True)
class Stage2Outcome:
    text: str
    leg: str                     # "primary" | "fallback" | "deterministic" | "prior_turn"
    attempts: int
    degenerate_rejections: int

def dispatch_stage2(request: Stage2Request) -> Stage2Outcome: ...
```
Absorbs ~1,400 lines from §3.3 and makes "which leg served this answer" (R417) and
"retry before falling through" (R418) properties of ONE function instead of two
call sites.

### T2 — `app/routes/refpasses.py`: an ordered, declarative reference pipeline
```python
@dataclass(frozen=True)
class RefPass:
    name: str
    enabled: Callable[[], bool]
    applies: Callable[[RefContext], bool]
    run: Callable[[list[str], RefContext], list[str]]

PIPELINE: tuple[RefPass, ...]          # order is the contract, and it is data
def apply_ref_pipeline(refs: list[str], ctx: RefContext) -> list[str]: ...
```
Absorbs the route's post-Stage-2 passes into one module where the **order** is a
single readable list. Every ordering bug this project has hit (the deepener before
the prose pass, R397 before R386, R425 after both) was an ordering argument held
in someone's head.

### T3 — derived engine cache key
```python
#: (flag name, reader) — the key is derived from THIS, never transcribed.
KEY_FLAGS: tuple[str, ...] = (...)
def _engine_cache_key(...) -> tuple: return (*KEY_FLAGS_READERS, *structural_parts)
```
986 → order-of-100 lines, and the R355 AST gate stops being load-bearing.

### T4 — decompose the route handler into phases
`regenold_eu_ai_act_ask` becomes a thin orchestrator over a `RouteContext`:
`resolve_intent → retrieve → draft → polish → repair → finalise_references →
trace`. The phases already exist as comments; they need to become functions with
typed inputs and outputs.

## 5. Sequencing, gates, and what NOT to do

**Gates for every tranche** (this is a graded pipeline; "it still imports" is not
evidence):

1. full suite green on a clean clone with `.env` loaded (the R365 offline guards
   fail a bare worktree on purpose);
2. a **byte-identical** side-by-side on recorded draws — the technique that gated
   R386, R388 and R425 (replay the same rows before/after the move and diff the
   answers, reference sets, heads and counts). A pure move must produce `+0` on
   every row;
3. the AST gates (`test_r355_cache_key_complete`, `test_r394_2_tracked_module_imports`);
4. ruff clean on every touched file.

**Not doing:** a big-bang rewrite; bundling behaviour changes with moves; deleting
"dead code" that does not exist; refactoring a file a concurrent editor currently
holds uncommitted hunks in (see below); touching `app/data/eu_ai_act_corpus.py`
and `official_eu_ai_act.py` — 8.5 kLOC and 7.8 kLOC of *data*, where size is the
point.

## 6. First tranche — the one to do next

**T1 (stage-2 transport)** is the recommendation to start with, because it is the
only one that is simultaneously (a) in an uncontested file
(`_graph_rag_impl.py` has had no edits from another thread), (b) high value
(~1,400 lines, and it retires a duplicated policy that has caused two production
outages), and (c) gate-able by the existing recorded-draw replay.

**Ordering constraint discovered this round.** `app/routes/regenold.py` in the
shared checkout holds an unrelated, uncommitted feature from a concurrent thread
(an ontology citable expansion: `_expand_citable_bases_with_ontology` plus its two
call sites inside `regenold_eu_ai_act_ask`). T2/T3/T4 all live in that file. They
should start only once that work has landed, otherwise the two refactors collide
in the same 3,660-line function. R425 shipped around this by committing an
explicitly reconstructed blob (`docs/measurements/r425/stage_my_hunks.py`), which
is a workaround, not a process.
