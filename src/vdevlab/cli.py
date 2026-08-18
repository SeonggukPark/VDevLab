# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import argparse
from collections.abc import Sequence
from glob import glob, has_magic
import sys

from . import __version__
from .scenario import ScenarioValidationError, load_scenario


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vdevlab")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate scenario YAML")
    validate.add_argument("paths", nargs="+", help="scenario YAML path")
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

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
