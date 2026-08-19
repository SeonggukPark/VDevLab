# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import argparse
from collections.abc import Sequence
from glob import glob, has_magic
import sys

from . import __version__
from .runner import RunnerError, ScenarioRunner
from .scenario import ScenarioValidationError, load_scenario


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vdevlab")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate scenario YAML")
    validate.add_argument("paths", nargs="+", help="scenario YAML path")

    run = commands.add_parser("run", help="run a scenario against its device")
    run.add_argument("path", help="scenario YAML path")
    run.add_argument("--cwd", default=".", help="application working directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)

    if arguments.command == "validate":
        paths: list[str] = []
        for path in arguments.paths:
            matches = sorted(glob(path)) if has_magic(path) else [path]
            paths.extend(matches or [path])

        for path in paths:
            try:
                scenario = load_scenario(path)
            except ScenarioValidationError as error:
                print(f"error: {error}", file=sys.stderr)
                return 2

            print(
                f"valid: {path} name={scenario.name} "
                f"events={len(scenario.events)} assertions={len(scenario.assertions)}"
            )
        return 0

    if arguments.command == "run":
        try:
            scenario = load_scenario(arguments.path)
            result = ScenarioRunner().run(scenario, cwd=arguments.cwd)
        except ScenarioValidationError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print("error: interrupted", file=sys.stderr)
            return 130
        except (OSError, RunnerError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1

        if result.application.stdout:
            print(result.application.stdout, end="")
        if result.application.stderr:
            print(result.application.stderr, end="", file=sys.stderr)
        print(
            f"result: name={result.scenario_name} "
            f"exit_code={result.application.exit_code} "
            f"timed_out={str(result.application.timed_out).lower()} "
            f"forced={str(result.application.forced).lower()} "
            f"events={len(result.dispatches)}"
        )

        if result.application.timed_out:
            return 124
        if result.application.exit_code != 0:
            return result.application.exit_code if 1 <= result.application.exit_code <= 125 else 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
