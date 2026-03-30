# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

__all__ = [
    "get_vfs_databases",
]


def get_vfs_databases() -> dict[str, dict]:
    """
    Generate all VFS replica database configurations from LITESTREAM["vfs"].

    VFS replicas are read-only database connections that fetch data on-demand
    from cloud storage (S3, GCS, etc.) without downloading the entire database.

    Returns:
        Dict mapping database alias -> Django database configuration

    Example:
        # settings.py
        from django_litestream import get_vfs_databases

        LITESTREAM = {
            "vfs": {
                "prod_replica": "s3://mybucket/db.sqlite3",
                "analytics_replica": "s3://analytics/analytics.db",
            }
        }

        DATABASES = {
            "default": {...},
            **get_vfs_databases(),  # Adds prod_replica and analytics_replica
        }

        # Usage in code:
        User.objects.using("prod_replica").all()
    """
    from django_litestream.conf import app_settings

    vfs_config = app_settings.user_settings.get("vfs", {})

    if not vfs_config:
        return {}

    databases = {}

    for alias, replica_url in vfs_config.items():
        # Only process replica URLs (strings starting with a protocol)
        if not isinstance(replica_url, str):
            continue

        databases[alias] = {
            "ENGINE": "django_litestream.db.backends.sqlite_vfs",
            "NAME": f"file:{alias}.db?vfs=litestream&mode=ro",
            "OPTIONS": {
                "uri": True,
                "litestream_replica_url": replica_url,
            },
        }

    return databases
