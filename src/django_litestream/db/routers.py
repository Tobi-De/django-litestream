from __future__ import annotations

import random
from typing import TYPE_CHECKING

from django_litestream.conf import app_settings
from django.conf import settings
from django_litestream import get_vfs_status

if TYPE_CHECKING:
    from django.db.models import Model


class LitestreamRouter:
    """
    Database router that distributes reads to VFS replicas and writes to primary.

    This router automatically routes read queries to available VFS replica databases
    while keeping all writes on the primary database. It's lag-aware and will only
    use replicas that are within the configured staleness threshold.

    Configuration:
        Add to DATABASES settings:

        DATABASE_ROUTERS = ['django_litestream.db.routers.LitestreamRouter']

        LITESTREAM = {
            'vfs': {
                'prod_replica': 's3://mybucket/db.sqlite3',
                'analytics_replica': 's3://analytics/db.sqlite3',
                'max_lag_seconds': 60,  # Only use replicas with lag < 60s (optional, default: 60)
            }
        }

    """

    def __init__(self):
        vfs_config = app_settings.user_settings.get("vfs", {})
        self._max_lag = vfs_config.get("max_lag_seconds", 60)
        self._replica_aliases = None

    def _get_vfs_replicas(self) -> list[str]:
        if self._replica_aliases is not None:
            return self._replica_aliases

        self._replica_aliases = [
            alias
            for alias, config in settings.DATABASES.items()
            if config.get("ENGINE") == "django_litestream.db.backends.sqlite_vfs"
        ]
        return self._replica_aliases

    def _get_healthy_replicas(self) -> list[str]:
        healthy = []
        for alias in self._get_vfs_replicas():
            try:
                status = get_vfs_status(alias)
                lag = status.get("lag_seconds")

                # Only use replica if lag is available and within threshold
                if lag is not None and lag <= self._max_lag:
                    healthy.append(alias)
            except Exception:
                continue

        return healthy

    def db_for_read(self, model: type[Model], **hints) -> str | None:
        """
        Route read operations to healthy VFS replicas.

        Randomly selects from replicas with lag under max_lag_seconds.
        Falls back to primary if no healthy replicas available.
        """
        healthy_replicas = self._get_healthy_replicas()

        if healthy_replicas:
            return random.choice(healthy_replicas)

        return "default"

    def db_for_write(self, model: type[Model], **hints) -> str | None:
        """
        Route all write operations to primary database.

        VFS replicas are read-only, so all writes must go to primary.
        """
        return "default"

    def allow_relation(self, obj1, obj2, **hints) -> bool | None:
        """
        Allow relations between any databases.

        Since replicas are copies of the primary, relations should work.
        """
        return True

    def allow_migrate(
        self, db: str, app_label: str, model_name=None, **hints
    ) -> bool | None:
        """
        Only allow migrations on primary database.

        VFS replicas are read-only and should never be migrated.
        """
        if db == "default":
            return True

        if db in self._get_vfs_replicas():
            return False

        # No opinion on other databases
        return None
