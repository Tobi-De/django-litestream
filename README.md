# django-litestream

[![PyPI - Version](https://img.shields.io/pypi/v/django-litestream.svg)](https://pypi.org/project/django-litestream)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-litestream.svg)](https://pypi.org/project/django-litestream)
[![PyPI - Versions from Framework Classifiers](https://img.shields.io/pypi/frameworkversions/django/django-litestream)](https://pypi.org/project/django-litestream/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Tobi-De/django-litestream/blob/main/LICENSE.txt)

Django integration for [Litestream](https://litestream.io), the SQLite replication tool. The Litestream binary is bundled in platform-specific wheels — no manual download needed. All upstream commands are available as `python manage.py litestream <command>`.

> **Note:** This package tracks Litestream's upstream version. The initial release is **0.5.11**, matching Litestream v0.5.11. Wrapper-only fixes (no Litestream update) use [PEP 440 post-releases](https://peps.python.org/pep-0440/#post-releases) like `0.5.11.post1`.

## Installation

```console
pip install django-litestream
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django_litestream",
]
```

The binary is installed automatically on supported platforms (Linux/macOS x86_64 & arm64). On unsupported platforms, set a custom path:

```python
LITESTREAM = {
    "bin_path": "/usr/local/bin/litestream",
}
```

## Configuration

Configuration is generated dynamically from Django settings — no YAML file needed.

```python
# settings.py
LITESTREAM = {
    "path_prefix": "",      # prepended to S3 replica paths
    "bin_path": "...",      # custom binary path (optional)
    "dbs": [                # databases to replicate
        {"path": "default"},
    ],
}
```

All [Litestream config options](https://litestream.io/reference/config/) are supported (`addr`, `logging`, `mcp-addr`, `access-key-id`, etc.).

### Database aliases

Use Django database aliases instead of file paths wherever `db_path` is required:

```console
python manage.py litestream restore default        # instead of /path/to/db.sqlite3
python manage.py litestream sync default
```

### Auto-generated replicas

If no `replica` is specified for a database, an S3 replica is auto-generated using environment variables:

```python
LITESTREAM = {
    "dbs": [{"path": "default"}],
}
# Uses: LITESTREAM_REPLICA_BUCKET, LITESTREAM_ACCESS_KEY_ID, LITESTREAM_SECRET_ACCESS_KEY
```

Explicit replica config:

```python
LITESTREAM = {
    "dbs": [
        {
            "path": "default",
            "replica": {
                "type": "s3",
                "bucket": "my-bucket",
                "path": "db.sqlite3",
            },
        },
    ],
}
```

### Multiple databases with path_prefix

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
            "replica": {
                "type": "s3",
                "bucket": "my-cache-bucket",
                "path": "cache.sqlite3",
            },
        },
    ],
}
```

## Custom commands

These commands are unique to django-litestream — they don't exist in upstream Litestream.

### `litestream config`

Display the generated configuration in YAML format.

```console
python manage.py litestream config
```

Useful for verifying your setup before running replication.

### `litestream verify`

Checks backup integrity end-to-end: writes a verification row, waits for replication, restores the latest backup, and confirms the row exists.

```console
python manage.py litestream verify default
```

## Upstream commands

All [Litestream commands](https://litestream.io/reference/) are exposed as management commands. Run `python manage.py litestream` to see the full list. Key notes:

- **`replicate`**: Run in production via a process manager. Use `-exec` to wrap your application server.
- **`restore`**: Supports `-timestamp`, `-generation`, `-index` for point-in-time recovery.
- **Daemon control** (`info`, `list`, `register`, `unregister`, `start`, `stop`): Communicate with a running `replicate` daemon over IPC.

The only difference from upstream is that Django database aliases work anywhere `db_path` is expected.

## VFS Read Replicas

Read-only access to cloud-stored replicas without downloading the entire database. Pages are fetched on-demand.

```console
pip install django-litestream[vfs]
```

This installs both `django-litestream` and `django-litestream-vfs` (the VFS extension and Python integration).

### Setup

```python
# settings.py
from django_litestream_vfs import get_vfs_databases

INSTALLED_APPS = [
    "django_litestream",
    "django_litestream_vfs",  # loads VFS extension on startup
]

LITESTREAM = {
    "dbs": [{"path": "default"}],
    "vfs": {
        "prod_replica": "s3://mybucket/db.sqlite3",
    },
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    **get_vfs_databases(),  # adds VFS replicas
}
```

### Usage

```python
User.objects.using("prod_replica").all()  # read-only, on-demand page fetch
```

VFS replicas are read-only. Only x86_64 and arm64 supported. Multiple storage backends supported (S3, GCS, Azure Blob).

## License

MIT. The bundled Litestream binary uses the Apache 2.0 license.
