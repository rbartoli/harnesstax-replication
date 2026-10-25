"""Upload a host directory tree into the trial container.

Harbor only exposes ``environment.upload_file``; a tarball keeps symlink-free
snapshots intact and costs one copy per trial.  ``remote_dir`` is expanded by
the container shell, so ``$HOME`` is allowed there.
"""

from __future__ import annotations

import shlex
import tarfile
import tempfile
import uuid
from pathlib import Path

from harbor.environments.base import BaseEnvironment


async def upload_tree(
    agent, environment: BaseEnvironment, local_dir: Path | str, remote_dir: str
) -> None:
    local_dir = Path(local_dir)
    if not local_dir.is_dir():
        raise FileNotFoundError(f"snapshot tree missing: {local_dir}")
    with tempfile.TemporaryDirectory(prefix="harnesstax-inject-") as tmp:
        tgz = Path(tmp) / "tree.tgz"
        with tarfile.open(tgz, "w:gz") as tar:
            tar.add(local_dir, arcname=".")
        staged = f"/tmp/harnesstax-{uuid.uuid4().hex}.tgz"
        await environment.upload_file(tgz, staged)
        if environment.default_user is not None:
            await agent.exec_as_root(
                environment,
                command=f"chown {environment.default_user} {shlex.quote(staged)}",
            )
        await agent.exec_as_agent(
            environment,
            command=(
                f"mkdir -p {remote_dir} && tar -xzf {shlex.quote(staged)} -C {remote_dir}"
                f" && rm -f {shlex.quote(staged)}"
            ),
        )
