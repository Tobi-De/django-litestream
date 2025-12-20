# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from django_litestream.db.routers import LitestreamRouter

__all__ = [
    "get_vfs_databases",
    "time_travel",
    "get_vfs_status",
    "LitestreamRouter",
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
                "max_lag_seconds": 60,  # Optional: for LitestreamRouter (default: 60)
            }
        }

        DATABASES = {
            "default": {...},
            **get_vfs_databases(),  # Adds prod_replica and analytics_replica
        }
    """
    from django_litestream.conf import app_settings

    vfs_config = app_settings.user_settings.get("vfs", {})

    if not vfs_config:
        return {}

    databases = {}

    for alias, replica_url in vfs_config.items():
        # Skip config keys (only process replica URLs which are strings)
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


@contextmanager
def time_travel(db_alias: str, time_point: str):
    """
    Query a VFS database at a specific point in time.

    This context manager opens a connection to a VFS database and sets
    PRAGMA litestream_time to query historical data. The database appears
    as it existed at the specified time point.

    Args:
        db_alias: VFS database alias (must be configured in LITESTREAM["vfs"])
        time_point: Time specification in natural language or ISO format
            Examples: "5 minutes ago", "1 hour ago", "2024-12-20 15:00:00"

    Yields:
        str: Temporary database alias to use with .using()

    Example:
        from django_litestream import time_travel

        # Query data from 1 hour ago
        with time_travel("default_replica", "1 hour ago") as db:
            old_users = User.objects.using(db).all()

        # Query at specific timestamp
        with time_travel("default_replica", "2024-12-20 14:00:00") as db:
            orders = Order.objects.using(db).filter(status='pending')

    Raises:
        ImproperlyConfigured: If db_alias is not a VFS database
        RuntimeError: If time-travel setup fails
    """
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured
    from django.db import connections

    # Verify this is a VFS database
    if db_alias not in settings.DATABASES:
        raise ImproperlyConfigured(
            f"Database '{db_alias}' not found in DATABASES. "
            "Make sure it's a VFS database configured via get_vfs_databases()."
        )

    db_config = settings.DATABASES[db_alias]
    if db_config.get("ENGINE") != "django_litestream.db.backends.sqlite_vfs":
        raise ImproperlyConfigured(
            f"Database '{db_alias}' is not a VFS database. "
            "Time-travel only works with VFS replicas."
        )

    # Create a temporary alias for the time-travel connection
    temp_alias = f"_litestream_timetravel_{db_alias}"

    # Copy the database config
    temp_config = db_config.copy()
    temp_config["OPTIONS"] = db_config.get("OPTIONS", {}).copy()

    # Register temporary database
    settings.DATABASES[temp_alias] = temp_config

    try:
        # Get connection and set time-travel pragma
        connection = connections[temp_alias]

        # Execute the time-travel pragma
        with connection.cursor() as cursor:
            try:
                cursor.execute(f"PRAGMA litestream_time='{time_point}'")
            except Exception as e:
                raise RuntimeError(
                    f"Failed to set time-travel to '{time_point}'. "
                    f"Make sure the VFS extension supports time-travel and the time point is valid. "
                    f"Error: {e}"
                ) from e

        yield temp_alias

    finally:
        # Clean up: close connection and remove temporary database
        if temp_alias in connections:
            connections[temp_alias].close()
            del connections[temp_alias]
        if temp_alias in settings.DATABASES:
            del settings.DATABASES[temp_alias]


def get_vfs_status(db_alias: str) -> dict[str, any]:
    """
    Get status information for a VFS database.

    Queries the VFS PRAGMAs to get current transaction ID, replication lag,
    and other status information.

    Args:
        db_alias: VFS database alias

    Returns:
        Dict with status information:
        - txid: Current transaction ID
        - lag_seconds: Seconds since last poll (replica staleness)
        - replica_url: URL of the replica
        - is_vfs: Always True for VFS databases

    Example:
        from django_litestream import get_vfs_status

        status = get_vfs_status("default_replica")
        print(f"Lag: {status['lag_seconds']}s")
        print(f"Transaction ID: {status['txid']}")

    Raises:
        ImproperlyConfigured: If db_alias is not a VFS database
    """
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured
    from django.db import connections

    # Verify this is a VFS database
    if db_alias not in settings.DATABASES:
        raise ImproperlyConfigured(f"Database '{db_alias}' not found in DATABASES")

    db_config = settings.DATABASES[db_alias]
    if db_config.get("ENGINE") != "django_litestream.db.backends.sqlite_vfs":
        raise ImproperlyConfigured(
            f"Database '{db_alias}' is not a VFS database. "
            "Status checking only works with VFS replicas."
        )

    connection = connections[db_alias]
    status = {"is_vfs": True, "alias": db_alias}

    # Get replica URL from config
    status["replica_url"] = db_config.get("OPTIONS", {}).get(
        "litestream_replica_url", "unknown"
    )

    # Query VFS PRAGMAs
    with connection.cursor() as cursor:
        # Get transaction ID
        try:
            cursor.execute("PRAGMA litestream_txid")
            row = cursor.fetchone()
            status["txid"] = row[0] if row else None
        except Exception:
            status["txid"] = None

        # Get lag (seconds since last poll)
        try:
            cursor.execute("PRAGMA litestream_lag")
            row = cursor.fetchone()
            status["lag_seconds"] = float(row[0]) if row else None
        except Exception:
            status["lag_seconds"] = None

    return status
