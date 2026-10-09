from __future__ import annotations

import json

import pytest

from evals.official import judge


def _response():
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"verdicts": []}'}}]}
            ).encode()

    return Response()


def test_sonnet_55_wrapper_request_omits_temperature_and_keeps_cf_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(judge, "MODEL", judge.MODEL)
    monkeypatch.setattr(judge, "URL", judge.URL)
    monkeypatch.setattr(judge, "_HDRS", judge._HDRS)
    monkeypatch.setenv("R388_WRAPPER_URL", "https://wrapper.test/v1/chat/completions")
    monkeypatch.setenv("OPENAI_API_KEY", "wrapper-key")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    # R432 -- the Access token rides only to the pinned host.
    monkeypatch.setenv("CF_ACCESS_HOSTNAME", "wrapper.test")
    judge.configure_judge(provider="wrapper", model="claude-sonnet-5-5")

    calls: list[dict[str, object]] = []

    def open_request(request, timeout=None):
        calls.append(
            {
                "url": request.full_url,
                "body": json.loads(request.data),
                "headers": {key.lower(): value for key, value in request.header_items()},
            }
        )
        return _response()

    monkeypatch.setattr(judge.urllib.request, "urlopen", open_request)
    assert judge._call("probe", retries=1) == '{"verdicts": []}'

    assert calls[0]["url"] == "https://wrapper.test/v1/chat/completions"
    assert calls[0]["body"]["model"] == "claude-sonnet-5-5"
    assert "temperature" not in calls[0]["body"]
    assert calls[0]["headers"]["cf-access-client-id"] == "cf-id"
    assert calls[0]["headers"]["cf-access-client-secret"] == "cf-secret"
    assert "t=provider-default" in judge.judge_identity()


def test_access_token_is_not_sent_to_an_unpinned_judge_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(judge, "MODEL", judge.MODEL)
    monkeypatch.setattr(judge, "URL", judge.URL)
    monkeypatch.setattr(judge, "_HDRS", judge._HDRS)
    monkeypatch.setenv("R388_WRAPPER_URL", "https://third-party.test/v1/chat/completions")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    monkeypatch.delenv("CF_ACCESS_HOSTNAME", raising=False)
    judge.configure_judge(provider="wrapper", model="claude-sonnet-5")

    sent: list[dict[str, str]] = []

    def open_request(request, timeout=None):
        sent.append({key.lower(): value for key, value in request.header_items()})
        return _response()

    monkeypatch.setattr(judge.urllib.request, "urlopen", open_request)
    assert judge._call("probe", retries=1) == '{"verdicts": []}'
    assert not {h for h in sent[0] if h.startswith("cf-access")}, sent[0]


@pytest.mark.parametrize("provider", ["bedrock", "openrouter"])
def test_sonnet_55_rejected_for_other_judge_providers(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    monkeypatch.setattr(judge, "MODEL", judge.MODEL)
    # R463 - ``configure_judge`` writes R388_JUDGE_PROVIDER and R388_JUDGE_MODEL
    # into os.environ BEFORE it raises, so the rejected model used to stay in the
    # process env (and in the judge identity, which is read from there) for every
    # later test module: a leak that makes the suite order-dependent. Registering
    # the two names with monkeypatch makes teardown restore the pre-call state.
    monkeypatch.delenv("R388_JUDGE_PROVIDER", raising=False)
    monkeypatch.delenv("R388_JUDGE_MODEL", raising=False)
    with pytest.raises(ValueError, match="wrapper/tunnel"):
        judge.configure_judge(provider=provider, model="claude-sonnet-5-5")


def test_other_judge_models_keep_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judge, "MODEL", judge.MODEL)
    monkeypatch.setattr(judge, "URL", judge.URL)
    monkeypatch.setattr(judge, "_HDRS", judge._HDRS)
    monkeypatch.setenv("R388_WRAPPER_URL", "https://wrapper.test/v1/chat/completions")
    monkeypatch.setenv("OPENAI_API_KEY", "wrapper-key")
    monkeypatch.setattr(judge, "TEMPERATURE", 0.1)
    judge.configure_judge(provider="wrapper", model="claude-sonnet-5")

    calls: list[dict[str, object]] = []

    def open_request(request, timeout=None):
        calls.append(json.loads(request.data))
        return _response()

    monkeypatch.setattr(judge.urllib.request, "urlopen", open_request)
    assert judge._call("probe", retries=1) == '{"verdicts": []}'
    assert calls[0]["temperature"] == 0.1
    assert "t=0.1" in judge.judge_identity()
