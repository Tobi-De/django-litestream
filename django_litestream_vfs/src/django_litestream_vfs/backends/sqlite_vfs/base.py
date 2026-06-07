"""
Django database backend for Litestream VFS read replicas.

How it works -- a backend for each DATABASES entry configured by get_vfs_databases():

    DATABASES["prod_replica"] = {
        "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
        "NAME": "file:prod_replica.db?vfs=litestream&mode=ro",
        "OPTIONS": {
            "uri": True,
            "litestream_replica_url": "s3://mybucket/db.sqlite3",
        },
    }

When Django opens this connection:

1. ensure_vfs_loaded()
   Loads the litestream.so shared library once per process.
   Registers a custom SQLite VFS handler named "litestream" globally.

2. Sets os.environ["LITESTREAM_REPLICA_URL"]
   The C VFS handler reads this env var at connection-open time to know
   where the cloud replica lives. This is the sanctioned way to pass
   the replica URL at runtime (the handler runs in-process).

3. Opens "file:...?vfs=litestream&mode=ro"
   SQLite routes all I/O through the custom VFS handler. Pages are
   fetched on-demand from cloud storage. Writes return errors (read-only).

Result: User.objects.using("prod_replica").all() reads from cloud storage
with no local database file and no download step.
"""

from __future__ import annotations

import os

from django_litestream_vfs.loader import ensure_vfs_loaded
from django.db.backends.sqlite3 import base


class DatabaseWrapper(base.DatabaseWrapper):
    def get_new_connection(self, conn_params):
        ensure_vfs_loaded()
        replica_url = self.settings_dict.get("OPTIONS", {}).get(
            "litestream_replica_url"
        )

        if replica_url:
            os.environ["LITESTREAM_REPLICA_URL"] = replica_url

        conn_params.pop("litestream_replica_url", None)
        return super().get_new_connection(conn_params)
