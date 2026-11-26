#!/usr/bin/env python3
"""Download the pinned Litestream binary next to the current interpreter.

On PyPI the binary is injected into platform-specific wheels, so a source
checkout has no `litestream` executable. CI uses this script so the CLI drift
tests in `tests/test_litestream.py` run against the real binary instead of
being skipped.

Usage:
    python scripts/install_binary.py [--dest PATH] [--force]
"""

from __future__ import annotations

import argparse
import platform
import sys
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

sys.path.insert(0, str(SCRIPTS_DIR))

from build_binaries import (  # noqa: E402
    VERSION,
    _extract_archive,
    _litestream_binary_name,
    _litestream_url,
)

# Map `platform.machine()` values onto the upstream release asset names.
MACHINES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

SYSTEMS = {
    "linux": "linux",
    "darwin": "darwin",
    "win32": "windows",
}


def _release_target() -> tuple[str, str] | None:
    system = SYSTEMS.get(sys.platform)
    arch = MACHINES.get(platform.machine().lower())
    if system is None or arch is None:
        return None
    return system, arch


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the pinned Litestream binary"
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path(sys.executable).parent,
        help="Directory to install the binary into (default: the current venv's bin/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when the destination already exists.",
    )
    args = parser.parse_args()

    target = _release_target()
    if target is None:
        print(
            f"Unsupported platform: {sys.platform}/{platform.machine()}. "
            "Skipping binary download.",
            file=sys.stderr,
        )
        return 0

    system, arch = target
    binary_name = _litestream_binary_name(system)
    dest = args.dest / binary_name

    if dest.exists() and not args.force:
        print(f"{dest} already exists, skipping download.")
        return 0

    url = _litestream_url(system, arch)
    print(f"Downloading {url} ...")
    with urllib.request.urlopen(url) as response:
        data = response.read()

    binary = _extract_archive(data, binary_name, system == "windows")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(binary)
    if system != "windows":
        dest.chmod(0o755)

    print(f"Installed litestream {VERSION} at {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
