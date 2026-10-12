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
