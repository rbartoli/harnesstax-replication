"""Custom-harness cells: the live configuration, frozen by scripts/snapshot-config.sh,
is placed where each harness reads it inside the container before the stock
Harbor adapter runs.  ``HARNESSTAX_SNAPSHOT`` must point at one snapshot dir.
"""

from __future__ import annotations

import os
from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from .authsync import pull_auth
from .inject import upload_tree
from .pi_codex import PiCodex

_CODEX_HOST_AUTH = Path.home() / ".codex" / "auth.json"


def snapshot_dir() -> Path:
    root = os.environ.get("HARNESSTAX_SNAPSHOT")
    if not root:
        raise RuntimeError(
            "HARNESSTAX_SNAPSHOT must point at a scripts/snapshot-config.sh output dir"
        )
    path = Path(root).expanduser()
    if not (path / "MANIFEST.sha256").exists():
        raise FileNotFoundError(f"not a snapshot dir (no MANIFEST.sha256): {path}")
    return path


class ClaudeCodeCustom(ClaudeCode):
    """Harbor sets CLAUDE_CONFIG_DIR=/logs/agent/sessions; the user-level
    CLAUDE.md, rules, agents, commands, skills, plugins and settings.json go
    there.  Hook scripts referenced as ~/.claude/... go under $HOME/.claude."""

    @staticmethod
    def name() -> str:
        return "claude-code-custom"

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        snap = snapshot_dir() / "claude"
        config_dir = (self.environment_logs_dir / "sessions").as_posix()
        await upload_tree(self, environment, snap / "config", config_dir)
        await upload_tree(self, environment, snap / "home-claude", "$HOME/.claude")
        await super().run(instruction, environment, context)


class CodexWriteback(Codex):
    """Stock Codex adapter plus the refresh-token write-back (used for the
    out-of-the-box cell; behaviour inside the container is unchanged).

    The stock adapter deletes $CODEX_HOME and the secrets dir in its own
    ``finally``, so the pull has to happen just before that cleanup command
    rather than after ``run`` returns."""

    @staticmethod
    def name() -> str:
        return "codex-writeback"

    async def exec_as_agent(self, environment, command, *args, **kwargs):
        if command.startswith("rm -rf ") and "codex-secrets" in command:
            try:
                status = await pull_auth(
                    self, environment, "/tmp/codex-home/auth.json", _CODEX_HOST_AUTH, ("tokens",)
                )
                self.logger.info("Codex auth write-back: %s", status)
            except Exception as exc:
                self.logger.warning("Codex auth write-back failed: %s", exc)
        return await super().exec_as_agent(environment, command, *args, **kwargs)


class CodexCustom(CodexWriteback):
    """Sanitised config.toml goes through Harbor's native ``config`` kwarg;
    AGENTS.md, skills, rules and hooks.json are placed in $CODEX_HOME first."""

    @staticmethod
    def name() -> str:
        return "codex-custom"

    def __init__(self, *args, **kwargs) -> None:
        if kwargs.get("config") is None:
            kwargs["config"] = str(snapshot_dir() / "codex" / "config.toml")
        super().__init__(*args, **kwargs)

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        snap = snapshot_dir() / "codex"
        await upload_tree(
            self, environment, snap / "home", self._REMOTE_CODEX_HOME.as_posix()
        )
        await super().run(instruction, environment, context)


class PiCustom(PiCodex):
    """settings.json, prompts and skills under $HOME/.pi/agent plus the shared
    $HOME/.agents/skills tree, exactly as the host resolves them."""

    @staticmethod
    def name() -> str:
        return "pi-custom"

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        snap = snapshot_dir() / "pi"
        await upload_tree(self, environment, snap / "agent", "$HOME/.pi/agent")
        await upload_tree(self, environment, snap / "agents-skills", "$HOME/.agents/skills")
        await super().run(instruction, environment, context)
