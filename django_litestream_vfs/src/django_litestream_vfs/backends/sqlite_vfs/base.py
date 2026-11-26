"""
Django database backend for Litestream VFS read replicas.

How it works -- a backend for each DATABASES entry configured by get_vfs_databases():

    DATABASES["prod_replica"] = {
        "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
        "NAME": "file:prod_replica.db?vfs=litestream&mode=ro&replica_url=s3%3A%2F%2F...",
        "OPTIONS": {
            "uri": True,
            "litestream_replica_url": "s3://mybucket/db.sqlite3",
        },
    }

When Django opens this connection:

1. ensure_vfs_loaded()
   Loads the litestream.so shared library once per process.
   Registers a custom SQLite VFS handler named "litestream" globally.

2. Ensures the replica config is part of the connection URI
   The extension reads ``LITESTREAM_REPLICA_URL`` only once, at load time, so a
   process-wide environment variable cannot describe more than one replica. The
   replica URL (and any other VFS option) is passed as a URI parameter instead,
   which the extension resolves per connection.

3. Opens "file:...?vfs=litestream&mode=ro"
   SQLite routes all I/O through the custom VFS handler. Pages are
   fetched on-demand from cloud storage. Writes return errors (read-only).

Result: User.objects.using("prod_replica").all() reads from cloud storage
with no local database file and no download step.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from django_litestream_vfs import VFS_URI_OPTIONS
from django_litestream_vfs.loader import ensure_vfs_loaded
from django.db.backends.sqlite3 import base


def _with_vfs_params(database: str, params: dict[str, str]) -> str:
    """Append ``params`` to a ``file:`` URI without overwriting existing keys."""
    if not params or not database.startswith("file:"):
        return database

    existing = database.partition("?")[2]
    present = {
        key
        for key, _, _ in (part.partition("=") for part in existing.split("&") if part)
    }
    missing = {key: value for key, value in params.items() if key not in present}
    if not missing:
        return database

    separator = "&" if "?" in database else "?"
    return f"{database}{separator}{urlencode(missing, quote_via=quote, safe='')}"


class DatabaseWrapper(base.DatabaseWrapper):
    def get_new_connection(self, conn_params):
        # The extension must be registered before the first connection opens.
        ensure_vfs_loaded()

        params = {}
        replica_url = conn_params.pop("litestream_replica_url", None)
        if isinstance(replica_url, str):
            params["replica_url"] = replica_url

        for key in VFS_URI_OPTIONS:
            value = conn_params.pop(key, None)
            if value is None:
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            params[key] = str(value)

        database = conn_params.get("database")
        if isinstance(database, str):
            conn_params["database"] = _with_vfs_params(database, params)

        return super().get_new_connection(conn_params)
