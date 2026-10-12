# termrescue for PowerShell (Windows PowerShell 5.1 and PowerShell 7+): clear
# terminal modes left on by programs that died, e.g. ssh.exe when the link drops.
#
#   . "$HOME\.termrescue.ps1"
#
# `termrescue install powershell` adds that line to your profile. Keep it after
# anything else that defines `prompt` (oh-my-posh, starship): it wraps whatever
# prompt exists when it loads.

if ($global:TermRescueOriginalPrompt) { return }   # already loaded

$e = [char]27
# Mouse modes 9 1000 1001 1002 1003 1005 1006 1015 1016 off, focus reporting
# (1004) off, cursor visible. Keep in sync with termrescue.sequences.PROMPT_RESET.
$global:TermRescueReset = "$e[?9l$e[?1000l$e[?1001l$e[?1002l$e[?1003l$e[?1005l$e[?1006l$e[?1015l$e[?1016l$e[?1004l$e[?25h"
Remove-Variable e

$global:TermRescuePromptCount = 0

function global:Repair-TermRescueConsole {
    # 1. Switch mouse and focus reporting off in the terminal (Windows Terminal etc.).
    if ($Host.UI.SupportsVirtualTerminal) { [Console]::Write($global:TermRescueReset) }

    # 2. Switch the console's virtual-terminal input back off. ssh.exe turns it on
    #    and doesn't turn it off if it dies, so PowerShell reads escape codes as typing.
    if ($PSVersionTable.PSVersion.Major -ge 6 -and -not $IsWindows) { return }
    if (-not ('TermRescue.Native' -as [type])) {
        # Compiling this helper takes a moment, so wait until after the first
        # command instead of slowing down shell startup.
        if ($global:TermRescuePromptCount -lt 2) { return }
        Add-Type -Namespace TermRescue -Name Native -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int nStdHandle);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr hConsole, out uint mode);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr hConsole, uint mode);
[DllImport("kernel32.dll")] public static extern bool FlushConsoleInputBuffer(IntPtr hConsole);
'@
    }
    $handle = [TermRescue.Native]::GetStdHandle(-10)
    $mode = [uint32]0
    if (-not [TermRescue.Native]::GetConsoleMode($handle, [ref]$mode)) { return }
    if ($mode -band 0x200) {
        [void][TermRescue.Native]::SetConsoleMode($handle, [uint32]($mode -bxor 0x200))
        # Drop the mouse reports the dead session left queued.
        [void][TermRescue.Native]::FlushConsoleInputBuffer($handle)
    }
}

$global:TermRescueOriginalPrompt = $function:prompt
function global:prompt {
    $exitCode = $global:LASTEXITCODE
    $global:TermRescuePromptCount++
    try { Repair-TermRescueConsole } catch { }
    $global:LASTEXITCODE = $exitCode
    & $global:TermRescueOriginalPrompt
}
