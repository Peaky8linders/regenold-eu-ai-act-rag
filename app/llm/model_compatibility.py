"""Small provider-compatibility checks for model-specific request constraints."""
from __future__ import annotations

import re

# Claude Sonnet 5.5 in every spelling a transport uses: the first-party id
# (``claude-sonnet-5-5``), the dotted form namespaced catalogues use
# (``claude-sonnet-5.5``), dated / versioned snapshots (``-20260901``, ``-v1:0``,
# ``@20260901``) and variant suffixes (``:thinking``). The trailing class is what
# keeps a later release (``claude-sonnet-5-50``) from matching.
_SONNET_5_5 = re.compile(r"^claude-sonnet-5[-.]5(?:$|[-:@])")

# Bedrock inference-profile geography (``eu.``, ``us.``, ``global.``, ``apac.``)
# and the vendor segment route a request; they do not identify the model.
_BEDROCK_PREFIX = re.compile(r"^(?:[a-z]+\.)?anthropic\.")


def rejects_sampling_parameters(model_id: str | None) -> bool:
    """Return whether a model rejects explicit temperature/top-p/top-k values.

    A deliberately NARROW allow-list keyed on the model id, not a family
    prefix: a match removes ``temperature`` from the request, so every id added
    here changes a payload.

    Evidence, and its limits. Anthropic's API reference lists non-default
    ``temperature`` / ``top_p`` / ``top_k`` as an HTTP 400 on Claude Sonnet 5.5,
    which includes ``temperature=0``. This repository has never recorded that
    400, and it cannot show it on the Claude Max wrapper: the wrapper does not
    forward ``temperature`` at all, it renders it as a best-effort system-prompt
    hint, so over that route omitting the field only drops the hint. Bedrock and
    OpenRouter behaviour for this id is unmeasured here.

    The same reference documents removed sampling parameters on
    ``claude-opus-5-5``, ``claude-opus-5``, ``claude-sonnet-5`` and
    ``claude-opus-4-8``, and those are NOT listed: they ship today with
    ``temperature`` on the wire, over the wrapper, without error, and dropping it
    would also drop the wrapper's focus hint from the shipped Stage-2 prompt,
    which is an answer-affecting change that needs the gold gate.

    Accepts the bare id and provider-namespaced forms (``anthropic/...``, Bedrock
    ``eu.anthropic....-v1:0``, an inference-profile ARN).
    """
    name = (model_id or "").strip().lower().rsplit("/", 1)[-1]
    name = _BEDROCK_PREFIX.sub("", name, count=1)
    return _SONNET_5_5.match(name) is not None
