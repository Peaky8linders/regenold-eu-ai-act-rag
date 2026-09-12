"""R412 — the Neo4j DBMS-notification de-duplicating log filter.

The driver logs EVERY notification it receives through ``neo4j.notifications``
at WARNING and embeds the full Cypher text in the message. Vector recall calls
``db.index.vector.queryNodes``, which is DEPRECATION-flagged on every execution,
so one benchmark row printed the same ~1.3 kB notice three times and buried
genuine warnings at the same level.

These tests pin the two properties that matter: repeats are dropped, and nothing
outside the non-actionable informational classes is ever touched.
"""

from __future__ import annotations

import logging

import pytest

from app.graph.client import (
    _NOTIFICATION_NOISE_CLASSIFICATIONS,
    _NotificationDedupeFilter,
    install_notification_dedupe,
)


class _FakeNotification:
    def __init__(self, classification: str, description: str) -> None:
        self.classification = classification
        self.status_description = description


class _FakePrinter:
    """Stands in for the driver's ``NotificationPrinter``."""

    def __init__(self, notification: _FakeNotification, query: str = "MATCH (n) RETURN n") -> None:
        self.notification = notification
        self.query = query

    def __str__(self) -> str:  # pragma: no cover - only used by logging
        return f"{self.notification.classification} for query: {self.query!r}"


@pytest.fixture()
def captured() -> tuple[logging.Logger, list[str]]:
    """A fresh ``neo4j.notifications`` logger with the filter attached."""
    logger = logging.getLogger("neo4j.notifications")
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
            records.append(record.getMessage())

    handler = _Capture()
    logger.addHandler(handler)
    dedupe = _NotificationDedupeFilter()
    logger.addFilter(dedupe)
    try:
        yield logger, records
    finally:
        logger.removeFilter(dedupe)
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _emit(logger: logging.Logger, notification: _FakeNotification) -> None:
    logger.warning(
        "Received notification from DBMS server: %s", _FakePrinter(notification)
    )


def test_repeat_notifications_are_collapsed_to_one(captured) -> None:
    logger, records = captured
    deprecation = _FakeNotification(
        "NotificationClassification.DEPRECATION",
        "feature deprecated with replacement. db.index.vector.queryNodes is deprecated.",
    )
    for _ in range(5):
        _emit(logger, deprecation)
    assert len(records) == 1, "the same notification must be logged once per process"


def test_distinct_notifications_are_both_kept(captured) -> None:
    logger, records = captured
    first = _FakeNotification("NotificationClassification.DEPRECATION", "notice A")
    second = _FakeNotification("NotificationClassification.DEPRECATION", "notice B")
    _emit(logger, first)
    _emit(logger, second)
    _emit(logger, first)
    assert len(records) == 2, "different descriptions are different notifications"


def test_security_notifications_are_never_deduplicated(captured) -> None:
    """A repeated SECURITY notice must not be hidden by the first one."""
    logger, records = captured
    security = _FakeNotification("NotificationClassification.SECURITY", "auth disabled")
    for _ in range(3):
        _emit(logger, security)
    assert len(records) == 3
    assert "SECURITY" not in "".join(
        c for c in _NOTIFICATION_NOISE_CLASSIFICATIONS
    ), "SECURITY must stay out of the de-duplicated set"


def test_unkeyable_records_pass_through(captured) -> None:
    """A message the filter cannot classify is never swallowed."""
    logger, records = captured
    logger.warning("Received notification from DBMS server: %s", "a plain string arg")
    logger.warning("Received notification from DBMS server: %s", "a plain string arg")
    assert len(records) == 2


def test_install_is_idempotent() -> None:
    """Installing twice must not stack filters (each would halve visibility)."""
    logger = logging.getLogger("neo4j.notifications")
    before = [f for f in logger.filters if isinstance(f, _NotificationDedupeFilter)]
    for f in before:
        logger.removeFilter(f)
    try:
        assert install_notification_dedupe() is True
        assert install_notification_dedupe() is False
        assert (
            len([f for f in logger.filters if isinstance(f, _NotificationDedupeFilter)]) == 1
        )
    finally:
        for f in list(logger.filters):
            if isinstance(f, _NotificationDedupeFilter):
                logger.removeFilter(f)
