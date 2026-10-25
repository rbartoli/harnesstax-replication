#!/usr/bin/env bash
# The six cells. Usage: scripts/cells.sh <cell> <harbor target args...>
#   cell   ∈ oob-pi oob-codex oob-cc custom-pi custom-codex custom-cc
#   target  e.g.  -d terminal-bench@2.0 --job-name oob-pi-main   or   -p tasks/calib-ok --job-name x
# Mirrors HarnessTax (harnesstax.github.io, Experiment Setup): native configuration, high effort,
# 100-turn cap (Claude Code --max-turns; Pi via the turn-cap extension; Codex post hoc), the
# paper's harness versions (Pi 0.85.1, Codex 0.146.0, Claude Code 2.1.224), Terminal-Bench's own
# task time caps (no multiplier), web tools at native defaults (the paper disabled them for
# SWE-bench Lite only). Ours: concurrency 1, memory gate ≥ 8 GB, exclusions in tasks/tb2-exclude.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=$PWD
OUT=${HARNESSTAX_JOBS:-$HOME/harnesstax-runs/jobs}
cell=${1:?cell name}; shift

avail=$(awk '/MemAvailable/{print int($2/1024/1024)}' /proc/meminfo)
(( avail >= 8 )) || { echo "memory gate: only ${avail} GB available (need 8)" >&2; exit 2; }
case $cell in custom-*) : "${HARNESSTAX_SNAPSHOT:?custom cells need HARNESSTAX_SNAPSHOT=<snapshot dir>}";; esac

EXCLUDE=()
while read -r t; do [[ -z $t || $t == \#* ]] && continue; EXCLUDE+=(-x "$t"); done < tasks/tb2-exclude.txt
COMMON=(-n 1 -o "$OUT" "${EXCLUDE[@]}" "$@")

PI=(-m openai-codex/gpt-5.6-sol --ak version=0.85.1 --ak thinking=high)
CODEX=(-m openai/gpt-5.6-sol --ak version=0.146.0 --ak reasoning_effort=high)
CC=(-m anthropic/claude-sonnet-4-6 --ak version=2.1.224 --ak reasoning_effort=high --ak max_turns=100)

claude_token() {  # a Claude subscription token from `claude setup-token`, passed in the environment
  : "${CLAUDE_CODE_OAUTH_TOKEN:?Claude Code cells need CLAUDE_CODE_OAUTH_TOKEN (from claude setup-token)}"
  export CLAUDE_CODE_OAUTH_TOKEN CLAUDE_FORCE_OAUTH=1
}

case $cell in
  oob-pi)       exec harbor run -a agents.pi_codex:PiCodex       "${PI[@]}"    "${COMMON[@]}" ;;
  custom-pi)    exec harbor run -a agents.custom:PiCustom        "${PI[@]}"    "${COMMON[@]}" ;;
  oob-codex)    export CODEX_FORCE_AUTH_JSON=1
                exec harbor run -a agents.custom:CodexWriteback  "${CODEX[@]}" "${COMMON[@]}" ;;
  custom-codex) export CODEX_FORCE_AUTH_JSON=1
                exec harbor run -a agents.custom:CodexCustom     "${CODEX[@]}" "${COMMON[@]}" ;;
  oob-cc)       claude_token
                exec harbor run -a claude-code                   "${CC[@]}"    "${COMMON[@]}" ;;
  custom-cc)    claude_token
                exec harbor run -a agents.custom:ClaudeCodeCustom "${CC[@]}"   "${COMMON[@]}" ;;
  *) echo "unknown cell: $cell" >&2; exit 1 ;;
esac
