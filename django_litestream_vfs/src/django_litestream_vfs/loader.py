# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import ctypes
import ctypes.util
import threading

from django_litestream_vfs.conf import vfs_settings

_vfs_loaded = False
_vfs_load_lock = threading.Lock()


def ensure_vfs_loaded() -> None:
    """
    Load the Litestream VFS extension into the SQLite library.

    The extension uses a custom entry point (sqlite3_litestreamvfs_init)
    that Python's sqlite3.load_extension() cannot call (it hardcodes
    the default entry point name). We use ctypes to call
    sqlite3_auto_extension() directly, which registers the VFS
    globally for all future SQLite connections in this process.
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
            _load_vfs_ctypes(str(vfs_path))
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Litestream VFS extension from {vfs_path}. "
                f"Error: {e}"
            ) from e

        _vfs_loaded = True


def _load_vfs_ctypes(vfs_path: str) -> None:
    sqlite_lib = ctypes.util.find_library("sqlite3")
    if not sqlite_lib:
        raise RuntimeError("Could not find sqlite3 shared library")

    sqlite = ctypes.CDLL(sqlite_lib, use_errno=True)

    vfs_lib = ctypes.CDLL(vfs_path, use_errno=True)

    entry = ctypes.c_void_p.in_dll(vfs_lib, "sqlite3_litestreamvfs_init")

    sqlite.sqlite3_auto_extension.argtypes = [ctypes.c_void_p]
    sqlite.sqlite3_auto_extension.restype = ctypes.c_int
    sqlite.sqlite3_auto_extension(None)
    ret = sqlite.sqlite3_auto_extension(entry)
    if ret != 0:
        raise RuntimeError(f"sqlite3_auto_extension failed with code {ret}")
