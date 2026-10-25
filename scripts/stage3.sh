#!/usr/bin/env bash
# Stage 3 driver: 30 tasks × 3 runs × 6 cells, tasks over repeats (run 1 complete before run 2),
# one Harbor job per trial, resumable, quota-paced on both subscriptions.
# Usage: HARNESSTAX_SNAPSHOT=<dir> scripts/stage3.sh [tag]   (detach with setsid nohup)
set -uo pipefail
cd "$(dirname "$0")/.."
tag=${1:-s3}; : "${HARNESSTAX_SNAPSHOT:?}"
JOBS=${HARNESSTAX_JOBS:-$HOME/harnesstax-runs/jobs}; log=$HOME/harnesstax-runs/$tag.log
CELLS=(oob-codex oob-pi custom-codex custom-pi oob-cc custom-cc)   # Codex before Pi: Pi reports no limits; 5h threshold low because Pi trials spend the window unseen
CHATGPT_5H_MAX=70; CLAUDE_5H_MAX=85; CLAUDE_7D_MAX=80; CHATGPT_7D_MAX=90
RESET_MARK=$HOME/harnesstax-runs/chatgpt-reset   # touch after spending a manual reset on chatgpt.com: readings from older rollouts are ignored
say() { echo "$(date -Is) $*" | tee -a "$log"; }

latest_file() { ls -t "$JOBS"/$tag-*-$1-*/*/agent/$2 2>/dev/null | head -1; }
chatgpt_limits() {  # -> "used5h used7d resets5h resets7d" from the newest Codex rollout that carries figures (a rollout that died on the limit has none)
  local f r
  for f in $(ls -t "$JOBS"/$tag-*-*codex-*/*/agent/sessions/*/*/*/rollout-*.jsonl 2>/dev/null | head -8); do
    [ -e "$RESET_MARK" ] && [ ! "$f" -nt "$RESET_MARK" ] && break
    r=$(jq -r 'select(.type=="event_msg" and .payload.type=="token_count") | .payload.rate_limits | select(. != null and .primary != null) | "\(.primary.used_percent // 0) \(.secondary.used_percent // 0) \(.primary.resets_at // 0) \(.secondary.resets_at // 0)"' "$f" | tail -1)
    [ -n "$r" ] && { echo "$r"; return; }
  done
  echo "0 0 0 0"
}
claude_limits() {   # -> "used5h used7d resets5h resets7d" from the newest Claude Code stream
  local f; f=$(ls -t "$JOBS"/$tag-*-*cc-*/*/agent/claude-code.txt 2>/dev/null | head -1)
  [ -n "$f" ] || { echo "0 0 0 0"; return; }
  jq -r 'select(.type=="rate_limit_event") | .rate_limit_info.unifiedWindows | "\((.five_hour.utilization // 0)*100|floor) \((.seven_day.utilization // 0)*100|floor) \(.five_hour.resetsAt // 0) \(.seven_day.resetsAt // 0)"' "$f" | tail -1
}
QUOTA_HIT='hit your [a-z ]*limit|usage limit'   # text Claude Code prints when the subscription window is exhausted
claude_blocked() {  # -> resetsAt when the newest Claude Code stream reports a quota hit (2.1.224 streams carry no utilization), else empty
  local f; f=$(ls -t "$JOBS"/$tag-*-*cc-*/*/agent/claude-code.txt 2>/dev/null | head -1)
  [ -n "$f" ] || return 0
  /usr/bin/grep -qiE "$QUOTA_HIT" "$f" || return 0
  jq -r 'select(.type=="rate_limit_event") | .rate_limit_info.resetsAt // empty' "$f" | tail -1
}
wait_for_quota() {  # $1 = account (chatgpt|claude); a reading whose reset time has passed is stale, the window is clear
  while :; do
    local r u5 u7 r5 r7 max5 max7 b
    if [ "$1" = claude ]; then b=$(claude_blocked); if [ -n "$b" ] && [ "$b" -gt "$(date +%s)" ]; then say "PAUSE claude: rate limit rejected, until $(date -d @$b -Is)"; sleep $(( b - $(date +%s) + 60 )); continue; fi; fi
    if [ "$1" = chatgpt ]; then r=$(chatgpt_limits); max5=$CHATGPT_5H_MAX; max7=$CHATGPT_7D_MAX; else r=$(claude_limits); max5=$CLAUDE_5H_MAX; max7=$CLAUDE_7D_MAX; fi
    read -r u5 u7 r5 r7 <<<"$r"; u5=${u5%.*}; u7=${u7%.*}
    if [ "${u5:-0}" -ge "$max5" ] && [ "${r5:-0}" -gt "$(date +%s)" ]; then say "PAUSE $1 5h window at ${u5}% ≥ ${max5}%, until $(date -d @$r5 -Is 2>/dev/null)"; sleep $(( r5 - $(date +%s) > 60 ? r5 - $(date +%s) + 60 : 900 )); continue; fi
    if [ "${u7:-0}" -ge "$max7" ] && [ "${r7:-0}" -gt "$(date +%s)" ]; then say "PAUSE $1 weekly window at ${u7}% ≥ ${max7}% — needs a decision; polling hourly"; t0=$(date +%s); for _ in $(seq 60); do sleep 60; [ "$(stat -c %Y "$RESET_MARK" 2>/dev/null || echo 0)" -ge "$t0" ] && break; done; continue; fi
    return
  done
}
trial_done() {  # a trial counts when it has a result with no exception or an agent timeout; Claude trials also count when Claude Code
  # finished its own run and died (e.g. "Prompt is too long"): Harbor labels those ApiRateLimitError because its rate-limit regex matches
  # the rate_limit_event lines every Claude Code stream carries. A real quota hit is redone after the pause.
  local d=$1 r f exc; r=$(ls "$d"/*/result.json 2>/dev/null | head -1); [ -n "$r" ] || return 1
  exc=$(jq -r '.exception_info.exception_type // "-"' "$r")
  [ "$(jq -r '.verifier_result.rewards.reward // 0' "$r")" = "1.0" ] && return 0   # verified solve: never redone, whatever happened after
  case $exc in -|AgentTimeoutError) return 0;; esac
  case $d in *-cc-*)
    f=$(ls "$d"/*/agent/claude-code.txt 2>/dev/null | head -1); [ -n "$f" ] || return 1
    /usr/bin/grep -qiE "$QUOTA_HIT" "$f" && return 1
    /usr/bin/grep -q '"type":"result"' "$f" && return 0;;   # Claude Code ended its own run (prompt too long, 32k output cap, …): a failed attempt
  esac
  return 1
}

say "STAGE3 START tag=$tag snapshot=$HARNESSTAX_SNAPSHOT"
for run in 1 2 3; do
  for pass in 1 2 3; do   # pass 1 runs everything; later passes redo trials that died with an exception
    while read -r task; do
      [[ -z $task || $task == \#* ]] && continue
      for cell in "${CELLS[@]}"; do
        job="$tag-r$run-$cell-$task"; dir="$JOBS/$job"
        if trial_done "$dir"; then continue; fi
        if [ -d "$dir" ]; then mv "$dir" "$dir.failed-$(date +%s)"; say "RETRY $job (previous attempt had an exception)"; fi
        case $cell in *codex|*pi) wait_for_quota chatgpt;; *cc) wait_for_quota claude;; esac
        say "--- $job"
        while :; do
          scripts/cells.sh "$cell" -d terminal-bench@2.0 -i "$task" --job-name "$job" >> "$log" 2>&1; rc=$?
          [ $rc -eq 2 ] && { say "memory gate: waiting 5 min"; sleep 300; continue; }
          break
        done
        exc=$(jq -r '.exception_info.exception_type // "-"' "$dir"/*/result.json 2>/dev/null | head -1)
        say "EXIT $job rc=$rc reward=$(jq -r '.verifier_result.rewards.reward // "none"' "$dir"/*/result.json 2>/dev/null | head -1) exc=${exc:--}"
        trial_done "$dir" || { say "BACKOFF 2 min after $exc"; sleep 120; }
      done
    done < tasks/stage3-tasks.txt
  done
  left=$(for d in "$JOBS"/$tag-r$run-*; do [ -d "$d" ] && [[ $d != *.failed-* ]] && ! trial_done "$d" && echo x; done | wc -l)
  [ "$left" -eq 0 ] && say "RUN $run COMPLETE" || say "RUN $run INCOMPLETE: $left trials still end in an exception after 3 passes"
done
say "STAGE3 DONE"
