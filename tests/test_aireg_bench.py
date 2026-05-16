"""Tests for the AIReg-Bench secondary benchmark.

Covers:
    * Verdict bucketing (1-5 score → label) — every score + edge cases
    * Verdict extraction from free-form answers — keyword, modality, numeric
    * Per-row scoring (exact + soft) and confusion-matrix aggregation
    * Row normalisation: HF-shape wide rows → flat annotation records
    * Idempotent fetch: re-reading the cache returns identical SHA
    * Wire-contract shape: runner posts ``[{role,content}]`` payloads
    * CLI parsing: ``--label``, ``--limit``, ``--refresh`` accepted

Every test runs offline — ``urllib.request.urlopen`` is stubbed for
the fetch path so CI machines without network connectivity can still
run the suite.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from evals.bench import (
    aireg_dataset,
    aireg_metrics,
    aireg_runner,
)


# ── 1. Verdict bucketing ─────────────────────────────────────────────────


class TestBucketComplianceScore:
    """1-5 score → verdict label."""

    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (5, aireg_dataset.VERDICT_COMPLIANT),
            (4, aireg_dataset.VERDICT_COMPLIANT),
            (4.5, aireg_dataset.VERDICT_COMPLIANT),
            (3, aireg_dataset.VERDICT_BORDERLINE),
            (3.0, aireg_dataset.VERDICT_BORDERLINE),
            (3.5, aireg_dataset.VERDICT_BORDERLINE),
            (2, aireg_dataset.VERDICT_NON_COMPLIANT),
            (1, aireg_dataset.VERDICT_NON_COMPLIANT),
            (1.5, aireg_dataset.VERDICT_NON_COMPLIANT),
        ],
    )
    def test_in_range(self, score: float, expected: str) -> None:
        assert aireg_dataset.bucket_compliance_score(score) == expected

    def test_none_is_unknown(self) -> None:
        assert (
            aireg_dataset.bucket_compliance_score(None)
            == aireg_dataset.VERDICT_UNKNOWN
        )

    def test_non_numeric_is_unknown(self) -> None:
        assert (
            aireg_dataset.bucket_compliance_score("nan")  # type: ignore[arg-type]
            == aireg_dataset.VERDICT_UNKNOWN
        )

    def test_zero_is_unknown(self) -> None:
        # Outside 1-5 range — defensive fallback.
        assert (
            aireg_dataset.bucket_compliance_score(0)
            == aireg_dataset.VERDICT_UNKNOWN
        )

    def test_negative_is_unknown(self) -> None:
        assert (
            aireg_dataset.bucket_compliance_score(-1)
            == aireg_dataset.VERDICT_UNKNOWN
        )


class TestMedianHelper:
    def test_odd_count(self) -> None:
        assert aireg_dataset.median([1, 3, 5]) == 3.0

    def test_even_count(self) -> None:
        assert aireg_dataset.median([1, 2, 3, 4]) == 2.5

    def test_empty(self) -> None:
        assert aireg_dataset.median([]) is None

    def test_filters_none(self) -> None:
        assert aireg_dataset.median([None, 2, 4]) == 3.0  # type: ignore[list-item]


# ── 2. Verdict extraction from free-form answers ─────────────────────────


class TestExtractPredictedVerdict:
    """Regex-driven verdict detection from engine answers."""

    def test_explicit_non_compliant(self) -> None:
        text = (
            "This AI system is non-compliant with Article 9 — the risk "
            "management process is not continuous."
        )
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_NON_COMPLIANT
        )

    def test_explicit_compliant(self) -> None:
        text = "The technical documentation complies with Article 12."
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_COMPLIANT
        )

    def test_borderline_keyword(self) -> None:
        text = "Borderline — Article 15 obligations may be only partially met."
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_BORDERLINE
        )

    def test_does_not_comply_phrase(self) -> None:
        text = "The system does not comply with Art. 14 oversight rules."
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_NON_COMPLIANT
        )

    def test_modality_may_comply(self) -> None:
        text = "Under Article 10, this approach might comply with data quality."
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_BORDERLINE
        )

    def test_numeric_score_fallback(self) -> None:
        text = "Compliance score: 5 — full coverage of Article 9."
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_COMPLIANT
        )

    def test_no_signal_is_unknown(self) -> None:
        text = "Article 9 covers risk management."
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_UNKNOWN
        )

    def test_empty_input(self) -> None:
        assert (
            aireg_metrics.extract_predicted_verdict("")
            == aireg_dataset.VERDICT_UNKNOWN
        )

    def test_non_string_input(self) -> None:
        assert (
            aireg_metrics.extract_predicted_verdict(None)  # type: ignore[arg-type]
            == aireg_dataset.VERDICT_UNKNOWN
        )

    def test_negation_wins_over_positive(self) -> None:
        """``does not comply`` should beat the bare ``comply`` hit."""
        text = "Although it appears to comply, the system does not comply with Art. 9."
        assert (
            aireg_metrics.extract_predicted_verdict(text)
            == aireg_dataset.VERDICT_NON_COMPLIANT
        )


# ── 3. Verdict-match scoring + aggregation ───────────────────────────────


class TestVerdictMatch:
    def test_exact_match_compliant(self) -> None:
        assert (
            aireg_metrics.verdict_match(
                aireg_dataset.VERDICT_COMPLIANT,
                aireg_dataset.VERDICT_COMPLIANT,
            )
            == 1.0
        )

    def test_mismatch_compliant_vs_non(self) -> None:
        assert (
            aireg_metrics.verdict_match(
                aireg_dataset.VERDICT_COMPLIANT,
                aireg_dataset.VERDICT_NON_COMPLIANT,
            )
            == 0.0
        )

    def test_unknown_gold_zero(self) -> None:
        assert (
            aireg_metrics.verdict_match(
                aireg_dataset.VERDICT_COMPLIANT,
                aireg_dataset.VERDICT_UNKNOWN,
            )
            == 0.0
        )

    def test_unknown_pred_zero(self) -> None:
        assert (
            aireg_metrics.verdict_match(
                aireg_dataset.VERDICT_UNKNOWN,
                aireg_dataset.VERDICT_COMPLIANT,
            )
            == 0.0
        )


class TestVerdictSoftMatch:
    def test_exact_one(self) -> None:
        assert (
            aireg_metrics.verdict_soft_match(
                aireg_dataset.VERDICT_COMPLIANT,
                aireg_dataset.VERDICT_COMPLIANT,
            )
            == 1.0
        )

    def test_borderline_to_compliant_half(self) -> None:
        assert (
            aireg_metrics.verdict_soft_match(
                aireg_dataset.VERDICT_BORDERLINE,
                aireg_dataset.VERDICT_COMPLIANT,
            )
            == 0.5
        )

    def test_compliant_to_non_compliant_zero(self) -> None:
        assert (
            aireg_metrics.verdict_soft_match(
                aireg_dataset.VERDICT_COMPLIANT,
                aireg_dataset.VERDICT_NON_COMPLIANT,
            )
            == 0.0
        )

    def test_unknown_zero(self) -> None:
        assert (
            aireg_metrics.verdict_soft_match(
                aireg_dataset.VERDICT_UNKNOWN,
                aireg_dataset.VERDICT_COMPLIANT,
            )
            == 0.0
        )


class TestVerdictAggregation:
    def test_zero_rows_returns_zeroes(self) -> None:
        rep = aireg_metrics.aggregate_verdicts([])
        assert rep.n == 0
        assert rep.exact_match == 0.0
        assert rep.coverage == 0.0

    def test_perfect_run(self) -> None:
        rows = [
            {
                "pred_verdict": aireg_dataset.VERDICT_COMPLIANT,
                "gold_verdict": aireg_dataset.VERDICT_COMPLIANT,
            },
            {
                "pred_verdict": aireg_dataset.VERDICT_NON_COMPLIANT,
                "gold_verdict": aireg_dataset.VERDICT_NON_COMPLIANT,
            },
        ]
        rep = aireg_metrics.aggregate_verdicts(rows)
        assert rep.n == 2
        assert rep.exact_match == 1.0
        assert rep.coverage == 1.0
        d = rep.to_dict()
        assert d["confusion"][aireg_dataset.VERDICT_COMPLIANT][
            aireg_dataset.VERDICT_COMPLIANT
        ] == 1
        assert d["confusion"][aireg_dataset.VERDICT_NON_COMPLIANT][
            aireg_dataset.VERDICT_NON_COMPLIANT
        ] == 1

    def test_coverage_drops_unknown_gold(self) -> None:
        rows = [
            {
                "pred_verdict": aireg_dataset.VERDICT_COMPLIANT,
                "gold_verdict": aireg_dataset.VERDICT_COMPLIANT,
            },
            {
                "pred_verdict": aireg_dataset.VERDICT_COMPLIANT,
                "gold_verdict": aireg_dataset.VERDICT_UNKNOWN,
            },
        ]
        rep = aireg_metrics.aggregate_verdicts(rows)
        assert rep.n == 2
        assert rep.coverage == 0.5
        # exact_match is fraction of *scorable* rows, not all rows
        assert rep.exact_match == 1.0


class TestGoldVerdictFromAnnotations:
    def test_all_compliant(self) -> None:
        assert (
            aireg_metrics.gold_verdict_from_annotations([5, 4, 5])
            == aireg_dataset.VERDICT_COMPLIANT
        )

    def test_mixed_median_borderline(self) -> None:
        # median of [1, 3, 5] = 3 → borderline
        assert (
            aireg_metrics.gold_verdict_from_annotations([1, 3, 5])
            == aireg_dataset.VERDICT_BORDERLINE
        )

    def test_empty_unknown(self) -> None:
        assert (
            aireg_metrics.gold_verdict_from_annotations([])
            == aireg_dataset.VERDICT_UNKNOWN
        )

    def test_filters_nones(self) -> None:
        assert (
            aireg_metrics.gold_verdict_from_annotations([None, 5, 5])  # type: ignore[list-item]
            == aireg_dataset.VERDICT_COMPLIANT
        )


# ── 4. Row normalisation ─────────────────────────────────────────────────


_SAMPLE_HF_ROW = {
    "row_idx": 1,
    "row": {
        "Unnamed: 0": "Art 9 / Scenario A",
        "Use 1": "2",
        "Unnamed: 2": "Low compliance: the system does not comply with Art 9.",
        "Unnamed: 3": "nan",
        "Unnamed: 4": "3",
        "Unnamed: 5": "Moderately plausible.",
        "Use 2": "1",
        "Unnamed: 7": "Very low — fails risk management.",
        "Unnamed: 8": "nan",
        "Unnamed: 9": "4",
        "Unnamed: 10": "Highly plausible.",
        "Use 3": "5",
        "Unnamed: 12": "Fully compliant.",
        "Unnamed: 13": "nan",
        "Unnamed: 14": "5",
        "Unnamed: 15": "Very plausible.",
    },
}

_HEADER_ROW = {
    "row_idx": 0,
    "row": {"Unnamed: 0": "nan", "Use 1": "Compliance [1-5]"},
}


class TestRowNormalisation:
    def test_skips_header_row(self) -> None:
        out = aireg_dataset._normalize_rows([_HEADER_ROW])
        assert out == []

    def test_explodes_uses(self) -> None:
        out = aireg_dataset._normalize_rows([_SAMPLE_HF_ROW])
        assert len(out) == 3  # Uses 1, 2, 3 populated; 4-8 missing
        ids = {r["document_id"] for r in out}
        assert ids == {
            "art9_scenarioA_use1",
            "art9_scenarioA_use2",
            "art9_scenarioA_use3",
        }

    def test_score_typing(self) -> None:
        out = aireg_dataset._normalize_rows([_SAMPLE_HF_ROW])
        scores = {r["use_index"]: r["compliance_score"] for r in out}
        assert scores == {1: 2, 2: 1, 3: 5}

    def test_intended_use_attached(self) -> None:
        out = aireg_dataset._normalize_rows([_SAMPLE_HF_ROW])
        first = next(r for r in out if r["use_index"] == 1)
        # Use 1 = biometric ID per intended_uses.txt
        assert "biometric" in first["intended_use"].lower()

    def test_article_and_scenario_parsed(self) -> None:
        out = aireg_dataset._normalize_rows([_SAMPLE_HF_ROW])
        for r in out:
            assert r["article_id"] == 9
            assert r["scenario_id"] == "A"


# ── 5. Dataset fetch + idempotence + SHA pin ─────────────────────────────


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


def _make_urlopen_stub(
    rows_by_offset: dict[int, list[dict[str, Any]]],
    parquet_bytes: bytes = b"",
) -> Any:
    """Build a urlopen replacement that maps offset→rows + serves the parquet."""

    def stub(req: Any, timeout: float | None = None) -> _FakeResponse:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "datasets-server.huggingface.co/rows" in url:
            # Parse offset out of the query string.
            offset = 0
            length = 5
            for part in url.split("?", 1)[-1].split("&"):
                if part.startswith("offset="):
                    offset = int(part.split("=", 1)[1])
                elif part.startswith("length="):
                    length = int(part.split("=", 1)[1])
            rows = rows_by_offset.get(offset, [])[:length]
            payload = {"rows": rows}
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        if "human_annotations.parquet" in url:
            return _FakeResponse(parquet_bytes)
        return _FakeResponse(b"{}")

    return stub


def test_fetch_blocked_when_server_500s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If every urlopen call 500s, ``_FETCH_BLOCKED`` should flip True."""
    monkeypatch.setattr(
        aireg_dataset, "AIREG_LOCAL_CACHE", tmp_path / ".aireg-bench-cache"
    )
    monkeypatch.setattr(
        aireg_dataset,
        "_ANNOTATIONS_JSON",
        tmp_path / ".aireg-bench-cache" / "annotations.json",
    )
    monkeypatch.setattr(
        aireg_dataset, "_DOCS_DIR", tmp_path / ".aireg-bench-cache" / "documentation"
    )
    # Reset the module-level flag so this test is hermetic.
    monkeypatch.setattr(aireg_dataset, "_FETCH_BLOCKED", False)
    import urllib.error

    def always_500(*args: Any, **kwargs: Any) -> _FakeResponse:
        raise urllib.error.HTTPError(
            url="x", code=500, msg="Internal", hdrs=None, fp=None  # type: ignore[arg-type]
        )

    monkeypatch.setattr("urllib.request.urlopen", always_500)
    payload = aireg_dataset.fetch_aireg_bench(refresh=True, max_offset=5)
    assert payload["fetch_blocked"] is True
    assert payload["annotations"] == []
    assert aireg_dataset.is_fetch_blocked() is True


def test_fetch_idempotent_on_cache_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling fetch twice should hit the cache the second time and
    return byte-identical annotations.json (SHA stable)."""
    cache_dir = tmp_path / ".aireg-bench-cache"
    monkeypatch.setattr(aireg_dataset, "AIREG_LOCAL_CACHE", cache_dir)
    monkeypatch.setattr(
        aireg_dataset, "_ANNOTATIONS_JSON", cache_dir / "annotations.json"
    )
    monkeypatch.setattr(
        aireg_dataset, "_DOCS_DIR", cache_dir / "documentation"
    )
    monkeypatch.setattr(aireg_dataset, "_FETCH_BLOCKED", False)
    rows = {0: [_SAMPLE_HF_ROW], 5: [], 10: []}
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen_stub(rows)
    )

    first = aireg_dataset.fetch_aireg_bench(refresh=True, max_offset=15)
    sha1 = aireg_dataset.aireg_dataset_sha256()
    assert sha1 != ""
    assert first["n_rows"] >= 1

    # Second call should use cache — disable network entirely.
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Network was hit on cache-hit path!")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    second = aireg_dataset.fetch_aireg_bench(refresh=False, max_offset=15)
    sha2 = aireg_dataset.aireg_dataset_sha256()
    assert sha1 == sha2
    assert second["n_rows"] == first["n_rows"]


def test_sha_pin_constant_format() -> None:
    """The pinned SHA must be a 64-char lowercase hex string (sha256)."""
    sha = aireg_dataset.AIREG_PARQUET_SHA256
    assert isinstance(sha, str)
    assert len(sha) == 64
    assert all(c in "0123456789abcdef" for c in sha)


def test_dataset_fingerprint_shape() -> None:
    fp = aireg_dataset.dataset_fingerprint()
    assert fp["hf_id"] == "camlsys/AIReg-Bench"
    assert fp["revision"] == aireg_dataset.AIREG_REVISION
    assert fp["parquet_sha256_pinned"] == aireg_dataset.AIREG_PARQUET_SHA256
    assert "fetch_blocked" in fp
    assert "annotations_json_sha256" in fp


# ── 6. Runner wire-contract + CLI ────────────────────────────────────────


class TestRunnerWireContract:
    """The runner must post the exact wire shape the davidath runner posts."""

    def test_build_question_prompt_only(self) -> None:
        q = aireg_runner._build_question(
            document_id="art9_scenarioA_use1",
            article_id=9,
            intended_use="Biometric identification",
            document_text=None,
        )
        assert "Article 9" in q
        assert "biometric identification" in q.lower()

    def test_build_question_doc_grounded(self) -> None:
        q = aireg_runner._build_question(
            document_id="art9_scenarioA_use1",
            article_id=9,
            intended_use="Biometric identification",
            document_text="The system uses face matching with N=50K examples.",
        )
        assert "Article 9" in q
        assert "face matching" in q.lower()

    def test_ask_posts_messages_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the wire payload is ``[{role:"user", content:str}]``."""
        captured: dict[str, Any] = {}

        class _FakeClient:
            def post(self, path: str, json: Any = None) -> Any:  # noqa: A002
                captured["path"] = path
                captured["json"] = json

                class _Resp:
                    status_code = 200

                    def json(self) -> dict[str, Any]:
                        return {
                            "answer": "complies with Article 9.",
                            "references": ["Article 9"],
                            "reasoning": None,
                        }

                return _Resp()

        body, latency, status = aireg_runner._ask(
            _FakeClient(), "Test question?"
        )
        assert captured["path"] == "/api/v1/regenold/eu-ai-act/ask"
        assert isinstance(captured["json"], list)
        assert captured["json"] == [
            {"role": "user", "content": "Test question?"}
        ]
        assert status == 200
        assert body["answer"].startswith("complies")
        assert latency >= 0.0


class TestRunnerGrouping:
    def test_group_annotations_collapses_per_doc(self) -> None:
        annotations = [
            {
                "document_id": "art9_scenarioA_use1",
                "article_id": 9,
                "scenario_id": "A",
                "use_index": 1,
                "intended_use": "Biometric ID",
                "compliance_score": 2,
            },
            {
                "document_id": "art9_scenarioA_use1",
                "article_id": 9,
                "scenario_id": "A",
                "use_index": 1,
                "intended_use": "Biometric ID",
                "compliance_score": 1,
            },
            {
                "document_id": "art9_scenarioA_use1",
                "article_id": 9,
                "scenario_id": "A",
                "use_index": 1,
                "intended_use": "Biometric ID",
                "compliance_score": 1,
            },
        ]
        items = aireg_runner._group_annotations(annotations)
        assert len(items) == 1
        item = items[0]
        assert item["n_annotators"] == 3
        assert item["gold_verdict"] == aireg_dataset.VERDICT_NON_COMPLIANT
        assert item["median_score"] == 1.0


class TestRunnerCLI:
    def test_cli_parses_label_and_limit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``main`` must accept ``--label`` and ``--limit`` without erroring."""
        called: dict[str, Any] = {}

        def fake_run(**kwargs: Any) -> dict[str, Any]:
            called.update(kwargs)
            return {
                "label": kwargs.get("label", "?"),
                "n_items": 0,
                "summary": {},
                "items": [],
                "dataset_fingerprint": {},
                "fetch_blocked": False,
                "sidecar_path": "/tmp/x.json",
            }

        monkeypatch.setattr(aireg_runner, "run", fake_run)
        rc = aireg_runner.main(
            ["--label", "smoke", "--limit", "3", "--refresh"]
        )
        assert rc == 0
        assert called["label"] == "smoke"
        assert called["limit"] == 3
        assert called["refresh"] is True

    def test_cli_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: dict[str, Any] = {}

        def fake_run(**kwargs: Any) -> dict[str, Any]:
            called.update(kwargs)
            return {
                "label": "adhoc",
                "n_items": 0,
                "summary": {},
                "items": [],
                "dataset_fingerprint": {},
                "fetch_blocked": False,
                "sidecar_path": "/tmp/x.json",
            }

        monkeypatch.setattr(aireg_runner, "run", fake_run)
        aireg_runner.main([])
        assert called["label"] == "adhoc"
        assert called["limit"] is None
        assert called["refresh"] is False


class TestFormatSummary:
    def test_empty_summary_renders(self) -> None:
        out = aireg_runner._format_summary(
            {
                "label": "x",
                "summary": {},
                "n_items": 0,
                "fetch_blocked": False,
                "dataset_fingerprint": {},
                "n_doc_grounded": 0,
            }
        )
        assert "AIReg-Bench" in out
        assert "no rows" in out

    def test_full_summary_renders(self) -> None:
        out = aireg_runner._format_summary(
            {
                "label": "x",
                "summary": {
                    "n": 1,
                    "ans_correctness_loose": 0.5,
                    "verdict_exact": 0.5,
                    "verdict_soft": 0.75,
                    "verdict_coverage": 1.0,
                    "confusion": {
                        aireg_dataset.VERDICT_COMPLIANT: {
                            p: 0
                            for p in (
                                *aireg_dataset.VERDICT_SET,
                                aireg_dataset.VERDICT_UNKNOWN,
                            )
                        }
                    },
                },
                "n_items": 1,
                "n_doc_grounded": 0,
                "fetch_blocked": False,
                "dataset_fingerprint": {},
                "sidecar_path": "/tmp/x.json",
            }
        )
        assert "Verdict exact-match" in out
        assert "Verdict soft-match" in out
