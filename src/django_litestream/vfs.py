# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sqlite3
import threading
from django_litestream.conf import app_settings
from django_litestream.management.commands.litestream import (
    download_vfs_extension,
)

# Module-level state for tracking VFS extension loading
_vfs_loaded = False
_vfs_load_lock = threading.Lock()


def ensure_vfs_loaded() -> None:
    """
    Ensure the Litestream VFS extension is loaded exactly once per process.

    This function is thread-safe and uses double-checked locking to ensure
    the extension is loaded only once even with concurrent calls.

    The VFS extension registers a global VFS handler in the SQLite library
    for this process. Once registered, all connections in this process can
    use vfs=litestream without reloading the extension.

    Automatically downloads the extension if it's missing.

    Raises:
        RuntimeError: If the extension fails to load
    """
    global _vfs_loaded

    if _vfs_loaded:
        return

    with _vfs_load_lock:
        if _vfs_loaded:
            return

        vfs_extension_path = app_settings.vfs_extension_path

        if not vfs_extension_path.exists():
            download_vfs_extension()

        # Load extension into a temporary connection
        # This registers the VFS globally for this process
        try:
            conn = sqlite3.connect(":memory:")
            conn.enable_load_extension(True)
            conn.load_extension(str(vfs_extension_path))
            conn.close()
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Litestream VFS extension from {vfs_extension_path}. "
                f"Error: {e}"
            ) from e


        _vfs_loaded = True





