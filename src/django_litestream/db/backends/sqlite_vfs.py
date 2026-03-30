# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os

from django_litestream.vfs import ensure_vfs_loaded
from django.db.backends.sqlite3 import base


class DatabaseWrapper(base.DatabaseWrapper):
    def get_new_connection(self, conn_params):
        """
        Create a new database connection with VFS extension support.

        The VFS extension is loaded once per process (typically in AppConfig.ready()),
        but this method includes a fallback to load it if needed (e.g., for
        management commands that don't trigger ready()).
        """

        ensure_vfs_loaded()
        replica_url = self.settings_dict.get("OPTIONS", {}).get(
            "litestream_replica_url"
        )

        if replica_url:
            # Set environment variable for VFS extension
            # The VFS reads this when opening the database
            os.environ["LITESTREAM_REPLICA_URL"] = replica_url

        # Create connection using parent class
        # The database NAME includes ?vfs=litestream, so SQLite uses our VFS
        connection = super().get_new_connection(conn_params)

        return connection
