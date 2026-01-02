Commands
========

All Litestream commands are available via ``python manage.py litestream <command>``. The package integrates all commands from the Litestream CLI tool with only minor changes.

.. note::

   For database paths (``db_path``), you can use Django database aliases (e.g., ``default``) instead of full paths.

Common Commands
---------------

config
~~~~~~

Display the current Litestream configuration generated from your Django settings.

.. code-block:: bash

   python manage.py litestream config

This shows the YAML configuration that will be passed to Litestream. Useful for:

- Verifying configuration before running replication
- Debugging configuration issues
- Understanding what will be passed to the Litestream binary

databases
~~~~~~~~~

List all databases configured for replication.

.. code-block:: bash

   python manage.py litestream databases

replicate
~~~~~~~~~

Runs the replication server to continuously replicate databases to cloud storage.

.. code-block:: bash

   # Run replication separately
   python manage.py litestream replicate

   # Run replication with your Django server (Litestream acts as process manager)
   python manage.py litestream replicate -exec "gunicorn myproject.wsgi:application"

This is the command you'll run in production. It can:

- Run as a separate process managed by systemd/supervisor
- Run your web server as a subprocess (``-exec`` flag)

When using ``-exec``, the replication process exits when your web server shuts down.

restore
~~~~~~~

Restore a database from its replica backup.

.. code-block:: bash

   # Basic restore
   python manage.py litestream restore default

   # Restore to specific location
   python manage.py litestream restore default -o /path/to/restored.db

   # Restore only if replica exists (useful for initialization)
   python manage.py litestream restore -if-replica-exists default

   # Restore only if database doesn't exist
   python manage.py litestream restore -if-db-not-exists default

   # Restore from specific replica
   python manage.py litestream restore default -replica s3

   # Restore to specific point in time
   python manage.py litestream restore default -timestamp "2024-12-20 14:00:00"

Options:

- ``-replica``: Restore from specific replica (defaults to replica with latest data)
- ``-o``: Output path of the restored database (defaults to original DB path)
- ``-if-replica-exists``: Returns exit code 0 if no backups found
- ``-if-db-not-exists``: Returns exit code 0 if database already exists
- ``-parallelism``: Number of LTX files downloaded in parallel (default: 8)
- ``-generation``: Restore from specific generation (defaults to latest)
- ``-index``: Restore up to specific LTX index (defaults to highest available)
- ``-timestamp``: Restore to specific point-in-time

ltx
~~~

.. note::

   LTX support requires Litestream v0.5.0+

List LTX (Litestream Transaction Log) files for a database or replica. Mainly used for debugging.

.. code-block:: bash

   # List LTX files for database
   python manage.py litestream ltx default

   # Filter by replica
   python manage.py litestream ltx default -replica s3

   # List from replica URL directly
   python manage.py litestream ltx s3://mybucket/db.sqlite3

version
~~~~~~~

Print the Litestream binary version.

.. code-block:: bash

   python manage.py litestream version

Custom Commands
---------------

verify
~~~~~~

Verify the integrity of backed-up databases. This is a custom command (not part of upstream Litestream).

.. code-block:: bash

   python manage.py litestream verify default

The verification process:

1. Adds a verification row to ``_litestream_verification`` table (created if needed)
2. Waits 10 seconds for replication to complete
3. Restores latest backup to temporary location
4. Checks if verification row exists in restored database
5. Returns success/failure based on backup sync status

This ensures the restored database:

- Exists and can be opened by SQLite
- Has up-to-date data (not stale)
- Is actually being replicated

vfs-install
~~~~~~~~~~~

Download and install the Litestream VFS extension for read-only replica access.

.. code-block:: bash

   python manage.py litestream vfs-install

The VFS extension enables on-demand access to cloud-stored replicas without downloading the entire database file.

See :doc:`vfs` for details.

vfs-status
~~~~~~~~~~

Show health status of all configured VFS replica databases.

.. code-block:: bash

   python manage.py litestream vfs-status

Output includes:

- Replica URL
- Transaction ID (current txid)
- Replication lag in seconds
- Health status (Healthy/Lagging/Stale/Unknown)

Color-coded status indicators:

- ✓ Healthy: Lag < 60s (green)
- ⚠ Lagging: Lag 60-300s (yellow)
- ✗ Stale: Lag > 300s (red)
- ? Unknown: Status unavailable

See :doc:`vfs` for VFS setup.

MCP Server
----------

.. note::

   MCP support requires Litestream v0.5.0+

The MCP (Model Context Protocol) server allows AI assistants to interact with Litestream databases and replicas. Unlike other commands, MCP is not standalone but a server feature that runs alongside ``replicate``.

Enable MCP in your settings:

.. code-block:: python

   # settings.py
   LITESTREAM = {
       "mcp-addr": ":3001",  # Listen on all interfaces
       # or for production (localhost only):
       # "mcp-addr": "127.0.0.1:3001",
   }

The MCP server starts automatically with the replicate command:

.. code-block:: bash

   python manage.py litestream replicate

Available MCP tools for AI assistants:

- ``litestream_info`` - Get system status and configuration
- ``litestream_databases`` - List databases and replica status
- ``litestream_ltx`` - View available LTX files for a database
- ``litestream_restore`` - Restore database to specific point in time

For more information, see the `official MCP documentation <https://litestream.io/reference/mcp/>`_.

Command Options
---------------

All commands support these common options:

-no-expand-env
~~~~~~~~~~~~~~

Disable environment variable expansion in configuration.

.. code-block:: bash

   python manage.py litestream replicate -no-expand-env

This is useful if you want to use literal ``$`` characters in your configuration instead of environment variable references.
