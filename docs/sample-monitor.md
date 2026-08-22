# Sample temperature monitor

`vtemp-monitor` is the reference device client used to demonstrate VDevLab's
fault contracts through a real `/dev/vdevlab0` file descriptor. It is a small
consumer application, not a temperature-device emulator.

## Input protocol

The monitor accepts newline-delimited Celsius values from the device. It keeps
incomplete lines across reads, so normal, delayed, and partial reads use the
same parser.

```text
25.0
85.5
42.0
```

Values below 80 degrees produce `TEMPERATURE`. Values at or above 80 degrees
produce `THERMAL_WARNING`. Invalid or oversized lines are reported and skipped.

## Log contract

Each application log is one JSON object with a `timestamp_ms` value obtained
from `CLOCK_MONOTONIC` and an `event` name.

| Event | Meaning | Additional fields |
|---|---|---|
| `MONITOR_STARTED` | Device opened and poll loop started | none |
| `TEMPERATURE` | Normal value parsed | `temperature_c` |
| `THERMAL_WARNING` | Value is at least 80 degrees | `temperature_c` |
| `READ_RETRY` | A read returned `EIO` | `retry`, `max_retries`, `errno` |
| `RECOVERY_SUCCESS` | A read succeeded after one or more EIO results | `retries` |
| `DEVICE_DISCONNECTED` | A read returned `ENODEV` | `errno` |
| `READ_FAILED` | Retry limit or another read error ended the monitor | `errno` |
| `INVALID_INPUT` | A complete line was not a finite number | none |
| `INPUT_TOO_LONG` | An input line exceeded the buffer limit | none |

The client permits at most three consecutive EIO retries. A successful read
resets the retry count and emits exactly one recovery event. A fourth
consecutive EIO ends the process with `READ_FAILED`.

## Build and run

```bash
make examples
sudo ./examples/vtemp-monitor
```

Optional arguments select another device, stop after a fixed number of valid
temperature events, or change the poll timeout:

```bash
sudo ./examples/vtemp-monitor \
  --device /dev/vdevlab0 \
  --max-events 3 \
  --poll-timeout-ms 250
```

## Smoke test

The smoke test performs normal input, thermal warning, exactly three EIO
retries, recovery, and disconnect through the kernel device. It repeats the
complete module and process lifecycle ten times by default and writes JSONL
evidence under `logs/`.

```bash
make smoke-test
```

For a shorter diagnostic run, override the cycle count:

```bash
VDEVLAB_SMOKE_CYCLES=1 make smoke-test
```

## Stability Gate

`scripts/run-stability-test.sh` runs the same complete smoke lifecycle 100
times by default. It performs setup once, gives every cycle a distinct JSONL
log, checks new `dmesg` warning-or-higher patterns, verifies that the module,
device node, and monitor process are absent, and writes `summary.json` with the
requested and completed cycles, elapsed seconds, warning count, status, and log
paths.

```bash
./scripts/run-stability-test.sh
VDEVLAB_STABILITY_CYCLES=2 ./scripts/run-stability-test.sh
```

The second form is a diagnostic only; the project Gate requires 100/100 cycles.
