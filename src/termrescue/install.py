"""Install the shell hook: write it to the home directory and source it from the rc file."""

from __future__ import annotations

import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

SHELLS = ("zsh", "bash", "powershell")
_SOURCE_FILES = {"zsh": "termrescue.zsh", "bash": "termrescue.bash", "powershell": "termrescue.ps1"}
_MARK = "# termrescue"


def hook_text(shell: str) -> str:
    return files("termrescue").joinpath("shell", _SOURCE_FILES[shell]).read_text(encoding="utf-8")


def hook_path(shell: str, home: Path) -> Path:
    return home / f".{_SOURCE_FILES[shell]}"


def powershell_profiles() -> list[Path]:
    """$PROFILE for each PowerShell edition installed (7+ and Windows PowerShell 5.1)."""
    profiles = []
    for exe in ("pwsh", "powershell"):
        if not shutil.which(exe):
            continue
        result = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", "$PROFILE.CurrentUserCurrentHost"],
            capture_output=True, text=True, check=False, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            profiles.append(Path(result.stdout.strip()))
    return profiles


def _rc_files(shell: str, home: Path, profiles: list[Path] | None) -> list[Path]:
    if shell == "zsh":
        return [home / ".zshrc"]
    if shell == "bash":
        return [home / ".bashrc"]
    return profiles if profiles is not None else powershell_profiles()


def _source_line(shell: str, hook: Path) -> str:
    if shell == "powershell":
        quoted = str(hook).replace("'", "''")
        return f". '{quoted}'  {_MARK}"
    return f"source ~/{hook.name}  {_MARK}"


def _read(path: Path) -> tuple[str, str]:
    """File text and the encoding to write it back with (PowerShell profiles may be UTF-16)."""
    if not path.exists():
        return "", "utf-8"
    data = path.read_bytes()
    encoding = "utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    # Normalise to \n; write_text turns it back into the platform's line ending.
    return data.decode(encoding).replace("\r\n", "\n"), encoding


def install(shell: str, home: Path, profiles: list[Path] | None = None) -> list[Path]:
    """Install the hook; return the rc files that were changed."""
    hook = hook_path(shell, home)
    hook.write_text(hook_text(shell), encoding="utf-8")
    line = _source_line(shell, hook)
    changed = []
    for rc in _rc_files(shell, home, profiles):
        text, encoding = _read(rc)
        if any(existing.rstrip().endswith(_MARK) for existing in text.splitlines()):
            continue
        if text and not text.endswith("\n"):
            text += "\n"
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text(text + line + "\n", encoding=encoding)
        changed.append(rc)
    return changed


def uninstall(shell: str, home: Path, profiles: list[Path] | None = None) -> list[Path]:
    """Remove the hook and its source lines; return the rc files that were changed."""
    changed = []
    for rc in _rc_files(shell, home, profiles):
        text, encoding = _read(rc)
        kept = [ln for ln in text.splitlines(keepends=True) if not ln.rstrip().endswith(_MARK)]
        if len(kept) != len(text.splitlines(keepends=True)):
            rc.write_text("".join(kept), encoding=encoding)
            changed.append(rc)
    hook_path(shell, home).unlink(missing_ok=True)
    return changed


def execution_policy_warning() -> str | None:
    """Windows PowerShell 5.1 refuses to run profile scripts under some policies."""
    if not shutil.which("powershell"):
        return None
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                             "Get-ExecutionPolicy"],
                            capture_output=True, text=True, check=False, timeout=60)
    policy = result.stdout.strip()
    if policy in ("Restricted", "AllSigned", "Undefined"):
        return (f"Windows PowerShell's execution policy is {policy}, so it won't run your "
                "profile. To allow your own scripts, run:\n"
                "  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned")
    return None
