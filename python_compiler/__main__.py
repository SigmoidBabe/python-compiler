"""Command-line interface for python-project-compiler."""

import argparse
import subprocess
import sys
from zipfile import BadZipFile

from .builder import build


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Embed a Python project zipapp in a RAM-backed Linux executable."
    )
    parser.add_argument("source", help="Project import root containing __main__.py")
    parser.add_argument("-o", "--output-dir", help="Artifact directory (default: SOURCE/dist/NAME)")
    parser.add_argument("-n", "--name", help="Executable name (default: source directory name)")
    parser.add_argument("-m", "--entry-point", help="Entry point, e.g. mypackage.cli:main")
    parser.add_argument("--cc", help="C compiler command (default: $CC or cc)")
    parser.add_argument("--cflag", action="append", default=[], help="Extra compiler flag; use --cflag=-FLAG")
    args = parser.parse_args()
    try:
        result = build(
            args.source, args.output_dir, name=args.name,
            entry_point=args.entry_point, cc=args.cc, cflags=args.cflag,
        )
    except (OSError, ValueError, subprocess.CalledProcessError, BadZipFile) as exc:
        print(f"python-compiler: {exc}", file=sys.stderr)
        return 1
    print(f"Executable: {result.executable}")
    print(f"Archive:    {result.archive}")
    print(f"Header:     {result.header}")
    print(f"Launcher:   {result.launcher}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
