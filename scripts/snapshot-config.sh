#!/usr/bin/env bash
# Freeze a sanitised, symlink-free copy of the live harness configs for the custom cells.
# Usage: scripts/snapshot-config.sh [YYYY-MM-DD]   → ~/harnesstax-runs/snapshot/<date>/
# Dropped on purpose (listed in the README): statusLine, model/subagent-model pins,
# Codex mcp_servers/projects/hooks.state/model keys, every auth/credential file, blobs > 1 MiB.
set -euo pipefail
STAMP=${1:-$(date +%F)}
OUT=${HARNESSTAX_SNAPSHOT_ROOT:-$HOME/harnesstax-runs/snapshot}/$STAMP
PY=$HOME/.local/share/uv/tools/harbor/bin/python   # Harbor's venv has the toml package
REMOTE_CLAUDE_CONFIG_DIR=/logs/agent/sessions        # fixed by Harbor's claude-code adapter
MAXBLOB=1M

rm -rf "$OUT"; mkdir -p "$OUT"
copy_tree() { # src dst — dereference symlinks, skip VCS/caches and large blobs
  [ -d "$1" ] || { echo "skip (missing): $1"; return 0; }
  mkdir -p "$2"
  rsync -aqL --exclude .git --exclude node_modules --exclude __pycache__ --exclude .venv \
    --max-size="$MAXBLOB" "$1/" "$2/" || [ $? -eq 23 ]   # 23 = dangling symlinks skipped, as the harness itself does
  find -L "$1" -type f -size +"$MAXBLOB" -not -path '*/.git/*' -not -path '*/node_modules/*' \
    -printf 'dropped blob: %p (%s bytes)\n' || true
}

# --- Claude Code ------------------------------------------------------------
C=$OUT/claude/config; mkdir -p "$C"
cp ~/.claude/CLAUDE.md "$C/CLAUDE.md"
copy_tree ~/.claude/rules    "$C/rules"
copy_tree ~/.claude/agents   "$C/agents"
copy_tree ~/.claude/commands "$C/commands"
copy_tree ~/.claude/skills   "$C/skills"
copy_tree ~/.claude/plugins  "$C/plugins"
# plugin registry files carry absolute host paths
find "$C/plugins" -maxdepth 1 -name '*.json' -exec sed -i "s#$HOME/.claude/plugins#$REMOTE_CLAUDE_CONFIG_DIR/plugins#g" {} +
jq 'del(.statusLine, .model, .modelSettings, .env.CLAUDE_CODE_SUBAGENT_MODEL,
        .worktree, .voice, .voiceEnabled, .tui, .preferredNotifChannel, .feedbackSurveyState)' \
  ~/.claude/settings.json > "$C/settings.json"
HC=$OUT/claude/home-claude; mkdir -p "$HC/scripts"
copy_tree ~/.claude/scripts/hooks "$HC/scripts/hooks"
copy_tree ~/.claude/hooks         "$HC/hooks"

# --- Codex CLI --------------------------------------------------------------
X=$OUT/codex; mkdir -p "$X/home"
cp ~/.codex/AGENTS.md "$X/home/AGENTS.md"
cp ~/.codex/hooks.json "$X/home/hooks.json"
copy_tree ~/.codex/skills "$X/home/skills"
copy_tree ~/.codex/rules  "$X/home/rules"
"$PY" - > "$X/config.toml" <<'PYEOF'
import toml, pathlib
c = toml.load(pathlib.Path.home() / ".codex" / "config.toml")
for k in ("mcp_servers", "projects", "hooks", "tui", "notice", "model", "model_reasoning_effort"):
    c.pop(k, None)
print(toml.dumps(c), end="")
PYEOF

# --- Pi ---------------------------------------------------------------------
P=$OUT/pi; mkdir -p "$P/agent" "$P/agents-skills"
cp ~/.pi/agent/settings.json "$P/agent/settings.json"
copy_tree ~/.pi/agent/prompts "$P/agent/prompts"
copy_tree ~/.pi/agent/skills  "$P/agent/skills"
copy_tree ~/.agents/skills    "$P/agents-skills"

# --- manifest + secret scan ------------------------------------------------
( cd "$OUT" && find . -type f -not -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum ) > "$OUT/MANIFEST.sha256"
echo "snapshot: $OUT"
echo "manifest sha256: $(sha256sum "$OUT/MANIFEST.sha256" | cut -c1-16)…  files: $(wc -l < "$OUT/MANIFEST.sha256")  size: $(du -sh "$OUT" | cut -f1)"
if /usr/bin/grep -rIl -E '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|op://|xox[bp]-|AKIA[0-9A-Z]{16})' "$OUT" --exclude=MANIFEST.sha256 | head; then
  echo "WARNING: credential-looking strings above — review before use" >&2
fi
echo "codex config.toml kept keys: $("$PY" -c "import toml,sys;print(sorted(toml.load('$X/config.toml')))")"
