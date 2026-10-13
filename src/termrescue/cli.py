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


def _error(command: str, message: str) -> None:
    print(f"termrescue {command}: {message}", file=sys.stderr)


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
        _error("fix", "no terminal attached")
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
        _error(args.cmd, "name a shell: zsh, bash or powershell")
        return 2
    home = Path.home()
    try:
        return _install_or_uninstall(args.cmd, shell, home)
    except install.NoPowerShellError:
        hook = install.hook_path(shell, home)
        if args.cmd == "uninstall":
            _error(args.cmd, "cannot find the PowerShell profile, so nothing changed.\n"
                   "Remove the line that ends in `# termrescue` from the file that "
                   f"`$PROFILE` names, then delete {hook}.")
        else:
            _error(args.cmd, "cannot find the PowerShell profile. To install the hook by hand,"
                   f" run:\n  termrescue init powershell > {hook}\n"
                   f"Then add this line to the file that `$PROFILE` names:\n  . '{hook}'")
        return 1


def _install_or_uninstall(cmd: str, shell: str, home: Path) -> int:
    if cmd == "uninstall":
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
        print("Already set up. The hook file is now up to date.")
    if shell == "powershell":
        warning = install.execution_policy_warning()
        if warning:
            print(warning)
    print("Open a new terminal window to start using it.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        _error("run", "give a command. Example: termrescue run -- ssh myhost")
        return 2
    try:
        code = subprocess.call(command)
    except KeyboardInterrupt:
        code = 130
    except OSError as exc:  # the command doesn't exist or can't be run
        _error("run", f"can't run {command[0]}: {exc.strerror}")
        code = 127 if isinstance(exc, FileNotFoundError) else 126
    finally:
        _send_full_reset()
    return 128 - code if code < 0 else code


def _stop_index(text: str) -> int:
    """Index of the first q or Ctrl-C that isn't inside a report, or -1."""
    covered = set()
    for report in find_reports(text):
        covered.update(range(report.start, report.start + len(report.raw)))
    for i, ch in enumerate(text):
        if ch in "q\x03" and i not in covered:
            return i
    return -1


def _describe_input(text: str) -> list[str]:
    lines = []
    pos = 0
    for report in find_reports(text):
        start = report.start
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
        term.write(f"Press q to stop, or wait {args.seconds:g} s. Move the mouse, click or "
                   "switch windows. termrescue records all that the terminal sends.\r\n")
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
        description="Switch off terminal modes that a dead program left on. Example: after "
                    "an SSH link drops, mouse moves type escape codes into your shell.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fix", help="switch all stuck modes off now")
    p.add_argument("--print", action="store_true", help="show the reset sequence, but do not send it")
    p.set_defaults(func=cmd_fix)

    p = sub.add_parser("install", help="add the prompt hook to your shell (default: your current shell)")
    p.add_argument("shell", nargs="?", choices=install.SHELLS)
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall", help="remove the prompt hook")
    p.add_argument("shell", nargs="?", choices=install.SHELLS)
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("init", help="print the hook script for a shell")
    p.add_argument("shell", choices=install.SHELLS)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("run", help="run a command, then reset the terminal when it stops")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("capture", help="show what the terminal sends, decoded")
    p.add_argument("--seconds", type=float, default=10,
                   help="stop after this many seconds (default: 10)")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("doctor", help="ask the terminal which modes are on")
    p.add_argument("--timeout", type=float, default=1.0,
                   help="seconds to wait for the terminal to answer (default: 1)")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except terminal.NoTerminalError:
        _error(args.cmd, "no terminal attached. Run it in a terminal window.")
        return 1
