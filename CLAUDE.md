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
- Key settings: `path_prefix`, `bin_path`, `vfs_extension_path`, and all Litestream config options
- `path_prefix` is prepended to replica paths for multi-project bucket organization
- `bin_path` defaults to `<venv>/bin/litestream` but is auto-downloaded if missing

**Management Command (src/django_litestream/management/commands/litestream.py)**
- Single Django command that wraps all Litestream subcommands
- `generate_temp_config()` converts Django settings to temporary YAML config file
- Database alias resolution: users can specify "default" instead of full paths
- Auto-generates S3 replica config when not explicitly provided
- Binary auto-download on first use via `download_binary()`
- Custom `verify` subcommand (not part of upstream Litestream)

### Supported Commands

All upstream Litestream commands plus custom commands:

| Command | Description |
|---------|-------------|
| `databases` | List databases specified in config file |
| `ltx` | List available LTX files for a database |
| `replicate` | Runs a server to replicate databases |
| `restore` | Recovers database backup from a replica |
| `status` | Show replication status for databases |
| `sync` | Force immediate WAL-to-LTX sync |
| `version` | Prints the binary version |
| `config` | Show generated Litestream configuration (custom) |
| `verify` | Verify backup integrity (custom) |
| `vfs-install` | Download VFS extension (custom) |

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
- **VFS Extension**: Compiled SQLite extension (.so/.dylib) that registers a custom VFS handler
- **VFS Loader** (`vfs.py`): Thread-safe module that ensures extension loads exactly once per process
- **Custom Database Backend**: `django_litestream/db/backends/sqlite_vfs.py` extends Django's SQLite backend
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

**Configuration:**
```python
# settings.py
from django_litestream import get_vfs_databases

LITESTREAM = {
    "vfs": {
        "prod_replica": "s3://mybucket/db.sqlite3",
        "analytics_replica": "s3://analytics/analytics.db",
    }
}

DATABASES = {
    "default": {...},
    **get_vfs_databases(),  # Adds all VFS replicas
}
```

**Usage:**
```python
# Explicit replica usage with .using()
users = User.objects.using("prod_replica").all()
```

**VFS Extension Management:**
- Extension version hardcoded in `download_vfs_extension()` (currently 0.5.10)
- Only supports x86_64 and arm64 architectures (VFS limitation)
- Default install path: `<venv>/lib/litestream-vfs.so`
- Auto-downloads on first use (like main litestream binary)
- Manual install: `python manage.py litestream vfs-install`

**Key Differences from Regular Replication:**
- VFS is read-only (writes return errors)
- No local database file exists (virtual/on-demand)
- Completely separate config (`LITESTREAM["vfs"]` vs `LITESTREAM["dbs"]`)
- Requires VFS extension, not just litestream binary

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
- Binary version is hardcoded in `download_binary()` (currently 0.5.10)
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
