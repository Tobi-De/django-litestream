# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sqlite3
import threading
from django_litestream.conf import app_settings

_vfs_loaded = False
_vfs_load_lock = threading.Lock()


def ensure_vfs_loaded() -> None:
    """
    Ensure the Litestream VFS extension is loaded exactly once per process.

    Thread-safe via double-checked locking.

    The VFS extension registers a global VFS handler in the SQLite library
    for this process. Once registered, all connections in this process can
    use vfs=litestream without reloading.

    Raises:
        FileNotFoundError: If the VFS extension file is not found at the
            configured or default path.
        RuntimeError: If the extension fails to load.
    """
    global _vfs_loaded

    if _vfs_loaded:
        return

    with _vfs_load_lock:
        if _vfs_loaded:
            return

        vfs_path = app_settings.vfs_extension_path

        if not vfs_path.exists():
            raise FileNotFoundError(
                f"Litestream VFS extension not found at {vfs_path}.\n"
                "Install via: pip install django-litestream[vfs]\n"
                "Or set LITESTREAM['vfs_extension_path'] to a custom path."
            )

        try:
            conn = sqlite3.connect(":memory:")
            conn.enable_load_extension(True)
            conn.load_extension(str(vfs_path))
            conn.close()
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Litestream VFS extension from {vfs_path}. "
                f"Error: {e}"
            ) from e

        _vfs_loaded = True
