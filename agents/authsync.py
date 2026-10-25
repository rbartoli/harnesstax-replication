"""Write a refreshed OAuth file from the container back to the host.

Codex and Pi hold single-use refresh tokens. If a trial refreshes inside the
container, the host copy is dead for the next trial unless it is copied back.
Only well-formed JSON with the expected top-level keys is written; the previous
file is kept as a 0600 backup next to it.
"""

from __future__ import annotations

import json
import os
import shlex
import tempfile
import time
from pathlib import Path


async def pull_auth(agent, environment, remote_path: str, host_path: Path, required_keys: tuple[str, ...]) -> str:
    """Copy ``remote_path`` (shell-expanded in the container) over ``host_path`` if it changed."""
    staged = f"/tmp/harnesstax-auth-out-{os.getpid()}.json"
    await agent.exec_as_agent(
        environment,
        command=f"cp -L {remote_path} {shlex.quote(staged)} && chmod 644 {shlex.quote(staged)}",  # -L: Codex replaces a symlinked auth.json with a real file on refresh
    )
    with tempfile.TemporaryDirectory(prefix="harnesstax-auth-") as tmp:
        local = Path(tmp) / "auth.json"
        await environment.download_file(staged, local)
        text = local.read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return "ignored: container auth.json is not JSON"
    if not isinstance(data, dict) or not all(k in data for k in required_keys):
        return "ignored: container auth.json lacks expected keys"
    if host_path.read_text() == text:
        return "unchanged"
    backup = host_path.with_name(f"{host_path.name}.bak-{time.strftime('%Y%m%dT%H%M%S')}")
    backup.write_text(host_path.read_text()); backup.chmod(0o600)
    tmp_path = host_path.with_name(host_path.name + ".tmp")
    tmp_path.write_text(text); tmp_path.chmod(0o600); tmp_path.replace(host_path)
    return f"refreshed (backup {backup.name})"
