# SPDX-License-Identifier: GPL-2.0-only

import errno

import pytest

from vdevlab.analysis import (
    ApplicationLogError,
    calculate_recovery_metrics,
    evaluate_event_assertions,
    evaluate_retry_count,
    parse_application_log,
)


RECOVERY_LOG = """\
{"timestamp_ms":1000,"event":"MONITOR_STARTED"}
{"timestamp_ms":1100,"event":"READ_RETRY","retry":1,"max_retries":3,"errno":5}
{"timestamp_ms":1120,"event":"READ_RETRY","retry":2,"max_retries":3,"errno":5}
{"timestamp_ms":1140,"event":"READ_RETRY","retry":3,"max_retries":3,"errno":5}
{"timestamp_ms":1200,"event":"RECOVERY_SUCCESS","retries":3}
{"timestamp_ms":1200,"event":"TEMPERATURE","temperature_c":42.0}
"""


def test_parse_and_calculate_recovery_metrics() -> None:
    events = parse_application_log(RECOVERY_LOG)
    metrics = calculate_recovery_metrics(events)

    assert len(events) == 6
    assert metrics.observed_eio_count == 3
    assert metrics.application_retry_count == 3
    assert metrics.first_error_timestamp_ms == 1100
    assert metrics.recovery_timestamp_ms == 1200
    assert metrics.recovery_latency_ms == 100
    assert metrics.recoveries[0].observed_retries == 3
    assert metrics.recoveries[0].reported_retries == 3


def test_calculate_recovery_metrics_supports_multiple_windows() -> None:
    text = "\n".join(
        (
            '{"timestamp_ms":10,"event":"READ_RETRY","retry":1,"errno":5}',
            '{"timestamp_ms":20,"event":"RECOVERY_SUCCESS","retries":1}',
            '{"timestamp_ms":30,"event":"READ_RETRY","retry":1,"errno":5}',
            '{"timestamp_ms":50,"event":"RECOVERY_SUCCESS","retries":1}',
        )
    )

    metrics = calculate_recovery_metrics(parse_application_log(text))

    assert [window.recovery_latency_ms for window in metrics.recoveries] == [10, 20]
    assert metrics.application_retry_count == 2


def test_non_eio_retry_is_not_counted_as_observed_eio() -> None:
    text = (
        f'{{"timestamp_ms":10,"event":"READ_RETRY","retry":1,'
        f'"errno":{errno.ENODEV}}}'
    )

    metrics = calculate_recovery_metrics(parse_application_log(text))

    assert metrics.application_retry_count == 1
    assert metrics.observed_eio_count == 0
    assert metrics.recoveries == ()
    assert metrics.first_error_timestamp_ms == 10
    assert metrics.recovery_timestamp_ms is None
    assert metrics.recovery_latency_ms is None


@pytest.mark.parametrize(
    ("expected", "passed"),
    ((3, True), (2, False)),
)
def test_evaluate_retry_count(expected: int, passed: bool) -> None:
    metrics = calculate_recovery_metrics(parse_application_log(RECOVERY_LOG))

    assertion = evaluate_retry_count(metrics, expected)

    assert assertion.expected == expected
    assert assertion.observed == 3
    assert assertion.passed is passed


def test_evaluate_event_assertions_applies_count_and_within_window() -> None:
    events = parse_application_log(RECOVERY_LOG)

    assertions = evaluate_event_assertions(
        events,
        (
            {"event": "READ_RETRY", "count": 2, "within_ms": 130},
            {"event": "READ_RETRY", "count": 3, "within_ms": 200},
            {"event": "TEMPERATURE", "count": 2},
        ),
    )

    assert [(item.observed, item.passed) for item in assertions] == [
        (2, True),
        (3, True),
        (1, False),
    ]


def test_evaluate_event_assertions_handles_empty_log() -> None:
    assertions = evaluate_event_assertions(
        (), ({"event": "READ_RETRY", "count": 1, "within_ms": 100},)
    )

    assert assertions[0].observed == 0
    assert assertions[0].passed is False


@pytest.mark.parametrize(
    "definition",
    (
        {"event": "", "count": 1},
        {"event": "READ_RETRY", "count": 0},
        {"event": "READ_RETRY", "count": True},
        {"event": "READ_RETRY", "count": 1, "within_ms": -1},
    ),
)
def test_evaluate_event_assertions_rejects_invalid_definition(
    definition: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        evaluate_event_assertions((), (definition,))


@pytest.mark.parametrize("expected", (-1, True, 1.5))
def test_evaluate_retry_count_rejects_invalid_expected_value(expected: object) -> None:
    metrics = calculate_recovery_metrics(())

    with pytest.raises(ApplicationLogError, match="expected retry count"):
        evaluate_retry_count(metrics, expected)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "message"),
    (
        ("not-json", "invalid JSON"),
        ("[]", "event must be a JSON object"),
        ('{"timestamp_ms":true,"event":"START"}', "timestamp_ms"),
        ('{"timestamp_ms":1,"event":""}', "event must be"),
        (
            '{"timestamp_ms":2,"event":"START"}\n'
            '{"timestamp_ms":1,"event":"END"}',
            "monotonically non-decreasing",
        ),
    ),
)
def test_parse_application_log_rejects_invalid_events(
    text: str, message: str
) -> None:
    with pytest.raises(ApplicationLogError, match=message):
        parse_application_log(text)


def test_parse_application_log_reports_stdout_line() -> None:
    with pytest.raises(ApplicationLogError) as exc_info:
        parse_application_log('\n{"timestamp_ms":1,"event":null}')

    assert str(exc_info.value).startswith("stdout[2]:")
    assert exc_info.value.line == 2


def test_recovery_success_requires_preceding_retry() -> None:
    events = parse_application_log(
        '{"timestamp_ms":10,"event":"RECOVERY_SUCCESS","retries":0}'
    )

    with pytest.raises(ApplicationLogError, match="no preceding READ_RETRY"):
        calculate_recovery_metrics(events)


@pytest.mark.parametrize(
    "text",
    (
        '{"timestamp_ms":10,"event":"READ_RETRY","retry":true,"errno":5}',
        '{"timestamp_ms":10,"event":"READ_RETRY","retry":1,"errno":null}',
        '{"timestamp_ms":10,"event":"RECOVERY_SUCCESS","retries":-1}',
    ),
)
def test_calculate_recovery_metrics_validates_event_fields(text: str) -> None:
    events = parse_application_log(text)

    with pytest.raises(ApplicationLogError):
        calculate_recovery_metrics(events)
