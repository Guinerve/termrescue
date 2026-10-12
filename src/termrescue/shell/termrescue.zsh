# termrescue for zsh: clear terminal modes left on by programs that died,
# e.g. a remote tmux or vim when the SSH link drops.
#
#   source /path/to/termrescue.zsh      (or: eval "$(termrescue init zsh)")

[[ -o interactive ]] || return 0

# Mouse modes 9 1000 1001 1002 1003 1005 1006 1015 1016 off, focus reporting
# (1004) off, cursor visible. Keep in sync with termrescue.sequences.PROMPT_RESET.
typeset -g _termrescue_reset=$'\e[?9l\e[?1000l\e[?1001l\e[?1002l\e[?1003l\e[?1005l\e[?1006l\e[?1015l\e[?1016l\e[?1004l\e[?25h'

# 1. Before every prompt, switch the modes off so the terminal stops sending reports.
_termrescue_precmd() {
  print -rn -- "$_termrescue_reset"
}

# 2. When the line editor starts, drop any reports that were already queued
#    (sent while the dead program's link was stalling) and keep real typeahead.
_termrescue_drain() {
  emulate -L zsh
  setopt extendedglob
  local pending= key
  while read -t 0 -k 1 key; do
    pending+=$key
  done
  [[ -n $pending ]] || return 0
  local esc=$'\e'
  pending=${pending//${esc}\[\<[0-9]##\;[0-9]##\;[0-9]##[Mm]/}    # SGR mouse
  pending=${pending//${esc}\[[0-9]##\;[0-9]##\;[0-9]##M/}         # urxvt mouse
  pending=${pending//${esc}\[M???/}                               # X10 mouse
  pending=${pending//${esc}\[[IO]/}                               # focus in/out
  [[ -n $pending ]] && zle -U -- "$pending"
  return 0
}

autoload -Uz add-zsh-hook add-zle-hook-widget
add-zsh-hook precmd _termrescue_precmd
zle -N _termrescue_drain
add-zle-hook-widget line-init _termrescue_drain
