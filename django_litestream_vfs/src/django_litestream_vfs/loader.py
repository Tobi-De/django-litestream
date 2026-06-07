# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sqlite3
import threading

from django_litestream_vfs.conf import vfs_settings

_vfs_loaded = False
_vfs_load_lock = threading.Lock()


def ensure_vfs_loaded() -> None:
    """
    Load the Litestream VFS extension into the SQLite library.

    Python's conn.load_extension() hardcodes the entry point as
    "sqlite3_extension_init", but litestream-vfs uses the custom
    entry point "sqlite3_litestreamvfs_init". We use SQLite's
    built-in load_extension() SQL function instead, which accepts
    the entry point name as a parameter.

    The VFS handler is registered globally for all SQLite connections
    in this process. Once loaded, opening with ?vfs=litestream works.
    """
    global _vfs_loaded

    if _vfs_loaded:
        return

    with _vfs_load_lock:
        if _vfs_loaded:
            return

        vfs_path = vfs_settings.vfs_extension_path

        if not vfs_path.exists():
            raise FileNotFoundError(
                f"Litestream VFS extension not found at {vfs_path}.\n"
                "Install via: pip install django-litestream[vfs]\n"
                "Or set LITESTREAM['vfs_extension_path'] to a custom path."
            )

        try:
            conn = sqlite3.connect(":memory:")
            conn.enable_load_extension(True)
            conn.execute(
                "SELECT load_extension(?, ?)",
                [str(vfs_path), "sqlite3_litestreamvfs_init"],
            )
            conn.close()
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Litestream VFS extension from {vfs_path}. "
                f"Error: {e}"
            ) from e

        _vfs_loaded = True
