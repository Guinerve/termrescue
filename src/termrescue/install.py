"""Install the shell hook: write it to the home directory and source it from the rc file."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

SHELLS = ("zsh", "bash", "powershell")
_SOURCE_FILES = {"zsh": "termrescue.zsh", "bash": "termrescue.bash", "powershell": "termrescue.ps1"}
_MARK = "# termrescue"  # ends every line `install` adds


class NoPowerShellError(LookupError):
    pass


def hook_text(shell: str) -> str:
    return files("termrescue").joinpath("shell", _SOURCE_FILES[shell]).read_text(encoding="utf-8")


def hook_path(shell: str, home: Path) -> Path:
    return home / f".{_SOURCE_FILES[shell]}"


def powershell_executables() -> list[str]:
    """PowerShell 7+ and Windows PowerShell 5.1, whichever are installed.

    Windows PowerShell is also looked for at its standard location, because
    some machines don't have it on PATH. Only absolute paths from PATH count.
    """
    found = []
    for name in ("pwsh", "powershell"):
        path = shutil.which(name)
        if path is not None and not os.path.isabs(path):
            # On Windows, which() looks in the current directory first. Never run
            # a pwsh.exe that happens to sit in the folder `install` was run from.
            path = None
        if path is None and name == "powershell" and sys.platform == "win32":
            standard = (Path(os.environ.get("SystemRoot", r"C:\Windows"))
                        / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
            path = str(standard) if standard.exists() else None
        if path:
            found.append(path)
    return found


def powershell_profiles() -> list[Path]:
    """$PROFILE for each PowerShell edition installed (7+ and Windows PowerShell 5.1)."""
    profiles = []
    for exe in powershell_executables():
        result = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", "$PROFILE.CurrentUserCurrentHost"],
            capture_output=True, text=True, check=False, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            profiles.append(Path(result.stdout.strip()))
    return profiles


def _zsh_dir(home: Path) -> Path:
    """zsh reads .zshrc from $ZDOTDIR when it is set, and from the home directory if not."""
    zdotdir = os.environ.get("ZDOTDIR")
    return Path(zdotdir).expanduser() if zdotdir else home


# bash login shells read the first of these that exists, and never read ~/.bashrc.
_BASH_LOGIN_FILES = (".bash_profile", ".bash_login", ".profile")


def _bash_login_file(home: Path) -> Path:
    """The file a bash login shell reads. macOS terminals start login shells.

    If none exists, use ~/.profile: a new ~/.bash_profile would stop bash
    from reading a ~/.profile the user adds later.
    """
    for name in _BASH_LOGIN_FILES:
        if (home / name).exists():
            return home / name
    return home / ".profile"


def _rc_files(shell: str, home: Path, profiles: list[Path] | None) -> list[Path]:
    if shell == "zsh":
        return [_zsh_dir(home) / ".zshrc"]
    if shell == "bash":
        rc_files = [home / ".bashrc"]
        if sys.platform == "darwin":
            rc_files.append(_bash_login_file(home))
        return rc_files
    rc_files = profiles if profiles is not None else powershell_profiles()
    if not rc_files:
        raise NoPowerShellError("couldn't find PowerShell or its profile path")
    return rc_files


def _uninstall_files(shell: str, home: Path, profiles: list[Path] | None) -> list[Path]:
    """Every file an install could have changed, on any platform."""
    if shell == "zsh":
        return list(dict.fromkeys([home / ".zshrc", _zsh_dir(home) / ".zshrc"]))
    if shell == "bash":
        return [home / ".bashrc", *(home / name for name in _BASH_LOGIN_FILES)]
    return _rc_files(shell, home, profiles)


# PowerShell ends a single-quoted string at any of these, and reads two in a row as one.
_POWERSHELL_QUOTES = "'\u2018\u2019\u201a\u201b"


def _source_line(shell: str, hook: Path, rc: Path) -> str:
    if shell == "powershell":
        quoted = "".join(ch * 2 if ch in _POWERSHELL_QUOTES else ch for ch in str(hook))
        return f". '{quoted}'  {_MARK}"
    if rc.name in _BASH_LOGIN_FILES:
        # ~/.profile is also read by sh, which has no `source` and can't parse the hook.
        return f'[ -n "$BASH_VERSION" ] && . ~/{hook.name}  {_MARK}'
    return f"source ~/{hook.name}  {_MARK}"


def _is_source_line(line: str, shell: str, hook: Path, rc: Path) -> bool:
    """True only for the exact line `install` writes, so users' own lines are left alone."""
    return line.strip() == _source_line(shell, hook, rc)


def _read(path: Path) -> tuple[str, str, str]:
    """Text, encoding and line ending of ``path``, so it can be written back unchanged.

    PowerShell profiles may be UTF-16 or in the ANSI code page. Bytes that are not
    UTF-8 survive the round trip through surrogate escapes.
    """
    if not path.exists():
        return "", "utf-8", os.linesep
    data = path.read_bytes()
    encoding = "utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    text = data.decode(encoding, errors=_errors(encoding))
    newline = "\r\n" if "\r\n" in text else ("\n" if "\n" in text else os.linesep)
    return text.replace("\r\n", "\n"), encoding, newline


def _errors(encoding: str) -> str:
    return "surrogateescape" if encoding == "utf-8" else "strict"


def _write(path: Path, text: str, encoding: str, newline: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", newline), encoding=encoding, errors=_errors(encoding),
                    newline="")


def install(shell: str, home: Path, profiles: list[Path] | None = None) -> list[Path]:
    """Install the hook; return the rc files that were changed."""
    rc_files = _rc_files(shell, home, profiles)  # fails before writing anything
    hook = hook_path(shell, home)
    hook.write_text(hook_text(shell), encoding="utf-8")
    changed = []
    for rc in rc_files:
        text, encoding, newline = _read(rc)
        if any(_is_source_line(existing, shell, hook, rc) for existing in text.splitlines()):
            continue
        if text and not text.endswith("\n"):
            text += "\n"
        _write(rc, text + _source_line(shell, hook, rc) + "\n", encoding, newline)
        changed.append(rc)
    return changed


def uninstall(shell: str, home: Path, profiles: list[Path] | None = None) -> list[Path]:
    """Remove the hook and its source lines; return the rc files that were changed."""
    hook = hook_path(shell, home)
    changed = []
    for rc in _uninstall_files(shell, home, profiles):
        if not rc.exists():
            continue
        text, encoding, newline = _read(rc)
        lines = text.splitlines(keepends=True)
        kept = [ln for ln in lines if not _is_source_line(ln, shell, hook, rc)]
        if len(kept) != len(lines):
            _write(rc, "".join(kept), encoding, newline)
            changed.append(rc)
    hook.unlink(missing_ok=True)
    return changed


def execution_policy_warning() -> str | None:
    """Windows PowerShell 5.1 refuses to run profile scripts under some policies."""
    windows_powershell = [exe for exe in powershell_executables()
                          if Path(exe).stem.lower() == "powershell"]
    if not windows_powershell:
        return None
    result = subprocess.run([windows_powershell[0], "-NoProfile", "-NonInteractive", "-Command",
                             "Get-ExecutionPolicy"],
                            capture_output=True, text=True, check=False, timeout=60)
    policy = result.stdout.strip()
    if policy in ("Restricted", "AllSigned", "Undefined"):
        return (f"Windows PowerShell's execution policy is {policy}, so it won't run your "
                "profile. To allow your own scripts, run:\n"
                "  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned")
    return None
