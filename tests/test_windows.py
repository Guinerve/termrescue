"""Windows console support.

The pure helpers run everywhere. The integration tests run only on Windows:
each starts a child process in a brand-new console, breaks that console the
way a dying ssh.exe does (virtual-terminal input left on), and checks that
termrescue repairs it.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from termrescue.sequences import PROMPT_RESET
from termrescue.winconsole import (
    ENABLE_VIRTUAL_TERMINAL_INPUT,
    describe_input_mode,
    repaired_input_mode,
)

SRC = Path(__file__).resolve().parent.parent / "src"
PS_HOOK = SRC / "termrescue" / "shell" / "termrescue.ps1"
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="needs a Windows console")

TYPICAL_POWERSHELL_INPUT_MODE = 0x1F7  # what PowerShell's console normally uses
AFTER_SSH_DIED = TYPICAL_POWERSHELL_INPUT_MODE | ENABLE_VIRTUAL_TERMINAL_INPUT


# --- pure helpers ---------------------------------------------------------------

def test_repaired_input_mode_turns_virtual_terminal_input_off():
    assert repaired_input_mode(AFTER_SSH_DIED) == TYPICAL_POWERSHELL_INPUT_MODE


def test_repaired_input_mode_leaves_a_healthy_mode_alone():
    assert repaired_input_mode(TYPICAL_POWERSHELL_INPUT_MODE) == TYPICAL_POWERSHELL_INPUT_MODE


def test_describe_input_mode_flags_the_stuck_state():
    assert "virtual-terminal input is ON" in describe_input_mode(AFTER_SSH_DIED)
    assert "virtual-terminal input is off" in describe_input_mode(TYPICAL_POWERSHELL_INPUT_MODE)


def test_powershell_hook_sends_exactly_the_prompt_reset():
    text = PS_HOOK.read_text()
    literal = re.search(r'\$global:TermRescueReset = "([^"]*)"', text).group(1)
    assert literal.replace("$e", "\x1b") == PROMPT_RESET


# --- integration: a real, separate Windows console -------------------------------

def _run_in_new_console(argv: list[str], result_file: Path, timeout: float = 60) -> dict:
    proc = subprocess.Popen(
        argv, creationflags=subprocess.CREATE_NEW_CONSOLE,
        env=os.environ | {"PYTHONPATH": str(SRC)},
    )
    deadline = time.monotonic() + timeout
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    if proc.poll() is None:
        proc.kill()
        pytest.fail(f"{argv[0]} did not finish within {timeout}s")
    assert result_file.exists(), f"{argv} exited {proc.returncode} without writing a result"
    return json.loads(result_file.read_text(encoding="utf-8-sig"))


@windows_only
def test_fix_turns_virtual_terminal_input_off_in_a_broken_console(tmp_path):
    result_file = tmp_path / "result.json"
    script = tmp_path / "child.py"
    script.write_text(textwrap.dedent(f"""
        import json, subprocess, sys, traceback
        try:
            from termrescue import winconsole
            con = winconsole.WindowsTerminal()
            con.set_input_mode(con.input_mode() | winconsole.ENABLE_VIRTUAL_TERMINAL_INPUT)
            before = con.input_mode()
            code = subprocess.call([sys.executable, "-m", "termrescue", "fix"])
            after = con.input_mode()
            result = {{"before": before, "after": after, "code": code}}
        except Exception:
            result = {{"error": traceback.format_exc()}}
        open({str(result_file)!r}, "w").write(json.dumps(result))
    """))
    result = _run_in_new_console([sys.executable, str(script)], result_file)
    assert "error" not in result, result.get("error")
    assert result["code"] == 0
    assert result["before"] & ENABLE_VIRTUAL_TERMINAL_INPUT
    assert not result["after"] & ENABLE_VIRTUAL_TERMINAL_INPUT


POWERSHELLS = [exe for exe in ("pwsh", "powershell") if shutil.which(exe)]


@windows_only
@pytest.mark.parametrize("exe", POWERSHELLS or ["pwsh"])
def test_powershell_prompt_repairs_a_broken_console_and_keeps_the_users_prompt(exe, tmp_path):
    if not shutil.which(exe):
        pytest.skip(f"{exe} not installed")
    result_file = tmp_path / "result.json"
    script = tmp_path / "child.ps1"
    script.write_text(textwrap.dedent(f"""
        $ErrorActionPreference = 'Stop'
        trap {{
            @{{ error = "$_ $($_.ScriptStackTrace)" }} | ConvertTo-Json |
                Set-Content -Encoding UTF8 '{result_file}'
            exit 1
        }}
        function global:prompt {{ "MINE code=$global:LASTEXITCODE> " }}
        . '{PS_HOOK}'
        . '{PS_HOOK}'   # sourcing twice must not wrap the prompt twice
        $null = prompt  # first prompt at startup: native helper not loaded yet
        $null = prompt  # second prompt loads it
        $h = [TermRescue.Native]::GetStdHandle(-10)
        $mode = [uint32]0
        [void][TermRescue.Native]::GetConsoleMode($h, [ref]$mode)
        [void][TermRescue.Native]::SetConsoleMode($h, $mode -bor 0x200)
        [void][TermRescue.Native]::GetConsoleMode($h, [ref]$mode)
        $before = $mode
        $global:LASTEXITCODE = 7
        $shown = prompt
        [void][TermRescue.Native]::GetConsoleMode($h, [ref]$mode)
        @{{ before = $before; after = $mode; shown = $shown; code = $global:LASTEXITCODE }} |
            ConvertTo-Json | Set-Content -Encoding UTF8 '{result_file}'
    """))
    result = _run_in_new_console(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], result_file)
    assert "error" not in result, result.get("error")
    assert result["before"] & ENABLE_VIRTUAL_TERMINAL_INPUT
    assert not result["after"] & ENABLE_VIRTUAL_TERMINAL_INPUT
    assert result["shown"] == "MINE code=7> "
    assert result["code"] == 7
