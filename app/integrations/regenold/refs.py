"""Centralised EU AI Act citation-form converter.

A single source of truth for translating between the three citation forms
the codebase juggles:

* **Internal canonical** — ``Art. 13`` / ``Art. 13(2)(a)`` / ``Annex IV(1)``.
  Used by the KB / xref graph / BM25 index keys.
* **User-facing** — ``Article 13`` / ``Article 13.2.a`` / ``Annex IV.1``.
  The Regenold wire form (Arabic for articles, Roman uppercase for
  annexes, dot-separated sub-points, NEVER parens). Enforced by
  ``models._ARTICLE_OUTPUT_RE`` / ``_ANNEX_OUTPUT_RE``.
* **Sub-point composition** — given parent ``Art. 5`` + sub ``1(a)``,
  yield ``Art. 5(1)(a)`` (internal) or ``Article 5.1.a`` (user-facing).

Before this module the codebase shipped 7+ separate inline regex
conversions (citation_guard / graphrag_expand / graph_aware_retrieval /
graph_expand_2hop / prohibited_gatekeeper / bench metrics /
regenold.runner). R43 had to update SIX of them in one go to support
letter suffixes — proof the duplication will bite again. This module
centralises so future shape extensions (e.g. ``Article 5.1.a.iii``) only
touch one file.

Hard rules (from CLAUDE.md):
    Never emit ``Art. 13``, ``Annex 3``, ``Article 13(1)``, ``Annex III(2)``,
    or ``Article III`` on the wire — :func:`to_user_facing` and
    :func:`parse` enforce this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "RefSpec",
    "InvalidRefError",
    "to_user_facing",
    "to_internal",
    "as_sub_point",
    "normalise",
    "parse",
]


class InvalidRefError(ValueError):
    """Raised by :func:`parse` when a reference doesn't match either shape."""


@dataclass(frozen=True)
class RefSpec:
    """Parsed representation of an EU AI Act citation.

    Exactly one of :attr:`article_number` / :attr:`annex_roman` is set;
    the other is ``None``. :attr:`subpoints` is the dot/paren chain in
    left-to-right order — e.g. ``["1", "a"]`` for ``Art. 5(1)(a)``.
    """

    article_number: int | None = None
    annex_roman: str | None = None
    subpoints: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_annex(self) -> bool:
        return self.annex_roman is not None


# ── Module-level compiled regexes ────────────────────────────────────────
#
# Accept either prefix (``Art.`` / ``Article``) on input; emit the strict
# form (``Art. N`` internal / ``Article N`` wire) on output.

_PREFIX_ARTICLE = r"(?:Art\.|Article)"
_PREFIX_ANNEX = r"Annex"
_ROMAN = r"[IVXLCDM]+"

# Match an article ref in either internal or user-facing form, capturing
# the bare number and the tail of sub-point tokens (in either ``(a)(b)``
# or ``.a.b`` form, or mixed).
_ARTICLE_FULL_RE = re.compile(
    r"^\s*" + _PREFIX_ARTICLE + r"\s+(?P<num>\d{1,3})(?P<tail>(?:\.[A-Za-z0-9]+|\([A-Za-z0-9]+\))*)\s*$",
    re.IGNORECASE,
)
_ANNEX_FULL_RE = re.compile(
    r"^\s*" + _PREFIX_ANNEX + r"\s+(?P<rom>" + _ROMAN + r")(?P<tail>(?:\.[A-Za-z0-9]+|\([A-Za-z0-9]+\))*)\s*$",
    re.IGNORECASE,
)
_SUBPOINT_TOKEN_RE = re.compile(r"\.([A-Za-z0-9]+)|\(([A-Za-z0-9]+)\)")

# Strict wire-shape regexes — kept here as the single source of truth.
# ``app/integrations/regenold/models.py`` references these (or its own
# copy until R47 migrates it) for the final output gate.
USER_FACING_ARTICLE_RE = re.compile(r"^Article \d+(?:\.[A-Za-z0-9]+)*$")
USER_FACING_ANNEX_RE = re.compile(r"^Annex [IVXLCDM]+(?:\.[A-Za-z0-9]+)*$")

# Strict internal-shape regexes — for parsing canonical KB output.
INTERNAL_ARTICLE_RE = re.compile(r"^Art\. \d+(?:\([A-Za-z0-9]+\))*$")
INTERNAL_ANNEX_RE = re.compile(r"^Annex [IVXLCDM]+(?:\([A-Za-z0-9]+\))*$")


def _extract_subpoints(tail: str) -> tuple[str, ...]:
    """Pull subpoint tokens from a tail like ``(1)(a)``, ``.1.a``, or mixed.

    Returns the tokens in left-to-right order. Returns ``()`` for an
    empty tail.
    """
    if not tail:
        return ()
    tokens: list[str] = []
    for dot_tok, paren_tok in _SUBPOINT_TOKEN_RE.findall(tail):
        raw = (dot_tok or paren_tok).strip()
        if raw:
            tokens.append(raw)
    return tuple(tokens)


def parse(ref: str) -> RefSpec:
    """Parse a reference (any of the three forms) into a :class:`RefSpec`.

    Accepts:
        * ``Art. 13`` / ``Article 13`` (bare base)
        * ``Art. 13(2)(a)`` / ``Article 13.2.a`` (with sub-points)
        * ``Annex IV`` / ``Annex IV(1)`` / ``Annex IV.1`` (annex variants)
        * Mixed-case Roman (``annex iv`` → uppercased)

    Rejects (raises :class:`InvalidRefError`):
        * Roman article numbers (``Article III`` — disallowed per CLAUDE.md)
        * Empty / whitespace-only input
        * Unparseable garbage
    """
    if ref is None:
        raise InvalidRefError("ref is None")
    raw = ref.strip()
    if not raw:
        raise InvalidRefError("empty ref")

    m = _ARTICLE_FULL_RE.match(raw)
    if m:
        return RefSpec(
            article_number=int(m.group("num")),
            subpoints=_extract_subpoints(m.group("tail")),
        )

    m = _ANNEX_FULL_RE.match(raw)
    if m:
        return RefSpec(
            annex_roman=m.group("rom").upper(),
            subpoints=_extract_subpoints(m.group("tail")),
        )

    raise InvalidRefError(f"unparseable ref: {ref!r}")


def to_user_facing(internal: str) -> str:
    """``"Art. 13(2)(a)"`` → ``"Article 13.2.a"``; ``"Annex IV(1)"`` → ``"Annex IV.1"``.

    Accepts either input prefix (idempotent on already-user-facing form).
    Raises :class:`InvalidRefError` on garbage.
    """
    spec = parse(internal)
    return _format_user_facing(spec)


def to_internal(user_facing: str) -> str:
    """Inverse of :func:`to_user_facing`.

    ``"Article 13.2.a"`` → ``"Art. 13(2)(a)"``; ``"Annex IV.1"`` →
    ``"Annex IV(1)"``. Accepts either input prefix (idempotent on
    already-internal form).
    """
    spec = parse(user_facing)
    return _format_internal(spec)


def as_sub_point(parent: str, sub: str) -> str:
    """Compose a child ref from a parent ref + a sub-point fragment.

    ``("Art. 5", "1(a)")`` → ``"Art. 5(1)(a)"``;
    ``("Article 5", "1.a")`` → ``"Art. 5(1)(a)"`` (output is always
    internal canonical — caller applies :func:`to_user_facing` for the
    wire). ``sub`` may carry dot / paren / mixed form; tokens are
    extracted by the same logic as :func:`parse`.
    """
    parent_spec = parse(parent)
    sub_tokens = _extract_subpoints(_normalise_sub_fragment(sub))
    if not sub_tokens:
        raise InvalidRefError(f"no sub-point tokens in {sub!r}")
    combined = RefSpec(
        article_number=parent_spec.article_number,
        annex_roman=parent_spec.annex_roman,
        subpoints=parent_spec.subpoints + sub_tokens,
    )
    return _format_internal(combined)


def normalise(ref: str) -> str:
    """Collapse whitespace, casefold annex Roman, return canonical user-facing form.

    Idempotent: ``normalise(normalise(x)) == normalise(x)``. Used as the
    "one true form" for set membership checks across rounds where some
    sites emit ``ANNEX iv.1`` and others ``Annex IV.1``.
    """
    spec = parse(ref)
    return _format_user_facing(spec)


# ── Internal formatters ──────────────────────────────────────────────────


def _format_user_facing(spec: RefSpec) -> str:
    """Render a :class:`RefSpec` in wire form, validating the result."""
    if spec.is_annex:
        head = f"Annex {spec.annex_roman}"
    else:
        head = f"Article {spec.article_number}"
    tail = "".join(f".{t}" for t in spec.subpoints)
    out = head + tail
    # Defence-in-depth: the strict wire regex MUST match. If it doesn't,
    # the spec carries a malformed token we can't safely ship.
    target_re = USER_FACING_ANNEX_RE if spec.is_annex else USER_FACING_ARTICLE_RE
    if not target_re.match(out):
        raise InvalidRefError(f"formatted ref fails strict wire regex: {out!r}")
    return out


def _format_internal(spec: RefSpec) -> str:
    """Render a :class:`RefSpec` in internal canonical form."""
    if spec.is_annex:
        head = f"Annex {spec.annex_roman}"
    else:
        head = f"Art. {spec.article_number}"
    tail = "".join(f"({t})" for t in spec.subpoints)
    return head + tail


def _normalise_sub_fragment(sub: str) -> str:
    """Prepend a ``.`` so a bare token like ``"a"`` becomes a parseable tail."""
    s = (sub or "").strip()
    if not s:
        return s
    # If the first char is already a separator (``.``/``(``), leave it.
    if s[0] in ".(":
        return s
    return "." + s
