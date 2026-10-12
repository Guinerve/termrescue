# termrescue

> Stop mouse-reporting garbage like `35;45;23M` from flooding your shell after an SSH session dies. Works in PowerShell on Windows, and in zsh and bash on macOS and Linux.

<!-- TODO: hero GIF — wiggle the mouse after killing an SSH session, with and without termrescue -->

## The problem

Programs running over SSH (tmux, vim, htop, Claude Code and so on) switch your **local** terminal into mouse-reporting mode. When the link drops before they can switch it back, your terminal keeps sending every mouse move and click as text, and your shell types it out:

```
PS C:\Users\me> [<35;45;23M[<35;46;23M[<35;47;23M
```

```
READY> 35;45;23M35;46;23Mecho hello
zsh: command not found: 35
```

**On Windows a second thing gets stuck.** `ssh.exe` switches the console into *virtual-terminal input* mode so it can forward escape codes to the remote machine. If it dies without switching back, PowerShell receives the terminal's raw escape codes as if you had typed them. termrescue repairs both.

## What termrescue does

| Piece | What it does |
|---|---|
| **PowerShell hook** (5.1 and 7+) | At every prompt: switches mouse/focus reporting off in Windows Terminal, turns the console's virtual-terminal input back off if a dead program left it on, and drops the garbage that was already queued. Wraps your existing prompt (oh-my-posh, starship), keeping `$LASTEXITCODE`. |
| **zsh hook** | At every prompt: switches mouse and focus reporting off. When the line editor starts, drops reports already queued from the dead session **and keeps what you really typed**. |
| **bash hook** | At every prompt: switches mouse and focus reporting off. |
| `termrescue install` | Sets up the hook for your shell (all installed PowerShell editions on Windows). `termrescue uninstall` removes it. |
| `termrescue fix` | Full manual reset, including leaving the alternate screen and turning off bracketed paste, application cursor keys and the kitty keyboard protocol. |
| `termrescue run -- ssh host` | Runs a command and resets the terminal afterwards, however it exits. |
| `termrescue capture` | Shows exactly what your terminal is sending and decodes it (button, column, row). |
| `termrescue doctor` | Shows which modes are stuck right now, including the Windows console input mode. Exits 1 if anything is stuck. |

The hooks themselves are plain shell or PowerShell, with no Python running at each prompt.

## Install

termrescue is a Python command-line tool, installed with [uv](https://docs.astral.sh/uv/).

### Windows (PowerShell)

```powershell
# 1. Install uv (skip if you have it), then open a new terminal
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Install termrescue from GitHub
uv tool install git+https://github.com/Guinerve/termrescue

# 3. Add the hook to your PowerShell profile(s), then open a new terminal
termrescue install
```

`termrescue install` adds one line to `$PROFILE` for each PowerShell edition it finds. If Windows PowerShell's execution policy would block your profile, it tells you the one command to fix that. If you use oh-my-posh or starship, keep the termrescue line **after** theirs.

### macOS / Linux

```sh
uv tool install git+https://github.com/Guinerve/termrescue
termrescue install          # zsh or bash, detected from $SHELL
```

### Recommended SSH settings

In `~/.ssh/config` (on Windows: `C:\Users\<you>\.ssh\config`), so a dead link exits after ~45 s instead of hanging:

```
Host *
  ServerAliveInterval 15
  ServerAliveCountMax 3
```

A hung SSH session can be killed at once by typing `~.` on a new line.

## When it happens: diagnose

```powershell
termrescue doctor     # what's stuck right now
termrescue capture    # wiggle the mouse, press q: shows exactly what the terminal sends
termrescue fix        # repair it by hand
```

## How it works

DEC private modes are switched on with `ESC [ ? n h` and off with `ESC [ ? n l`. Mouse reporting uses modes 9, 1000–1003 and 1005/1006/1015/1016 (different tracking levels and encodings), and focus reporting uses 1004. Every hook sends the "off" sequence for all of them at each prompt. That's safe because no program is running at a prompt, so nothing should be reporting.

**Windows:** the PowerShell hook also reads the console input mode with `GetConsoleMode`. If `ENABLE_VIRTUAL_TERMINAL_INPUT` (0x200) is set, it clears it and flushes the queued input. The small native helper is compiled on the second prompt rather than at startup, so it doesn't slow down opening a terminal.

**zsh:** reports the terminal sent *before* the reset are already waiting in the input queue. A `line-init` widget (chained with `add-zle-hook-widget`, so other plugins keep working) reads what's pending, strips the mouse and focus reports, and pushes the rest back with `zle -U` so real typeahead, including arrow keys, behaves normally.

## How I know it's right

CI runs on **Windows, macOS and Linux**.

- **Windows:** each integration test opens a brand-new console, breaks it the way a dying `ssh.exe` does, then checks the repair. One test uses `termrescue fix`. Another runs the PowerShell hook in both **Windows PowerShell 5.1 and PowerShell 7**, also checking that the user's own prompt and `$LASTEXITCODE` survive and that loading the hook twice is harmless.
- **zsh and bash:** the tests drive real interactive shells inside a pseudo-terminal. A program enables mouse reporting and is killed with `kill -9`, and the next prompt must send the reset. Queued mouse reports followed by `echo kept` must run exactly `echo kept`. Without termrescue, zsh runs `35` and `23Mecho` as commands, and the test reproduces that.
- `doctor` is tested by playing the terminal's side of the DECRQM conversation, including a terminal that never answers.
- `install` is tested for idempotence, UTF-16 profiles and Windows line endings.
- The escape sequences in every hook are checked against the Python source of truth, so they can't drift apart.

```sh
uv run pytest -v -rs
```

## Limits

- cmd.exe isn't covered; use PowerShell, or run `termrescue fix`.
- The bash hook doesn't drop reports already queued; bash has no line-init hook to do it in.
- `doctor`'s terminal-mode table depends on DECRQM. Terminals that don't support it are reported as "unknown", not guessed. The Windows console input check doesn't depend on it.
- Terminal support has not yet been verified by hand. Planned: Windows Terminal, iTerm2, Ghostty, Terminal.app, kitty, WezTerm.

## Roadmap

- fish hook
- Winget/Scoop and Homebrew packages
- Hand-verified terminal support table
- Hero GIF
