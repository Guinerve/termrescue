# termrescue for bash: clear terminal modes left on by programs that died,
# e.g. a remote tmux or vim when the SSH link drops.
#
#   source /path/to/termrescue.bash     (or: eval "$(termrescue init bash)")
#
# Source it at the end of ~/.bashrc, after anything else that sets PROMPT_COMMAND.

[[ $- == *i* ]] || return 0

# Mouse modes 9 1000 1001 1002 1003 1005 1006 1015 1016 off, focus reporting
# (1004) off, cursor visible. Keep in sync with termrescue.sequences.PROMPT_RESET.
# It runs first in PROMPT_COMMAND, so it hands the last exit status on unchanged
# for prompt themes that read $?.
_termrescue_reset() {
  local status=$?
  printf '\033[?9l\033[?1000l\033[?1001l\033[?1002l\033[?1003l\033[?1005l\033[?1006l\033[?1015l\033[?1016l\033[?1004l\033[?25h'
  return $status
}

case ";${PROMPT_COMMAND};" in
  *";_termrescue_reset;"*) ;;
  *) PROMPT_COMMAND="_termrescue_reset${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
esac
