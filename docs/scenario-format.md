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
Its top-level `schema_version` is independent of the scenario format version.

Successful output includes the scenario name and normalized event and
assertion counts. Validation failure exits with status 2 and prints one stable,
path-qualified error.
