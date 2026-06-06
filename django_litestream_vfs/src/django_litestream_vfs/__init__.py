# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

__all__ = [
    "get_vfs_databases",
]


def get_vfs_databases() -> dict[str, dict]:
    from django_litestream.conf import app_settings

    vfs_config = app_settings.user_settings.get("vfs", {})

    if not vfs_config:
        return {}

    databases = {}

    for alias, replica_url in vfs_config.items():
        if not isinstance(replica_url, str):
            continue

        databases[alias] = {
            "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
            "NAME": f"file:{alias}.db?vfs=litestream&mode=ro",
            "OPTIONS": {
                "uri": True,
                "litestream_replica_url": replica_url,
            },
        }

    return databases
