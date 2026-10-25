"""Pi on the ChatGPT subscription (``openai-codex`` provider) inside Harbor.

Harbor's stock Pi adapter only knows API-key providers.  This subclass stages
the host ``~/.pi/agent/auth.json`` into the container, installs the HarnessTax
turn-cap extension, runs the stock adapter, then copies a refreshed auth file
back to the host (single-use refresh tokens).
"""

from __future__ import annotations

import os
from pathlib import Path

from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from .authsync import pull_auth

_HOST_AUTH = Path.home() / ".pi" / "agent" / "auth.json"
_REMOTE_DIR = "$HOME/.pi/agent"
_TURN_CAP_TMPL = Path(__file__).with_name("turn_cap.ts.tmpl")


class PiCodex(Pi):
    @staticmethod
    def name() -> str:
        return "pi-codex"

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        if not _HOST_AUTH.exists():
            raise FileNotFoundError(f"host Pi auth file missing: {_HOST_AUTH}")
        staged = "/tmp/pi-auth.json"
        await self._upload_config_text(
            environment, content=_HOST_AUTH.read_text(), remote_path=staged, filename="auth.json"
        )
        max_turns = int(os.environ.get("HARNESSTAX_PI_MAX_TURNS", "100"))
        cap_src = _TURN_CAP_TMPL.read_text().replace("__MAX_TURNS__", str(max_turns))
        await self._upload_config_text(
            environment, content=cap_src, remote_path="/tmp/turn-cap.ts", filename="turn-cap.ts"
        )
        await self.exec_as_agent(
            environment,
            command=(
                f"mkdir -p {_REMOTE_DIR}/extensions && chmod 700 {_REMOTE_DIR} && "
                f"mv {staged} {_REMOTE_DIR}/auth.json && chmod 600 {_REMOTE_DIR}/auth.json && "
                f"mv /tmp/turn-cap.ts {_REMOTE_DIR}/extensions/turn-cap.ts"
            ),
        )
        try:
            await super().run(instruction, environment, context)
        finally:
            try:
                status = await pull_auth(
                    self, environment, f"{_REMOTE_DIR}/auth.json", _HOST_AUTH, ("openai-codex",)
                )
                self.logger.info("Pi auth write-back: %s", status)
            except Exception as exc:  # never fail the trial over the write-back
                self.logger.warning("Pi auth write-back failed: %s", exc)
