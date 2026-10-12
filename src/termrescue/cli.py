"""termrescue command line."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from . import doctor, install, terminal
from .reports import find_reports
from .sequences import FULL_RESET, describe


def _send_full_reset() -> bool:
    """Reset the terminal; False if there is no terminal to reset."""
    try:
        with terminal.open_terminal() as term:
            term.write(FULL_RESET)
            term.repair_input_mode()
    except OSError:
        return False
    return True


def cmd_fix(args: argparse.Namespace) -> int:
    if args.print:
        print(describe(FULL_RESET))
        return 0
    if not _send_full_reset():
        print("termrescue fix: no terminal attached")
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    print(install.hook_text(args.shell), end="")
    return 0


def _default_shell() -> str | None:
    if sys.platform == "win32":
        return "powershell"
    name = Path(os.environ.get("SHELL", "")).name
    return name if name in install.SHELLS else None


def cmd_install(args: argparse.Namespace) -> int:
    shell = args.shell or _default_shell()
    if shell is None:
        print("termrescue install: name a shell (zsh, bash or powershell)")
        return 2
    home = Path.home()
    if args.cmd == "uninstall":
        changed = install.uninstall(shell, home)
        for rc in changed:
            print(f"Removed termrescue from {rc}")
        if not changed:
            print("termrescue was not installed.")
        return 0
    rc_files = install.install(shell, home)
    print(f"Wrote {install.hook_path(shell, home)}")
    for rc in rc_files:
        print(f"Added it to {rc}")
    if not rc_files:
        print("Already set up; the hook file was refreshed.")
    if shell == "powershell":
        warning = install.execution_policy_warning()
        if warning:
            print(warning)
    print("Open a new terminal window to start using it.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("termrescue run: give a command, e.g. termrescue run -- ssh myhost")
        return 2
    try:
        code = subprocess.call(command)
    except KeyboardInterrupt:
        code = 130
    finally:
        _send_full_reset()
    return 128 - code if code < 0 else code


def _stop_index(text: str) -> int:
    """Index of the first q or Ctrl-C that isn't inside a report, or -1."""
    covered = set()
    for report in find_reports(text):
        start = text.index(report.raw)
        covered.update(range(start, start + len(report.raw)))
    for i, ch in enumerate(text):
        if ch in "q\x03" and i not in covered:
            return i
    return -1


def _describe_input(text: str) -> list[str]:
    lines = []
    pos = 0
    for report in find_reports(text):
        start = text.index(report.raw, pos)
        if start > pos:
            lines.append(f"{repr(text[pos:start]).replace(chr(92) + 'x1b', '^['):<24}text")
        if report.kind == "mouse":
            action = "release" if report.released else ("motion" if report.button & 32 else "press")
            detail = (f"mouse  {report.encoding}  button {report.button}  column {report.column}"
                      f"  row {report.row}  ({action})")
        else:
            detail = f"focus  {report.encoding}"
        lines.append(f"{describe(report.raw):<24}{detail}")
        pos = start + len(report.raw)
    if pos < len(text):
        lines.append(f"{repr(text[pos:]).replace(chr(92) + 'x1b', '^['):<24}text")
    return lines


def cmd_capture(args: argparse.Namespace) -> int:
    text = ""
    with terminal.open_terminal() as term:
        report = term.input_mode_report()
    if report:
        print(report)
    # Raw mode first, so nothing the terminal sends after the prompt is lost.
    with terminal.open_terminal() as term, term.raw():
        term.write(f"Press q (or wait {args.seconds:g}s) to stop. Move the mouse, click, "
                   "switch windows: everything the terminal sends is recorded.\r\n")
        deadline = time.monotonic() + args.seconds
        while _stop_index(text) < 0 and time.monotonic() < deadline:
            text += term.read_available(deadline - time.monotonic())
    stop = _stop_index(text)
    if stop >= 0:
        text = text[:stop]
    if not text:
        print("Nothing received.")
        return 0
    print(f"Raw: {describe(text)}")
    for line in _describe_input(text):
        print(line)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    return doctor.run(args.timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="termrescue",
        description="Clear terminal modes left on by programs that died "
                    "(e.g. mouse-reporting garbage after an SSH link drops).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fix", help="switch every stuck mode off now")
    p.add_argument("--print", action="store_true", help="show the sequence instead of sending it")
    p.set_defaults(func=cmd_fix)

    p = sub.add_parser("install", help="set up the shell hook (default: your current shell)")
    p.add_argument("shell", nargs="?", choices=install.SHELLS)
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall", help="remove the shell hook")
    p.add_argument("shell", nargs="?", choices=install.SHELLS)
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("init", help="print the shell hook")
    p.add_argument("shell", choices=install.SHELLS)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("run", help="run a command, then reset the terminal however it exits")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("capture", help="show exactly what the terminal is sending")
    p.add_argument("--seconds", type=float, default=10)
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("doctor", help="ask the terminal which modes are on")
    p.add_argument("--timeout", type=float, default=1.0)
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)
