# django-litestream

[![PyPI - Version](https://img.shields.io/pypi/v/django-litestream.svg)](https://pypi.org/project/django-litestream)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-litestream.svg)](https://pypi.org/project/django-litestream)

-----

> [!IMPORTANT]
> This package currently contains minimal features and is a work-in-progress

This package installs and integrates [litestream](https://litestream.io), the SQLite replication tool, as a Django command.

## Table of Contents

- [django-litestream](#django-litestream)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Usage](#usage)
    - [Configuration](#configuration)
      - [Configuration Examples](#configuration-examples)
    - [Commands](#commands)
      - [litestream config](#litestream-config)
      - [litestream databases](#litestream-databases)
      - [litestream databases](#litestream-databases-1)
      - [litestream ltx](#litestream-ltx)
      - [litestream replicate](#litestream-replicate)
      - [litestream restore](#litestream-restore)
      - [litestream mcp](#litestream-mcp)
      - [litestream version](#litestream-version)
      - [litestream verify](#litestream-verify)
  - [License](#license)

## Installation

```console
pip install django-litestream
```

Add `django_litestream` to your Django `INSTALLED_APPS`.

## Usage

The package integrates all the commands and options from the `litestream` command-line tool with only minor changes.

> [!Note]
> Django 5.1 was released a few days ago (as of the time of writing). If you are
> looking for a good production configuration for SQLite, check out [this blog post](https://blog.pecar.me/sqlite-django-config#in-django-51-or-newer).

### Configuration

These are the available configurations for `django-litestream`:

```python
# settings.py
LITESTREAM = {
    "path_prefix": None,
    "bin_path": "litestream",
    "dbs": [],
    "logging": {},
    "addr": "",
    "mcp_addr": "",
}
```

> [!IMPORTANT]
> All litestream commands automatically use the configuration from your Django settings. Configuration is dynamically generated when you run commands - no config file needed!

The **path_prefix** is a string that will be prepended to the path of every database in the `dbs` configuration. This is useful if you are replicating databases from different projects to the same bucket, you could set the `path_prefix` to the project name so that the databases are stored in different folders in the bucket.

The **bin_path** is the path to the Litestream binary. If you want to use a custom installation, specify it here.

The **dbs** configuration allows you to specify which databases should be backed up by Litestream. You must explicitly list each database you want to replicate. For each database entry:
- If you omit the `replica` configuration, django-litestream will automatically generate a default S3 replica configuration using environment variables
- If you provide a `replica` configuration, your custom settings will be used exactly as specified

This explicit approach gives you full control over what gets backed up and ensures no databases are accidentally replicated.

The **logging** and **addr** configurations are the same as those in the Litestream configuration file.
You can read more about them [here](https://litestream.io/reference/config/#database-settings).
This allows you to keep all your litestream configuration in your Django settings.

The **mcp_addr** is the address for the Model Context Protocol (MCP) server. This enables AI assistants to interact with your Litestream databases and replicas through a standardized HTTP API. For example, you can set it to `":3001"` to listen on all interfaces or `"127.0.0.1:3001"` for localhost only (recommended for production). Learn more about MCP [here](https://litestream.io/reference/mcp/).

#### Configuration Examples

**Simple configuration with auto-generated replica:**
```python
# settings.py
LITESTREAM = {
    "dbs": [
        {"path": "default"},  # Use Django database alias
    ]
}
# This will use environment variables for S3 credentials:
# - LITESTREAM_REPLICA_BUCKET (or AWS_BUCKET)
# - LITESTREAM_ACCESS_KEY_ID (or AWS_ACCESS_KEY_ID)
# - LITESTREAM_SECRET_ACCESS_KEY (or AWS_SECRET_ACCESS_KEY)
```

**Manual replica configuration:**
```python
# settings.py
LITESTREAM = {
    "dbs": [
        {
            "path": "default",  # Django alias
            "replica": {
                "type": "s3",
                "bucket": "my-bucket",
                "path": "db.sqlite3",
                "region": "us-east-1",
            }
        }
    ]
}
```

**Multiple databases with path_prefix:**
```python
# settings.py
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"},
    "cache": {"ENGINE": "django.db.backends.sqlite3", "NAME": "cache.sqlite3"},
}

LITESTREAM = {
    "path_prefix": "myproject",  # Prepended to replica paths
    "dbs": [
        {"path": "default"},  # Will replicate to myproject/db.sqlite3
        {
            "path": "cache",
            "replica": {
                "type": "s3",
                "bucket": "my-cache-bucket",
                "path": "custom-cache.sqlite3",
            }
        }
    ]
}
```

### Commands

You can run `python manage.py litestream` to see all available commands.

#### litestream config

```console
python manage.py litestream config
```

This command displays the current Litestream configuration that will be used by all commands. It shows the configuration generated from your Django settings in YAML format. This is useful for:
- Verifying your configuration before running replication
- Debugging configuration issues
- Understanding what will be passed to the Litestream binary

The output matches the format of a litestream.yml file.

#### litestream databases

This works exactly like the equivalent [litestream command](https://litestream.io/reference/databases/) and lists all the databases.

Examples:

```console
python manage.py litestream databases
```

> [!IMPORTANT]
> For the rest of the commands, wherever you are asked to specify the database path `db_path`,
> you can use the Django database alias instead, for example, `default` instead of the full path to your database file.

For example, if you have the following `DATABASES` and `LITESTREAM` configuration:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    "other": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "other.sqlite3",
    },
}

LITESTREAM = {
    "dbs": [
        {"path": "default"},
        {"path": "other"},
    ]
}
```

And your `BASE_DIR` is `/home/tobi/myproject`, the dynamically generated configuration will look like this:

```yaml
access-key-id: $LITESTREAM_ACCESS_KEY_ID
secret-access-key: $LITESTREAM_SECRET_ACCESS_KEY
dbs:
- path: /home/tobi/myproject/db.sqlite3
  replica:
    type: s3
    bucket: $LITESTREAM_REPLICA_BUCKET
    path: db.sqlite3
- path: /home/tobi/myproject/other.sqlite3
  replica:
    type: s3
    bucket: $LITESTREAM_REPLICA_BUCKET
    path: other.sqlite3
```

You can tweak these settings according to your preferences. Check the [databases settings reference](https://litestream.io/reference/config/#database-settings) for more information.

You can omit the `access-key-id` and `secret-access-key` keys and litestream will automatically use any of the environment variables below if available:

- `AWS_ACCESS_KEY_ID` or `LITESTREAM_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY` or `LITESTREAM_SECRET_ACCESS_KEY`


#### litestream databases

This works exactly like the equivalent [litestream command](https://litestream.io/reference/databases/) and lists all the databases.

Examples:

```console
python manage.py litestream databases
```

> [!IMPORTANT]
> For the rest of the commands, wherever you are asked to specify the database path `db_path`,
> you can use the Django database alias instead, for example, `default` instead of `/home/tobi/myproject/db.sqlite3`.


#### litestream ltx

> [!NOTE]
> LTX support is available in Litestream v0.5.0+.

This works exactly like the equivalent [litestream command](https://litestream.io/reference/ltx/) and lists LTX (Litestream Transaction Log) files available for a database or replica. This command is mainly used for debugging and is not typically used in normal usage.

Examples:

```console
python manage.py litestream ltx default
python manage.py litestream ltx -replica s3 default
```

You can also specify a replica URL directly:

```console
python manage.py litestream ltx s3://mybkt.litestream.io/db
```

#### litestream replicate

This works exactly like the equivalent [litestream command](https://litestream.io/reference/replicate/), except it does not support the ability to replicate a single file.
Running `litestream replicate db_path replica_url` won't work. You can only run:

```console
python manage.py litestream replicate
python manage.py litestream replicate -exec "gunicorn myproject.wsgi:application"
```

This is the command you will run in production using a process manager as its own process. You can run it separately (the first example) or
use it to run your main Django process (second example). It would basically act as a process manager itself and run both the replicate
and the Django process. The replication process will exit when your web server shuts down.

#### litestream restore

This works exactly like the equivalent [litestream command](https://litestream.io/reference/restore/).

Examples:

```console
python manage.py litestream restore default
python manage.py litestream restore -if-replica-exists default
```


#### litestream mcp

> [!NOTE]
> MCP support is available in Litestream v0.5.0+. This feature is not available in v0.3.13.

The MCP (Model Context Protocol) server allows AI assistants to interact with Litestream databases and replicas through a standardized HTTP API. Unlike other litestream commands, MCP is not a standalone command but a server feature that runs alongside the `replicate` command.

To enable MCP, add the `mcp_addr` configuration to your Django settings:

```python
# settings.py
LITESTREAM = {
    "mcp_addr": ":3001",  # Listen on all interfaces
    # or for production (localhost only):
    # "mcp_addr": "127.0.0.1:3001",
}
```

The MCP server will automatically start when you run the replicate command:

```console
python manage.py litestream replicate
```

The MCP server exposes several tools for AI assistants:
- `litestream_info` - Get system status and configuration information
- `litestream_databases` - List all configured databases and their replica status
- `litestream_ltx` - View available LTX (transaction log) files for a specific database
- `litestream_restore` - Restore a database to a specific point in time

For more information about MCP integration and AI assistant setup, visit the [official documentation](https://litestream.io/reference/mcp/).

#### litestream version

Print the version of the Litestream binary.

```console
python manage.py litestream version
```

#### litestream verify

This command verifies the integrity of your backed-up databases. This process is inspired by the [verify command](https://github.com/fractaledmind/litestream-ruby?tab=readme-ov-file#verification) of the `litestream-ruby` gem.
The verification process involves the following steps:

1. **Add Verification Data**: A new row is added to a `_litestream_verification` table in the specified database. This table is created if it does not already exist. The row contains a unique code and the current timestamp.
2. **Wait for Replication**: The command waits for 10 seconds to allow Litestream to replicate the new row to the configured storage providers.
3. **Restore Backup**: The latest backup is restored from the storage provider to a temporary location.
4. **Check Verification Data**: The restored database is checked to ensure that the verification row is present. This ensures that the backup is both restorable and up-to-date.

If the verification row is not found in the restored database, the command will return an error indicating that the backup data is out of sync. If the row is found, the command confirms that the backup data is in sync.

Examples:

```console
python manage.py litestream verify default
```

This check ensures that the restored database file Exists, can be opened by SQLite, and has up-to-date data.

## License

`django-litestream` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
