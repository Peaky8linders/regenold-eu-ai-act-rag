## Mirror and live query disagree on shape during outage
- file: `app/engines/kg_context.py:823`
- bug: The outage path in `fetch_subpoint_detail` falls back to `_mirror_subpoints` which returns only SubPoint rows, but the live query `_SUBPOINT_CYPHER` returns both Point and SubPoint rows. This causes the mirror to serve a different shape during an outage, reintroducing the R408 "a long first provision evicts the rest" defect.
- evidence: "R418 — the ON branch's outage path must answer in the SAME shape. It used to fall through to ``_mirror_subpoints``, which emits SubPoint rows only (the pre-R408 legacy shape) and fills them greedily in ref order, so a single-turn ask during an Aura outage silently received the LEGACY block — a different Stage-2 prompt, logged only as ``kg_local_mirror_served``."
- impact: During an Aura outage, the system serves a different prompt shape that reintroduces the R408 defect where a long first provision can evict others from the context, leading to incomplete answers.
- fix: Change the fallback to use `_mirror_point_units` instead of `_mirror_subpoints` to maintain consistent shape between live and mirror queries.
- confidence: 95

## Connection failure path swallows error and returns empty context
- file: `app/engines/kg_context.py:763`
- bug: The guard `if rows and not getattr(rows, "failed", False)` treats an empty result from a working graph as a failure, causing the mirror to serve text the graph does not hold. The correct guard should only use `not getattr(rows, "failed", False)` to distinguish real failures from empty matches.
- evidence: "R418 — consult the local mirror ONLY on a real read failure. ``_ReadRows`` carries ``failed`` precisely to tell an error apart from an empty match, and a healthy empty result is a legitimate answer. The old guard (``if rows and not failed``) treated ``[]`` from a WORKING graph as an outage, so the mirror — built from the in-process regex parser, not the seeded graph — served text the graph does not hold, and logged it as ``kg_local_mirror_served``."
- impact: The system incorrectly treats empty but valid graph responses as failures, causing the mirror to serve potentially incorrect text and log it as if it came from the mirror during an outage.
- fix: Change the guard to `if not getattr(rows, "failed", False):` to only fallback on actual failures, not empty results.
- confidence: 95

## Mirror build failure is cached permanently
- file: `app/engines/kg_context.py:688`
- bug: When `_mirror_index` fails to build, it sets `_MIRROR_CACHE = {}`, making a single transient fault permanent for the process lifetime. The failure should not be cached to allow retry on subsequent requests.
- evidence: "R418 — do NOT cache the failure. ``_MIRROR_CACHE = {}`` made a single transient fault permanent: a boot-order import problem or one malformed node returned ``[]`` for the rest of the process while the warning was logged once, so the mirror silently stopped being a fallback at all. Not caching re-attempts the build on the next consult; the mirror is only ever consulted after a real graph read failure, so the retry cannot slow a healthy request."
- impact: A temporary failure during mirror build permanently disables the mirror fallback for the entire process lifetime, removing a critical resilience feature.
- fix: Return `{}` without caching it when the build fails, allowing retry on the next request.
- confidence: 95

## NEEDS MORE EVIDENCE
None
