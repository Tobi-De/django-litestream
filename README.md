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
    - [Commands](#commands)
      - [litestream init](#litestream-init)
      - [litestream databases](#litestream-databases)
      - [litestream generations](#litestream-generations)
      - [litestream replicate](#litestream-replicate)
      - [litestream restore](#litestream-restore)
      - [litestream verify](#litestream-verify)
      - [litestream snapshots](#litestream-snapshots)
      - [litestream wal](#litestream-wal)
      - [litestream version](#litestream-version)
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
    "config_file": "/etc/litestream.yml",
    "path_prefix": None,
    "bin_path": "litestream",
    "dbs": [],
    "extend_dbs": [],
    "logging": {},
    "addr": "",
}
```

The **config_file** is where the Litestream configuration file should be generated by the [init command](#litestream-init).
The **config_file** will be automatically passed to every command you run, so you can freely change the default location 
without having to pass the `-config` argument manually each time. 
For example, you could place it in your project directory:

```python
# settings.py
LITESTREAM = {
    "config_file": BASE_DIR / "litestream.yml",
    ...
}
```

The **path_prefix** is a string that will be prepended to the path of every database in the `dbs` configuration. This is useful if you are replicating databases from different projects to the same bucket, you could set the `path_prefix` to the project name so that the databases are stored in different folders in the bucket.

The **bin_path** is the path to the Litestream binary. If you want to use a custom installation, specify it here.

The **dbs**, **logging**, and **addr** configurations are the same as those in the Litestream configuration file. 
You can read more about them [here](https://litestream.io/reference/config/#database-settings). 
This allows you to keep your litestream configuration in your Django settings.

The **extend_dbs** is a list of dictionaries with the same format as the `dbs` configuration, and, 
as its name suggests, it will extend the `dbs` configuration when the final configuration is generated.

### Commands

You can run `python manage.py litestream` to see all available commands.

#### litestream init

```console
python manage.py litestream init
```

This command will write the Litestream configuration to the indicated **config_file** based on your settings. 
If you did not specify any values in the **dbs** key, it will automatically parse your Django `DATABASES` configuration 
and write one `s3` replica for each SQLite database it finds. 

For example, if you have the following `DATABASES` configuration:

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
```

And your `BASE_DIR` is `/home/tobi/myproject`, the generated configuration after running `init` will look like this:

```yaml
dbs:
- path: /home/tobi/myproject/db.sqlite3
  replicas:
  - type: s3
    bucket: $LITESTREAM_REPLICA_BUCKET
    path: db.sqlite3
    access-key-id: $LITESTREAM_ACCESS_KEY_ID
    secret-access-key: $LITESTREAM_SECRET_ACCESS_KEY
- path: /home/tobi/myproject/other.sqlite3
  replicas:
  - type: s3
    bucket: $LITESTREAM_REPLICA_BUCKET
    path: other.sqlite3
    access-key-id: $LITESTREAM_ACCESS_KEY_ID
    secret-access-key: $LITESTREAM_SECRET_ACCESS_KEY
```

You can tweak these settings according to your preferences. Check the [databases settings reference](https://litestream.io/reference/config/#database-settings) for more information.

If you have any entries in the **dbs** configuration, the `init` command won’t automatically parse the `DATABASES` configuration.
To extend the configuration generated by the `init` command, you should use the **extend_dbs** configuration, for example:

```python
# settings.py
LITESTREAM = {
    "config_file": BASE_DIR / "litestream.yml",
    "extend_dbs": [
        {
            "path": BASE_DIR / "cache.sqlite3",
            "replicas": [
                {
                    "type": "s3",
                    "bucket": "$LITESTREAM_REPLICA_BUCKET",
                    "path": "cache.sqlite3",
                    "access-key-id": "$LITESTREAM_ACCESS_KEY_ID",
                    "secret-access-key": "$LITESTREAM_SECRET_ACCESS_KEY",
                }
            ]
        }
    ]
}
```

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

#### litestream generations

This works exactly like the equivalent [litestream command](https://litestream.io/reference/generations/).

Examples:

```console
python manage.py litestream generations default
python manage.py litestream generations -replica s3 default
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

#### litestream snapshots

This works exactly like the equivalent [litestream command](https://litestream.io/reference/snapshots/). 

Examples:

```console
python manage.py litestream snapshots default
python manage.py litestream snapshots -replica s3 default
```

#### litestream wal

This works exactly like the equivalent [litestream command](https://litestream.io/reference/wal/).

Examples:

```console
python manage.py litestream wal default
python manage.py litestream wal -replica s3 default
```

#### litestream version

Print the version of the Litestream binary.

```console
python manage.py litestream version
```

## License

`django-litestream` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
