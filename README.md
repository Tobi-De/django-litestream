# django-litestream

[![PyPI - Version](https://img.shields.io/pypi/v/django-litestream.svg)](https://pypi.org/project/django-litestream)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-litestream.svg)](https://pypi.org/project/django-litestream)
[![PyPI - Versions from Framework Classifiers](https://img.shields.io/pypi/frameworkversions/django/django-litestream)](https://pypi.org/project/django-litestream/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Tobi-De/django-litestream/blob/main/LICENSE.txt)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Litestream integration for Django - SQLite replication made simple**

This package integrates [Litestream](https://litestream.io), the SQLite replication tool, as Django management commands. It provides:

- ✅ Continuous SQLite replication to S3, GCS, Azure Blob Storage, and more
- ✅ Read-only VFS replicas for zero-download database access
- ✅ Time-travel queries for historical data analysis
- ✅ Automatic read distribution with lag-aware routing
- ✅ All Litestream commands via `python manage.py litestream`
- ✅ Auto-download of Litestream binary on first use

## Installation

```bash
pip install django-litestream
```

Add to `INSTALLED_APPS`:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django_litestream",
]
```

Configure replication:

```python
# settings.py
LITESTREAM = {
    "dbs": [
        {"path": "default"},  # Use Django database alias
    ]
}
```

Set up cloud storage credentials:

```bash
export LITESTREAM_REPLICA_BUCKET=my-backup-bucket
export LITESTREAM_ACCESS_KEY_ID=your-access-key
export LITESTREAM_SECRET_ACCESS_KEY=your-secret-key
```

## Quick Start

Start continuous replication:

```bash
python manage.py litestream replicate
```

Restore from backup:

```bash
python manage.py litestream restore default
```

## Documentation

📖 **[Read the full documentation](https://django-litestream.readthedocs.io/)**

- [Installation Guide](https://django-litestream.readthedocs.io/en/latest/installation.html)
- [Configuration](https://django-litestream.readthedocs.io/en/latest/configuration.html)
- [Commands Reference](https://django-litestream.readthedocs.io/en/latest/commands.html)
- [VFS Read Replicas](https://django-litestream.readthedocs.io/en/latest/vfs.html)
- [Advanced Features](https://django-litestream.readthedocs.io/en/latest/advanced.html)

## Features

### Continuous Replication

```bash
# Start replication
python manage.py litestream replicate

# Restore database
python manage.py litestream restore default
```

### VFS Read Replicas

Access cloud-stored replicas without downloading:

```python
from django_litestream import get_vfs_databases

DATABASES = {
    "default": {...},
    **get_vfs_databases(),
}

# Query from replica
users = User.objects.using('prod_replica').all()
```

### Time-Travel Queries

Query historical database state:

```python
from django_litestream import time_travel

with time_travel("prod_replica", "1 hour ago") as db:
    old_users = User.objects.using(db).all()
```

### Automatic Read Distribution

Route reads to replicas automatically:

```python
DATABASE_ROUTERS = ['django_litestream.db.routers.LitestreamRouter']

# Reads go to replicas, writes to primary - no code changes!
users = User.objects.all()  # → VFS replica
user.save()  # → Primary database
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

- [GitHub Repository](https://github.com/Tobi-De/django-litestream)
- [Issue Tracker](https://github.com/Tobi-De/django-litestream/issues)
- [Discussions](https://github.com/Tobi-De/django-litestream/discussions)

## License

`django-litestream` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
