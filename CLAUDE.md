# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

django-litestream is a Django app that integrates [Litestream](https://litestream.io) (a SQLite replication tool) as Django management commands. The package automatically downloads the Litestream binary on first use and exposes all Litestream functionality through `python manage.py litestream` commands.

## Development Commands

### Package Management
```bash
# Install dependencies
just install
# or
uv sync

# Run tests
just test
# or
uv run pytest
```

### Demo Application
```bash
# Run Django commands in the demo app
just dj <command>
# Examples:
just dj migrate
just dj shell

# Run the demo server
just run-demo
```

### Code Quality
```bash
# Format code with ruff and prek
just fmt
```

### Release Process
```bash
# Bump version (patch, minor, or major) and update changelog
just bumpver patch
```

## Architecture

### Core Components

**Configuration System (src/django_litestream/conf.py)**
- `AppSettings` dataclass reads from `settings.LITESTREAM`
- Key settings: `path_prefix`, `bin_path`, and all Litestream config options
- `path_prefix` is prepended to replica paths for multi-project bucket organization
- `bin_path` defaults to `<venv>/bin/litestream` but is auto-downloaded if missing

**Management Command (src/django_litestream/management/commands/litestream.py)**
- Single Django command that wraps all Litestream subcommands
- `generate_temp_config()` converts Django settings to temporary YAML config file
- Database alias resolution: users can specify "default" instead of full paths
- Auto-generates S3 replica config when not explicitly provided
- Binary auto-download on first use via `download_binary()`
- Custom `verify` subcommand (not part of upstream Litestream)

### Configuration Translation

The command dynamically generates Litestream config from Django settings:

1. Reads `LITESTREAM` dict from Django settings
2. Resolves Django database aliases to actual file paths using `settings.DATABASES`
3. For each database without explicit `replica` config:
   - Auto-generates S3 replica pointing to `$LITESTREAM_REPLICA_BUCKET`
   - Applies `path_prefix` to the replica path
   - Adds global `access-key-id` and `secret-access-key` env var references
4. Writes YAML to temporary file
5. Passes config path to Litestream binary via `-config` flag

### Database Alias Resolution

`_db_location_from_alias()` function allows users to reference databases by Django alias:
- If alias exists in `settings.DATABASES` and uses SQLite engine, returns the `NAME` path
- Otherwise returns the original string (allows direct paths or replica URLs)
- Used for all `db_path` arguments across commands

### Verify Command

Custom integrity check (inspired by litestream-ruby):
1. Inserts unique verification row into `_litestream_verification` table
2. Waits 10 seconds for replication
3. Restores latest backup to temporary location
4. Verifies the verification row exists in restored database
5. Returns success/failure based on whether backup is in sync

### VFS (Virtual File System) Feature

The VFS feature enables read-only access to database replicas stored in cloud object storage without downloading the entire database file. Pages are fetched on-demand and cached in memory.

**Architecture:**
- **VFS Extension**: Compiled SQLite extension (.so/.dylib/.dll) that registers a custom VFS handler
- **VFS Loader** (`vfs.py`): Thread-safe module that ensures extension loads exactly once per process
- **Custom Database Backend**: `django_litestream/db/backends/sqlite_vfs/base.py` extends Django's SQLite backend
- **Configuration Helper**: `get_vfs_databases()` in `__init__.py` generates Django database configs

**How It Works:**
1. User calls `get_vfs_databases()` in settings.py to generate VFS database configurations
2. On Django startup, `AppConfig.ready()` loads the VFS extension once (if VFS databases configured)
   - Uses `ensure_vfs_loaded()` with thread-safe double-checked locking
   - Auto-downloads extension if missing
   - Registers VFS handler globally for this process
3. When Django opens a VFS database connection, the custom backend:
   - Calls `ensure_vfs_loaded()` as fallback (no-op if already loaded)
   - Sets `LITESTREAM_REPLICA_URL` environment variable from `OPTIONS['litestream_replica_url']`
   - Opens the database with `?vfs=litestream&mode=ro` URI parameter
4. SQLite uses the already-registered VFS to fetch pages from cloud storage on-demand
5. VFS extension polls for updates every 1 second (configurable in extension)

**Configuration:**
```python
# settings.py
from django_litestream import get_vfs_databases

LITESTREAM = {
    "vfs": {
        "prod_replica": "s3://mybucket/db.sqlite3",
        "analytics_replica": "s3://analytics/analytics.db",
        "gcs_replica": "gcs://my-gcs-bucket/data.db",
    }
}

DATABASES = {
    "default": {...},
    **get_vfs_databases(),  # Adds all VFS replicas
}
```

**Simple mapping:**
- VFS config is just `{alias: replica_url}` - no nested dicts or validation
- Supports any replica URL: s3://, gcs://, abs://, file://, sftp://, etc.

**VFS Extension Management:**
- Extension version hardcoded in `download_vfs_extension()` (currently 0.5.5)
- Only supports x86_64 and arm64 architectures (VFS limitation)
- Downloads directly as .so/.dylib/.dll (no archive extraction needed)
- Default install path: `<venv>/lib/litestream-vfs.so`
- Auto-downloads on first use (like main litestream binary)
- Manual install: `python manage.py litestream vfs-install`

**Thread-Safe Loading (`vfs.py`):**
- `ensure_vfs_loaded()`: Loads extension exactly once per process using double-checked locking
- Module-level `_vfs_loaded` flag with `threading.Lock` for thread safety
- Called in `AppConfig.ready()` for proactive loading
- Called in `get_new_connection()` as fallback (no-op if already loaded)

**Custom Database Backend Details:**
- Extends `django.db.backends.sqlite3.base.DatabaseWrapper`
- Overrides `get_new_connection()` to ensure VFS loaded (fallback) and set replica URL
- No per-connection extension loading (extension loaded once at startup)
- Environment variable set per-connection based on `OPTIONS['litestream_replica_url']`

**Key Differences from Regular Replication:**
- VFS is read-only (writes return errors)
- No local database file exists (virtual/on-demand)
- Completely separate config (`LITESTREAM["vfs"]` vs `LITESTREAM["dbs"]`)
- Requires VFS extension, not just litestream binary

### Advanced VFS Features

**Time-Travel Queries:**

The `time_travel()` context manager allows querying VFS databases at specific points in time using the `PRAGMA litestream_time` feature:

```python
from django_litestream import time_travel
from myapp.models import User, Order

# Query data from 1 hour ago
with time_travel("prod_replica", "1 hour ago") as db:
    old_users = User.objects.using(db).all()
    old_count = old_users.count()

# Query at specific timestamp
with time_travel("prod_replica", "2024-12-20 14:00:00") as db:
    orders = Order.objects.using(db).filter(status='pending')

# Compare current vs historical data
current_users = User.objects.all().count()
with time_travel("prod_replica", "24 hours ago") as db:
    yesterday_users = User.objects.using(db).all().count()
    growth = current_users - yesterday_users
```

**How it works:**
1. Creates a temporary database alias with the same VFS configuration
2. Opens a connection and executes `PRAGMA litestream_time='{time_point}'`
3. Yields the temporary alias for use with `.using()`
4. Automatically cleans up the connection and removes the temporary database on exit

**Supported time formats:**
- Natural language: "5 minutes ago", "1 hour ago", "2 days ago"
- ISO timestamps: "2024-12-20 15:00:00"
- Relative times: Any format supported by Litestream VFS

**VFS Monitoring:**

The `get_vfs_status()` function queries VFS PRAGMAs to get replication status:

```python
from django_litestream import get_vfs_status

status = get_vfs_status("prod_replica")
# Returns:
# {
#     "is_vfs": True,
#     "alias": "prod_replica",
#     "replica_url": "s3://mybucket/db.sqlite3",
#     "txid": 12345,  # Current transaction ID (or None if unavailable)
#     "lag_seconds": 2.5,  # Seconds since last poll (or None if unavailable)
# }

# Check if replica is healthy
if status["lag_seconds"] and status["lag_seconds"] < 60:
    print("Replica is healthy!")
else:
    print("Replica is stale or unavailable")
```

**VFS Status Management Command:**

The `vfs-status` command displays status for all configured VFS databases:

```bash
python manage.py litestream vfs-status
```

Output example:
```
Found 2 VFS database(s):

prod_replica:
  Replica URL: s3://mybucket/db.sqlite3
  Transaction ID: 12345
  Replication Lag: 2.5s
  Status: ✓ Healthy

analytics_replica:
  Replica URL: s3://analytics/analytics.db
  Transaction ID: 8901
  Replication Lag: 125.0s (2.1m)
  Status: ⚠ Lagging
```

**Status indicators:**
- ✓ Healthy: Lag < 60s (green)
- ⚠ Lagging: Lag 60s-300s (yellow)
- ✗ Stale: Lag > 300s (red)
- ? Unknown: Status unavailable

**Automatic Read Distribution (Router):**

The `LitestreamRouter` automatically routes read queries to VFS replicas and write queries to the primary database. It's lag-aware and only uses healthy replicas.

```python
# settings.py
from django_litestream import get_vfs_databases

LITESTREAM = {
    "vfs": {
        "prod_replica": "s3://mybucket/db.sqlite3",
        "analytics_replica": "s3://analytics/db.sqlite3",
        "max_lag_seconds": 60,  # Only use replicas with lag < 60s (optional, default: 60)
    }
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    **get_vfs_databases(),
}

# Enable the router
DATABASE_ROUTERS = ["django_litestream.db.routers.LitestreamRouter"]
```

**Router behavior:**
- **Reads**: Randomly distributed across healthy VFS replicas (lag < max_lag_seconds)
- **Writes**: Always routed to primary database (VFS replicas are read-only)
- **Migrations**: Only allowed on primary database
- **Relations**: Allowed between any databases (replicas are copies of primary)
- **Fallback**: Always uses primary for reads if no healthy replicas available

**Example usage with router:**

```python
# No changes needed to your code - router handles everything!

# This read goes to a VFS replica (automatic)
users = User.objects.all()

# This write goes to primary database (automatic)
user = User.objects.create(username="alice")

# This read goes to a VFS replica (automatic)
recent_orders = Order.objects.filter(created_at__gte=yesterday)

# Force specific database (bypasses router)
primary_users = User.objects.using("default").all()
replica_users = User.objects.using("prod_replica").all()
```

**Router configuration:**

Configure the router by adding `max_lag_seconds` to your VFS config:

```python
LITESTREAM = {
    "vfs": {
        "prod_replica": "s3://mybucket/db.sqlite3",
        "max_lag_seconds": 60,  # Default: 60 seconds
    }
}
```

- `max_lag_seconds` (default: 60): Maximum acceptable replication lag in seconds. Replicas with lag above this threshold are excluded from read distribution. The router auto-discovers all VFS databases and uses this threshold to determine which replicas are healthy enough to route reads to.

**Performance considerations:**

- Router checks replica health on every read operation (calls `get_vfs_status()`)
- For high-traffic applications, consider caching status checks
- Replica selection is random to distribute load evenly
- VFS extension polls for updates every 1 second (controlled by VFS, not router)

## Testing Strategy

Tests use Django's `override_settings` to configure different scenarios:
- Auto-generated replica configuration
- User-defined replica configuration
- Path prefix application
- Multiple database handling
- Verify command with mocked subprocess calls

Run tests with `just test` or `uv run pytest`.

## Important Implementation Details

### Database Path Resolution
When processing `dbs` config:
- Filter out non-SQLite databases (only `django.db.backends.sqlite3` supported)
- Convert relative paths to absolute paths using `Path.resolve()`
- Match user-provided paths to Django database settings by comparing `NAME` fields

### Environment Variable Expansion
Litestream config uses environment variables for credentials:
- `$LITESTREAM_ACCESS_KEY_ID` or `$AWS_ACCESS_KEY_ID`
- `$LITESTREAM_SECRET_ACCESS_KEY` or `$AWS_SECRET_ACCESS_KEY`
- `$LITESTREAM_REPLICA_BUCKET` or `$AWS_BUCKET`
- Use `-no-expand-env` flag to disable expansion

### Binary Management
- Binary version is hardcoded in `download_binary()` (currently 0.5.2)
- Supports Linux, macOS, Windows on x86_64, ARM64, ARMv7, ARMv6
- Downloads from official GitHub releases
- Extracts from tar.gz (Unix) or zip (Windows)
- Makes executable on Unix systems

## Code Style

Uses Ruff for linting and formatting:
- Line length: 88 (Black-compatible)
- Python 3.12+ required
- Ignores: E501 (line too long), E741 (ambiguous variable names)
- Lint rules: flake8-bugbear, Pycodestyle, Pyflakes, pyupgrade
