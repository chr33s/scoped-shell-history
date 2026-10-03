# Zinit entrypoint; no compilation or downloads occur while loading a shell.
fpath=("${${(%):-%N}:A:h}/shell/completions" $fpath)
source "${${(%):-%N}:A:h}/shell/shistory.zsh"
if (( $+functions[compdef] )); then
  autoload -Uz _shistory
  compdef _shistory shistory
fi
