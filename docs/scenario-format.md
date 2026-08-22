# Scenario schema version 1

VDevLab scenarios describe deterministic actions and observable application-log
assertions. Validation occurs before any process, device, or fault state is
changed.

## Root fields

Every document contains exactly these fields:

| Field | Type | Purpose |
|---|---|---|
| `schema_version` | integer | Must be `1` |
| `device` | mapping | Device path used by the scenario |
| `application` | mapping | Program and startup deadline |
| `scenario` | mapping | Name, deadline, and scheduled actions |
| `assertions` | list | Expected structured application events |

Unknown fields are rejected. Error messages contain the full field path, for
example `scenario.events[1].repeat: must be between 1 and 1000000`.

## Durations

Durations are non-negative integers followed by `ms` or `s`:

```yaml
startup_timeout: 2s
at: 250ms
```

Decimals, signs, leading zeroes, missing suffixes, and values above 24 hours
are rejected. The parser normalizes accepted values to integer milliseconds.

## Device and application

```yaml
device:
  path: /dev/vdevlab0

application:
  command:
    - ./examples/vtemp-monitor
    - --poll-timeout-ms
    - "250"
  startup_timeout: 2s
```

`device.path` must be an absolute path below `/dev`. `application.command` is a
non-empty argument list rather than a shell command string. This preserves
argument boundaries for the future runner. `startup_timeout` defaults to two
seconds when omitted.

## Scenario and event ordering

```yaml
scenario:
  name: three-eio-recovery
  timeout: 5s
  events:
    - at: 100ms
      action: fault
      type: eio
      repeat: 3
    - at: 200ms
      action: write
      data: "42\n"
```

Each event time must not exceed `scenario.timeout`. Times must be
non-decreasing in YAML order; an event earlier than its predecessor is rejected.
Events with the same time retain their YAML order.

### Event forms

| Action | Required fields | Constraints |
|---|---|---|
| `write` | `at`, `action`, `data` | `data` is a non-empty string |
| `fault` / `eio` | `at`, `action`, `type`, `repeat` | `repeat` is 1–1,000,000 |
| `fault` / `delay` | `at`, `action`, `type`, `duration` | Valid duration |
| `fault` / `partial-read` | `at`, `action`, `type`, `bytes` | `bytes` is 1–4,096 |
| `fault` / `disconnect` | `at`, `action`, `type` | No additional field |
| `clear` | `at`, `action` | Clears the active fault |
| `reset` | `at`, `action` | Clears fault and FIFO data |

Fields belonging to another event form are rejected instead of being ignored.

## Assertions

```yaml
assertions:
  - event: READ_RETRY
    count: 3
    within: 2s
  - event: RECOVERY_SUCCESS
    count: 1
    within: 3s
    max_latency: 1s
```

`event` must be one of the structured events documented for the sample
monitor. `count` is a positive integer. Optional `within` must not exceed the
scenario timeout. `max_latency` is available only for `RECOVERY_SUCCESS` and
limits the time from the first retryable error to the recovery event.

Additional assertion types use an explicit `type` discriminator:

```yaml
  - type: stdout
    contains: RECOVERY_SUCCESS
    not_contains: READ_FAILED
  - type: disconnect
    expected: true
  - type: kernel_warnings
    count: 0
```

`stdout` accepts `contains`, `not_contains`, or both. `disconnect` checks for a
structured `DEVICE_DISCONNECTED` application event. `kernel_warnings` compares
new warning-or-higher `dmesg` entries recorded during the scenario. A requested
kernel log assertion produces `ERROR`, not a false pass, when the log cannot be
read; run these scenarios with sufficient permission to read the kernel log.

## Validation

Install the package and validate one or more files without accessing the
kernel device:

```bash
python -m pip install --editable '.[test]'
vdevlab validate examples/scenarios/*.yaml
python -m pytest
```

Run a scenario with `--report` to persist its status, observations, assertion
results, and monotonic causal timeline as JSON:

```bash
vdevlab run examples/scenarios/recovery.yaml --report recovery-report.json
```

The report is written for `PASS`, `FAIL`, `ERROR`, and `TIMEOUT` outcomes.
Scenario dispatch timestamps use the same whole-millisecond resolution as the
application log. A scenario event sorts before an application event when both
occur in the same millisecond, preserving the causal order at the clock's
published resolution.

## Focused delay example

[`examples/scenarios/delay.yaml`](../examples/scenarios/delay.yaml) applies the
existing 100-millisecond read delay, writes one temperature payload, and checks
that the monitor starts, produces one `TEMPERATURE` event, exits with code zero,
and records no new kernel warning. Every scenario report automatically includes
the process exit-code assertion, so a nonzero exit changes the report to `FAIL`.

For the 100-millisecond request, the kernel runtime contract accepts an observed
delay from 80 through 1,000 milliseconds. The lower allowance covers timer
granularity and scheduling jitter; the upper bound detects accidental repeated
or unbounded sleeps. The focused scenario checks observable application and
report behavior, while the kernel runtime suite measures this timing tolerance
directly.

## Focused partial-read example

[`examples/scenarios/partial-read.yaml`](../examples/scenarios/partial-read.yaml)
limits each successful read to two bytes and writes the six-byte payload
`42.5\n`. The sample monitor retains incomplete lines across reads, so the
scenario passes only after it reconstructs the complete payload and emits
`"temperature_c":42.500` without `INVALID_INPUT`.

The partial-read fault remains active until cleanup, never returns more than
the configured byte limit, and never discards the unread FIFO remainder. The
kernel contract suite verifies the per-read byte limit directly; this focused
scenario verifies the user-visible buffering, parse, report, zero exit-code,
kernel-warning, and cleanup behavior.
Deterministic schema examples are available in
[`examples/reports/recovery-pass.json`](../examples/reports/recovery-pass.json)
and [`examples/reports/recovery-fail.json`](../examples/reports/recovery-fail.json).
Its top-level `schema_version` is independent of the scenario format version.

Successful output includes the scenario name and normalized event and
assertion counts. Validation failure exits with status 2 and prints one stable,
path-qualified error.
