# SPDX-FileCopyrightText: 2024-present Tobi DEGNON <tobidegnon@proton.me>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from urllib.parse import quote, urlencode

__all__ = [
    "get_vfs_databases",
    "VFS_URI_OPTIONS",
]

# Per-database VFS options accepted by the extension as URI parameters
# (litestream v0.5.17+, see `vfs_config.go` upstream).
VFS_URI_OPTIONS = frozenset(
    {
        "write_enabled",
        "sync_interval",
        "buffer_path",
        "hydration_enabled",
        "hydration_path",
        "poll_interval",
        "cache_size",
    }
)


def _normalize_entry(entry: object) -> tuple[str, dict[str, object]] | None:
    """Return ``(replica_url, options)`` for a ``LITESTREAM["vfs"]`` value."""
    if isinstance(entry, str):
        return entry, {}

    if isinstance(entry, dict):
        replica_url = entry.get("url", entry.get("replica_url"))
        if not isinstance(replica_url, str):
            return None
        options = {key: value for key, value in entry.items() if key in VFS_URI_OPTIONS}
        return replica_url, options

    return None


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def _database_name(alias: str, replica_url: str, options: dict[str, object]) -> str:
    """Build a SQLite URI carrying the replica config for this connection.

    The extension reads ``LITESTREAM_REPLICA_URL`` only once, when it is loaded
    into the process, so the replica must be passed per connection. Every
    ``vfs`` parameter is URL-encoded because SQLite decodes query values before
    handing them to the extension.
    """
    params: dict[str, str] = {
        "vfs": "litestream",
        "replica_url": replica_url,
    }
    # Write mode is experimental upstream; `mode=ro` would block writes at the
    # SQLite layer even when the VFS accepts them.
    if not _is_truthy(options.get("write_enabled", False)):
        params["mode"] = "ro"
    for key, value in options.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        params[key] = str(value)

    query = urlencode(params, quote_via=quote, safe="")
    return f"file:{alias}.db?{query}"


def get_vfs_databases() -> dict[str, dict]:
    from django_litestream.conf import app_settings

    vfs_config = app_settings.user_settings.get("vfs", {})

    if not vfs_config:
        return {}

    databases = {}

    for alias, entry in vfs_config.items():
        normalized = _normalize_entry(entry)
        if normalized is None:
            continue
        replica_url, options = normalized

        databases[alias] = {
            "ENGINE": "django_litestream_vfs.backends.sqlite_vfs",
            "NAME": _database_name(alias, replica_url, options),
            "OPTIONS": {
                "uri": True,
                "litestream_replica_url": replica_url,
            },
        }

    return databases
