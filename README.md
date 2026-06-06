# django-litestream

[![PyPI - Version](https://img.shields.io/pypi/v/django-litestream.svg)](https://pypi.org/project/django-litestream)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-litestream.svg)](https://pypi.org/project/django-litestream)
[![PyPI - Versions from Framework Classifiers](https://img.shields.io/pypi/frameworkversions/django/django-litestream)](https://pypi.org/project/django-litestream/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Tobi-De/django-litestream/blob/main/LICENSE.txt)

django-litestream integrates [Litestream](https://litestream.io), the SQLite replication tool, as a Django management command. The Litestream binary is bundled in platform-specific wheels — no manual download needed.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Commands](#commands)
  - [litestream config](#litestream-config)
  - [litestream databases](#litestream-databases)
  - [litestream ltx](#litestream-ltx)
  - [litestream replicate](#litestream-replicate)
  - [litestream restore](#litestream-restore)
  - [litestream status](#litestream-status)
  - [litestream sync](#litestream-sync)
  - [litestream mcp](#litestream-mcp)
  - [litestream wal / reset](#litestream-wal--reset)
  - [litestream info / list](#litestream-info--list)
  - [litestream register / unregister](#litestream-register--unregister)
  - [litestream start / stop](#litestream-start--stop)
  - [litestream version](#litestream-version)
  - [litestream verify](#litestream-verify)
- [VFS Read Replicas](#vfs-read-replicas)
- [License](#license)

## Installation

The Litestream binary is bundled in platform-specific wheels and installed automatically alongside the Python wrapper. Supported platforms: Linux (x86_64, arm64, armv7, armv6) and macOS (x86_64, arm64).

```console
pip install django-litestream
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django_litestream",
]
```

### Custom binary path

If you prefer to use your own Litestream binary, set `bin_path`:

```python
LITESTREAM = {
    "bin_path": "/usr/local/bin/litestream",
}
```

When a platform-specific wheel is installed, the default `bin_path` of `<venv>/bin/litestream` works automatically — no configuration needed.

## Configuration

```python
# settings.py
LITESTREAM = {
    "path_prefix": "",                       # prepended to replica paths
    "bin_path": "./venv/bin/litestream",     # custom binary path (optional)
    "dbs": [{"path": "default"}],            # databases to replicate
    # ... any other Litestream config options
}
```

Configuration is dynamically generated from Django settings when you run commands — no YAML file needed. All [Litestream configuration options](https://litestream.io/reference/config/) are supported (e.g. `logging`, `addr`, `mcp-addr`, `access-key-id`, `secret-access-key`).

**`path_prefix`** is prepended to replica paths, useful when multiple projects share the same S3 bucket.

**`bin_path`** defaults to the bundled binary. Override it to use a system-installed Litestream or a custom installation.

**`dbs`** entries can reference Django database aliases (`"default"`) instead of full file paths. If no `replica` is specified, an S3 replica is auto-generated using environment variables:

- `LITESTREAM_REPLICA_BUCKET` or `AWS_BUCKET`
- `LITESTREAM_ACCESS_KEY_ID` or `AWS_ACCESS_KEY_ID`
- `LITESTREAM_SECRET_ACCESS_KEY` or `AWS_SECRET_ACCESS_KEY`

### Configuration examples

**Minimal — auto-generated S3 replica:**

```python
LITESTREAM = {
    "dbs": [{"path": "default"}],
}
```

**Multiple databases with `path_prefix`:**

```python
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"},
    "cache":  {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "cache.sqlite3"},
}

LITESTREAM = {
    "path_prefix": "myproject",
    "dbs": [
        {"path": "default"},           # → myproject/db.sqlite3
        {
            "path": "cache",
            "replica": {               # explicit replica config
                "type": "s3",
                "bucket": "my-cache-bucket",
                "path": "cache.sqlite3",
            },
        },
    ],
}
```

Generated config:

```yaml
access-key-id: $LITESTREAM_ACCESS_KEY_ID
secret-access-key: $LITESTREAM_SECRET_ACCESS_KEY
dbs:
- path: /home/tobi/myproject/db.sqlite3
  replica:
    type: s3
    bucket: $LITESTREAM_REPLICA_BUCKET
    path: myproject/db.sqlite3
- path: /home/tobi/myproject/cache.sqlite3
  replica:
    type: s3
    bucket: my-cache-bucket
    path: cache.sqlite3
```

## Commands

Run `python manage.py litestream` to see all available commands. Wherever `db_path` is required, you can use a Django database alias (e.g. `"default"`) instead of the full file path.

### litestream config

Display the current configuration generated from Django settings.

```console
python manage.py litestream config
```

### litestream databases

Lists all databases specified in the configuration. Same as upstream [`litestream databases`](https://litestream.io/reference/databases/).

```console
python manage.py litestream databases
```

### litestream ltx

Lists LTX (Litestream Transaction Log) files. Same as upstream [`litestream ltx`](https://litestream.io/reference/ltx/).

```console
python manage.py litestream ltx default
python manage.py litestream ltx -replica s3 default
python manage.py litestream ltx s3://mybkt.litestream.io/db
```

### litestream replicate

Runs the replication server. Same as upstream [`litestream replicate`](https://litestream.io/reference/replicate/).

```console
python manage.py litestream replicate
python manage.py litestream replicate -exec "gunicorn myproject.wsgi:application"
python manage.py litestream replicate -once
python manage.py litestream replicate -force-snapshot
python manage.py litestream replicate -restore-if-db-not-exists
```

### litestream restore

Recovers a database backup from a replica. Same as upstream [`litestream restore`](https://litestream.io/reference/restore/).

```console
python manage.py litestream restore default
python manage.py litestream restore -o /tmp/restored.db default
python manage.py litestream restore -timestamp "2025-01-15T10:00:00Z" default
python manage.py litestream restore -f default            # follow mode
python manage.py litestream restore -if-replica-exists default
```

### litestream status

Reports local replication status.

```console
python manage.py litestream status
python manage.py litestream status default
```

### litestream sync

Forces immediate WAL-to-LTX sync for a database.

```console
python manage.py litestream sync default
```

### litestream mcp

Starts a standalone MCP (Model Context Protocol) server for AI assistant integration. Requires `mcp-addr` in configuration.

```python
LITESTREAM = {
    "mcp-addr": "127.0.0.1:3001",
}
```

```console
python manage.py litestream mcp
```

The MCP server can also run alongside replication by adding `mcp-addr` and running `replicate`. Exposed tools: `litestream_info`, `litestream_databases`, `litestream_status`, `litestream_ltx`, `litestream_restore`, `litestream_reset`.

### litestream wal / reset

```console
python manage.py litestream wal default       # list WAL files (deprecated, use ltx)
python manage.py litestream reset default     # clear local state, force fresh snapshot
python manage.py litestream reset -dry-run default
```

### litestream info / list

Daemon control commands — communicate with a running `replicate` daemon over the IPC socket.

```console
python manage.py litestream info              # daemon version, PID, uptime
python manage.py litestream info -json
python manage.py litestream list               # list managed databases
```

### litestream register / unregister

Dynamically add or remove databases from a running daemon.

```console
python manage.py litestream register -replica s3://bucket/db default
python manage.py litestream unregister default
python manage.py litestream unregister -dry-run default
```

### litestream start / stop

Pause or resume replication for a specific database on a running daemon.

```console
python manage.py litestream stop default
python manage.py litestream start default
```

### litestream version

Prints the Litestream binary version.

```console
python manage.py litestream version
```

### litestream verify

Verifies backup integrity by writing a verification row, waiting for replication, restoring the latest backup, and checking the row exists.

```console
python manage.py litestream verify default
```

Steps:
1. Inserts a unique row into `_litestream_verification`
2. Waits 10 seconds for replication
3. Restores the latest backup to a temporary location
4. Verifies the row exists in the restored database

## VFS Read Replicas

The VFS (Virtual File System) feature enables read-only access to database replicas in cloud storage without downloading the entire database. Pages are fetched on-demand.

VFS support is provided by the `django-litestream-vfs` package:

```console
pip install django-litestream[vfs]
```

This installs:
- `django-litestream` — wrapper + Litestream binary
- `django-litestream-vfs` — VFS extension + Python integration

### Setup

**1. Add to INSTALLED_APPS:**

```python
INSTALLED_APPS = [
    "django_litestream",
    "django_litestream_vfs",  # loads VFS extension on startup
]
```

**2. Configure VFS replicas:**

```python
# settings.py
from django_litestream_vfs import get_vfs_databases

LITESTREAM = {
    "dbs": [{"path": "default"}],
    "vfs": {
        "prod_replica": "s3://mybucket/db.sqlite3",
        "analytics_replica": "s3://analytics/db.sqlite3",
    },
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    **get_vfs_databases(),  # adds prod_replica and analytics_replica
}
```

**3. Use VFS replicas:**

```python
from myapp.models import User

users = User.objects.using("prod_replica").all()
```

### Supported storage backends

| URL format | Provider |
|------------|----------|
| `s3://bucket/path` | Amazon S3 |
| `gcs://bucket/path` | Google Cloud Storage |
| `abs://container/path` | Azure Blob Storage |

### Architecture

`django-litestream-vfs` is a separate package that depends on `django-litestream`. The VFS extension (`.so`/`.dylib`) is bundled in platform-specific wheels and installed alongside the main Litestream binary. The extension is loaded once per process by `VfsConfig.ready()` and made available to all SQLite connections via `vfs=litestream`.

VFS replicas are read-only. Writes will return errors. Only x86_64 and arm64 architectures are supported for the VFS extension.

## License

MIT — see [LICENSE.txt](https://github.com/Tobi-De/django-litestream/blob/main/LICENSE.txt). The bundled Litestream binary uses the Apache 2.0 license.
