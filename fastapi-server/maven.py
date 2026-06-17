"""Locate the Maven executable.

Single source of truth for both ``server.py`` and ``pipeline.py``. The command
is resolved from the ``MAVEN_CMD`` environment variable when set, otherwise from
``PATH`` (``mvn.cmd`` on Windows, ``mvn`` elsewhere). No machine-specific paths
are hardcoded — configure ``MAVEN_CMD`` or put Maven on ``PATH``.
"""
import os
import shutil


def maven_executable() -> str:
    """Return the Maven command to invoke."""
    configured = os.getenv("MAVEN_CMD")
    if configured:
        return configured
    return shutil.which("mvn.cmd") or shutil.which("mvn") or "mvn"
