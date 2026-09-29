"""Compile a lab's Bicep with the local Bicep CLI (never deploys). Tests skip when no CLI exists."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_bicep() -> str | None:
    found = shutil.which("bicep")
    if found:
        return found
    home = Path(os.path.expanduser("~/.azure/bin/bicep"))
    return str(home) if home.exists() else None


def build(main_bicep: Path) -> subprocess.CompletedProcess:
    exe = find_bicep()
    if exe is None:
        raise FileNotFoundError("bicep CLI not found")
    return subprocess.run(
        [exe, "build", str(main_bicep), "--stdout"], capture_output=True, text=True, timeout=180
    )
