#!python3
"""Runs downstream projects tests with current code from compat injected in them."""

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from subprocess import run  # noqa: S404

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger()


parent_project_dir = Path(__file__).parent.parent.resolve().as_posix()
checksum = hashlib.sha256(parent_project_dir.encode("utf-8")).hexdigest()[:4]
tmp_path = Path(tempfile.gettempdir()) / f"ansible-compat-smoke-{checksum}"

logger.info("Using %s temporary directory...", tmp_path)

for project in ("molecule", "ansible-lint"):

    logger.info("Running tests for %s", project)
    project_dir = tmp_path / project
    if (project_dir / ".git").exists():
        run(["git", "-C", project_dir, "pull"], check=True)
    else:
        project_dir.mkdir(parents=True, exist_ok=True)
        run(
            [
                "git",
                "clone",
                "--recursive",
                f"https://github.com/ansible/{project}",
                project_dir,
            ],
            check=True,
        )

    os.chdir(project_dir)
    venv_dir = (project_dir / ".venv").as_posix()
    os.environ["VIRTUAL_ENV"] = venv_dir
    run(
        ["uv", "venv", "--seed", venv_dir],
        check=True,
    )  # creates .venv (implicit for next commands)
    run(
        ["uv", "pip", "install", "-e", f"{parent_project_dir}[test]", "-e", ".[test]"],
        check=True,
    )
    run(["uv", "pip", "freeze"], check=True)
    run(["uv", "run", "pytest", "-v", "-n", "auto"], check=True)
