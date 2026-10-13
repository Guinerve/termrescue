from termrescue.install import hook_text, install, uninstall


def test_install_zsh_writes_the_hook_and_sources_it_from_zshrc(tmp_path):
    (tmp_path / ".zshrc").write_text("export EDITOR=vim\n")
    changed = install("zsh", tmp_path)
    assert (tmp_path / ".termrescue.zsh").read_text() == hook_text("zsh")
    rc = (tmp_path / ".zshrc").read_text()
    assert rc.startswith("export EDITOR=vim\n")
    assert "source ~/.termrescue.zsh" in rc
    assert changed == [tmp_path / ".zshrc"]


def test_install_twice_does_not_add_a_second_source_line(tmp_path):
    install("bash", tmp_path)
    install("bash", tmp_path)
    assert (tmp_path / ".bashrc").read_text().count("termrescue.bash") == 1


def test_install_powershell_creates_missing_profiles_and_dot_sources_the_hook(tmp_path):
    ps7 = tmp_path / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    ps5 = tmp_path / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
    ps5.parent.mkdir(parents=True)
    ps5.write_text("Set-PSReadLineOption -EditMode Emacs\n")
    changed = install("powershell", tmp_path, profiles=[ps7, ps5])
    hook = tmp_path / ".termrescue.ps1"
    assert hook.read_text() == hook_text("powershell")
    for profile in (ps7, ps5):
        assert f". '{hook}'" in profile.read_text()
    assert ps5.read_text().startswith("Set-PSReadLineOption")
    assert changed == [ps7, ps5]


def test_uninstall_removes_the_source_line_and_the_hook(tmp_path):
    (tmp_path / ".zshrc").write_text("export EDITOR=vim\n")
    install("zsh", tmp_path)
    uninstall("zsh", tmp_path)
    assert (tmp_path / ".zshrc").read_text() == "export EDITOR=vim\n"
    assert not (tmp_path / ".termrescue.zsh").exists()


def test_cli_install_and_uninstall_use_the_home_directory(tmp_path, monkeypatch, capsys):
    from termrescue.cli import main

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert main(["install", "zsh"]) == 0
    assert "source ~/.termrescue.zsh" in (tmp_path / ".zshrc").read_text()
    assert ".zshrc" in capsys.readouterr().out
    assert main(["uninstall", "zsh"]) == 0
    assert "termrescue" not in (tmp_path / ".zshrc").read_text()


def test_cli_init_prints_the_powershell_hook(capsys):
    from termrescue.cli import main

    assert main(["init", "powershell"]) == 0
    assert capsys.readouterr().out == hook_text("powershell")


def test_install_keeps_windows_line_endings_intact(tmp_path):
    profile = tmp_path / "profile.ps1"
    profile.write_bytes(b"Import-Module posh-git\r\nSet-Alias g git\r\n")
    install("powershell", tmp_path, profiles=[profile])
    data = profile.read_bytes()
    assert b"\r\r\n" not in data
    assert data.startswith(b"Import-Module posh-git")
    uninstall("powershell", tmp_path, profiles=[profile])
    assert b"termrescue" not in profile.read_bytes()


def test_windows_powershell_is_found_at_its_standard_path_when_not_on_path(tmp_path, monkeypatch):
    from termrescue import install as install_module

    exe = tmp_path / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(install_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(install_module.sys, "platform", "win32")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    assert install_module.powershell_executables() == [str(exe)]


def test_install_powershell_fails_loudly_when_no_profile_is_found(tmp_path):
    import pytest

    from termrescue.install import NoPowerShellError

    with pytest.raises(NoPowerShellError):
        install("powershell", tmp_path, profiles=[])


def test_install_into_a_utf16_profile_is_idempotent_and_keeps_the_encoding(tmp_path):
    # Windows PowerShell 5.1 has written UTF-16 profiles by default.
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    profile.write_bytes("Set-Location C:\\code\n".encode("utf-16"))
    install("powershell", tmp_path, profiles=[profile])
    install("powershell", tmp_path, profiles=[profile])
    data = profile.read_bytes()
    assert data[:2] in (b"\xff\xfe", b"\xfe\xff")
    text = data.decode("utf-16")
    assert text.startswith("Set-Location C:\\code")
    assert text.count("termrescue.ps1") == 1


# --- regression tests ---------------------------------------------------------

def test_install_zsh_uses_zdotdir_when_it_is_set(tmp_path, monkeypatch):
    zdotdir = tmp_path / "config" / "zsh"
    monkeypatch.setenv("ZDOTDIR", str(zdotdir))
    changed = install("zsh", tmp_path)
    assert changed == [zdotdir / ".zshrc"]
    assert "source ~/.termrescue.zsh" in (zdotdir / ".zshrc").read_text()
    assert not (tmp_path / ".zshrc").exists()
    assert uninstall("zsh", tmp_path) == [zdotdir / ".zshrc"]
    assert "termrescue" not in (zdotdir / ".zshrc").read_text()


def _on_macos(monkeypatch):
    from termrescue import install as install_module

    monkeypatch.setattr(install_module.sys, "platform", "darwin")


def test_install_bash_on_macos_also_adds_the_existing_bash_profile(tmp_path, monkeypatch):
    # Terminal.app starts login shells, which read ~/.bash_profile and not ~/.bashrc.
    _on_macos(monkeypatch)
    (tmp_path / ".bash_profile").write_text("export PATH=/opt/bin:$PATH\n")
    changed = install("bash", tmp_path)
    assert changed == [tmp_path / ".bashrc", tmp_path / ".bash_profile"]
    assert "termrescue.bash" in (tmp_path / ".bash_profile").read_text()
    assert not (tmp_path / ".profile").exists()
    uninstall("bash", tmp_path)
    assert (tmp_path / ".bash_profile").read_text() == "export PATH=/opt/bin:$PATH\n"


def test_install_bash_on_macos_does_not_create_a_bash_profile_that_hides_profile(
        tmp_path, monkeypatch):
    # A new ~/.bash_profile would stop bash from reading the user's ~/.profile.
    _on_macos(monkeypatch)
    (tmp_path / ".profile").write_text("export LANG=en_AU.UTF-8\n")
    install("bash", tmp_path)
    assert not (tmp_path / ".bash_profile").exists()
    assert "termrescue.bash" in (tmp_path / ".profile").read_text()


def test_the_line_in_profile_is_safe_for_sh_and_loads_the_hook_in_bash(tmp_path, monkeypatch):
    import shutil
    import subprocess
    import sys

    import pytest

    if sys.platform == "win32" or shutil.which("sh") is None or shutil.which("bash") is None:
        pytest.skip("needs a Unix sh and bash")
    _on_macos(monkeypatch)
    (tmp_path / ".profile").write_text("export LANG=en_AU.UTF-8\n")
    install("bash", tmp_path)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    sh = subprocess.run(["sh", "-c", ". ~/.profile && echo ok"], env=env,
                        capture_output=True, text=True, check=False)
    assert (sh.stdout, sh.stderr) == ("ok\n", "")
    bash = subprocess.run(
        ["bash", "--noprofile", "--norc", "-i", "-c", ". ~/.profile; declare -F _termrescue_reset"],
        env=env, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    assert "_termrescue_reset" in bash.stdout


def test_install_bash_on_macos_creates_profile_when_there_is_no_login_file(tmp_path, monkeypatch):
    _on_macos(monkeypatch)
    install("bash", tmp_path)
    assert not (tmp_path / ".bash_profile").exists()
    assert "termrescue.bash" in (tmp_path / ".profile").read_text()


def test_a_users_own_line_ending_in_the_marker_is_neither_skipped_nor_removed(tmp_path):
    mine = "alias tr='termrescue fix'  # termrescue\n"
    (tmp_path / ".zshrc").write_text(mine)
    assert install("zsh", tmp_path) == [tmp_path / ".zshrc"]
    assert "source ~/.termrescue.zsh" in (tmp_path / ".zshrc").read_text()
    uninstall("zsh", tmp_path)
    assert (tmp_path / ".zshrc").read_text() == mine


def test_powershell_line_escapes_typographic_quotes_in_the_home_path(tmp_path):
    # PowerShell ends a single-quoted string at ' and also at ‘ ’ ‚ ‛.
    home = tmp_path / "O’Brien"
    home.mkdir()
    profile = tmp_path / "profile.ps1"
    install("powershell", home, profiles=[profile])
    escaped = str(home / ".termrescue.ps1").replace("’", "’’")
    assert f". '{escaped}'" in profile.read_text(encoding="utf-8")


def test_install_and_uninstall_keep_bytes_that_are_not_utf8(tmp_path):
    # Windows PowerShell profiles saved by older Notepad are often in the ANSI code page.
    profile = tmp_path / "profile.ps1"
    original = b"# Caf\xe9 settings\nSet-Alias g git\n"
    profile.write_bytes(original)
    install("powershell", tmp_path, profiles=[profile])
    assert profile.read_bytes().startswith(original)
    uninstall("powershell", tmp_path, profiles=[profile])
    assert profile.read_bytes() == original


def test_install_keeps_the_files_own_line_endings(tmp_path):
    profile = tmp_path / "profile.ps1"
    profile.write_bytes(b"Import-Module posh-git\r\nSet-Alias g git\r\n")
    install("powershell", tmp_path, profiles=[profile])
    data = profile.read_bytes()
    assert data.count(b"\n") == data.count(b"\r\n") == 3
    unix = tmp_path / ".zshrc"
    unix.write_bytes(b"export EDITOR=vim\n")
    install("zsh", tmp_path)
    assert b"\r" not in unix.read_bytes()


def test_a_powershell_in_the_current_directory_is_never_used(monkeypatch):
    # shutil.which() on Windows searches the current directory before PATH.
    from termrescue import install as install_module

    monkeypatch.setattr(install_module.shutil, "which", lambda name: f".\\{name}.EXE")
    monkeypatch.setattr(install_module.sys, "platform", "linux")
    assert install_module.powershell_executables() == []


def test_cli_install_reports_a_file_it_cannot_write_without_a_traceback(
        tmp_path, monkeypatch, capsys):
    from termrescue import install as install_module
    from termrescue.cli import main

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(tmp_path / ".zshrc"))

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(install_module, "_write", refuse)
    assert main(["install", "zsh"]) == 1
    err = capsys.readouterr().err
    assert ".zshrc" in err and "Permission denied" in err
