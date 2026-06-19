"""F1 fix — 2-hop budget no longer crowded out by hop1 for hub seeds.

Both backends order ``(hops, num)`` then ``LIMIT cap`` with the old
``cap = max(max_hop2*2, 4)`` (= 10). The 1-hop neighbours of any HUB seed
(Art. 5/6/26 each ≥10) fill the LIMIT, so ZERO hop2-only refs survived → the
2-hop feature contributed nothing for the most-common anchors. The fix sizes
the SQL cap to the catalog ceiling so the Python-side ``max_hop2`` cap is the
binding output limit. Env-reversible via ``REGENOLD_GRAPH_2HOP_FULL_CAP=0``.

These exercise the now-live embedded backend (conftest pins ``neo4j``, so the
embedded path is opted into per-test). davidath is byte-identical because the
bench leaves ``REGENOLD_GRAPH_2HOP`` unset (2-hop OFF regardless of this flag).
"""
from __future__ import annotations

import pytest

from app.data.article_existence import ARTICLE_EXISTENCE


class TestFullCapGate:
    def test_default_on_and_off_overrides(self, monkeypatch):
        from app.engines.graph_expand_2hop import _full_cap_enabled

        monkeypatch.delenv("REGENOLD_GRAPH_2HOP_FULL_CAP", raising=False)
        assert _full_cap_enabled() is True  # default ON
        for off in ("0", "false", "no", "off", "OFF", " 0 "):
            monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", off)
            assert _full_cap_enabled() is False
        for on in ("1", "true", "yes", "on", "anything"):
            monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", on)
            assert _full_cap_enabled() is True


class TestHubSeedHop2:
    def _setup(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")

    def test_fix_surfaces_hop2_for_hub_seed_was_empty(self, monkeypatch):
        # A/B on the SAME hub seed: OFF reproduces the crowd-out bug
        # (Art. 6 has ≥10 one-hop neighbours → cap=10 leaves no room), ON
        # surfaces hop2-only neighbours.
        self._setup(monkeypatch)
        from app.engines import graph_expand_2hop as g2

        monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "0")
        off = g2.expand_2hop(["Art. 6"], max_hop2=5)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "1")
        on = g2.expand_2hop(["Art. 6"], max_hop2=5)

        assert off.hop2_articles == (), "pre-fix: hub seed crowd-out → empty hop2"
        assert on.hop2_articles, "post-fix: hub seed must surface hop2"
        assert len(on.hop2_articles) > len(off.hop2_articles)
        assert len(on.hop2_articles) <= 5  # still bounded by max_hop2
        for ref in on.hop2_articles:
            assert ref in ARTICLE_EXISTENCE  # existence-gated
            assert ref != "Art. 6"  # excludes the seed
            assert ref not in on.hop1_articles  # hop2-only

    def test_non_hub_seed_same_hop2_content_on_off(self, monkeypatch):
        # A low-degree seed never truncated under either cap → the candidate
        # SET is preserved (the fix doesn't add/drop refs for non-hubs); only
        # the ORDER improves (numeric, not lexicographic-string).
        self._setup(monkeypatch)
        from app.engines import graph_expand_2hop as g2

        monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "0")
        off = g2.expand_2hop(["Art. 99"], max_hop2=5)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "1")
        on = g2.expand_2hop(["Art. 99"], max_hop2=5)

        assert set(on.hop2_articles) == set(off.hop2_articles)

    def test_ordering_demotes_amendment_articles(self, monkeypatch):
        # The relevance proxy surfaces substantive articles (Arts. 7-15
        # obligation chain), NOT the lexicographically-first amendment /
        # final-provision articles (Art. 100-113) the string sort puts first.
        self._setup(monkeypatch)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "1")
        from app.engines import graph_expand_2hop as g2

        exp = g2.expand_2hop(["Art. 6"], max_hop2=5)
        nums = [
            int(r[len("Art. ") :])
            for r in exp.hop2_articles
            if r.startswith("Art. ")
        ]
        assert nums, "expected article hop2 refs for the Art. 6 hub"
        assert all(n < 100 for n in nums), (
            f"amendment/final-provision article leaked into hop2: "
            f"{list(exp.hop2_articles)}"
        )

    def test_fuse_appends_hub_hop2(self, monkeypatch):
        self._setup(monkeypatch)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "1")
        from app.engines import graph_expand_2hop as g2

        exp = g2.expand_2hop(["Art. 6"], max_hop2=5)
        fused = g2.fuse_with_kb_xrefs(["Art. 6"], exp, budget=10)
        assert fused[0] == "Art. 6"  # BM25 winner preserved at the head
        assert len(fused) > 1  # the now-surfaced hop2 refs are appended


class TestCacheKey:
    def test_full_cap_flag_in_engine_cache_key(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key

        base = _engine_cache_key("q", None)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "0")
        assert _engine_cache_key("q", None) != base


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
