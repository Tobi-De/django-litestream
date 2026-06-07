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

    Python's sqlite3.load_extension() hardcodes the entry point as
    "sqlite3_extension_init", but litestream-vfs uses the custom
    entry point "sqlite3_litestreamvfs_init". We use ctypes to call
    sqlite3_load_extension() with the correct entry point name.

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
            _load_vfs(str(vfs_path))
        except OSError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Litestream VFS extension from {vfs_path}. Error: {e}"
            ) from e

        _vfs_loaded = True


def _load_vfs(vfs_path: str) -> None:
    sqlite_lib = ctypes.util.find_library("sqlite3")
    if not sqlite_lib:
        raise RuntimeError("Could not find sqlite3 shared library")

    sqlite = ctypes.CDLL(sqlite_lib, use_errno=True)

    sqlite.sqlite3_open_v2.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_int,
        ctypes.c_char_p,
    ]
    sqlite.sqlite3_open_v2.restype = ctypes.c_int

    sqlite.sqlite3_enable_load_extension.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    sqlite.sqlite3_enable_load_extension.restype = ctypes.c_int

    sqlite.sqlite3_load_extension.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_char_p),
    ]
    sqlite.sqlite3_load_extension.restype = ctypes.c_int

    sqlite.sqlite3_close.argtypes = [ctypes.c_void_p]
    sqlite.sqlite3_close.restype = ctypes.c_int

    handle = ctypes.c_void_p()
    rc = sqlite.sqlite3_open_v2(
        b":memory:",
        ctypes.byref(handle),
        0x00000002 | 0x00000004 | 0x00000040,  # SQLITE_OPEN_READWRITE | CREATE | URI
        None,
    )
    if rc != 0:
        raise RuntimeError(f"sqlite3_open_v2 failed with code {rc}")

    try:
        rc = sqlite.sqlite3_enable_load_extension(handle, 1)
        if rc != 0:
            raise RuntimeError(f"sqlite3_enable_load_extension failed with code {rc}")

        err = ctypes.c_char_p()
        rc = sqlite.sqlite3_load_extension(
            handle,
            vfs_path.encode(),
            b"sqlite3_litestreamvfs_init",
            ctypes.byref(err),
        )
        if rc != 0:
            msg = err.value.decode() if err.value else f"error code {rc}"
            raise RuntimeError(msg)
    finally:
        sqlite.sqlite3_close(handle)
