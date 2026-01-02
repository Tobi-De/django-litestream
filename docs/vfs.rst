VFS Read Replicas
=================

.. note::

   VFS support requires Litestream v0.5.0+ and is currently in beta.

The VFS (Virtual File System) feature enables read-only access to database replicas stored in cloud object storage without downloading the entire database file. Pages are fetched on-demand and cached in memory.

Quick Start
-----------

1. Install the VFS extension:

.. code-block:: bash

   python manage.py litestream vfs-install

2. Configure VFS replicas:

.. code-block:: python

   # settings.py
   from django_litestream import get_vfs_databases

   LITESTREAM = {
       # Regular replication
       "dbs": [{"path": "default"}],

       # VFS read replicas
       "vfs": {
           "prod_replica": "s3://mybucket/db.sqlite3",
           "analytics_replica": "s3://analytics/db.sqlite3",
       }
   }

   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.sqlite3",
           "NAME": BASE_DIR / "db.sqlite3",
       },
       **get_vfs_databases(),  # Adds VFS replicas
   }

3. Use VFS replicas in your code:

.. code-block:: python

   from myapp.models import User

   # Read from VFS replica
   users = User.objects.using('prod_replica').all()

   # Regular queries use primary database
   new_user = User.objects.create(username="alice")

How It Works
------------

**Architecture:**

1. User calls ``get_vfs_databases()`` to generate VFS database configurations
2. On Django startup, the VFS extension loads once per process (thread-safe)
3. When opening a VFS connection, Django sets the replica URL environment variable
4. SQLite uses the VFS handler to fetch pages from cloud storage on-demand
5. VFS extension polls for updates every 1 second

**Key Benefits:**

- ✅ No download required - pages fetched on-demand
- ✅ Memory efficient - only active pages cached
- ✅ Low latency - cached pages served from memory
- ✅ Auto-updating - polls for changes every second
- ✅ Multi-cloud - S3, GCS, Azure, SFTP, local files

Configuration
-------------

Simple Mapping
~~~~~~~~~~~~~~

VFS configuration is just ``{alias: replica_url}`` - no nested config needed:

.. code-block:: python

   LITESTREAM = {
       "vfs": {
           "prod_replica": "s3://mybucket/db.sqlite3",
           "analytics_replica": "gcs://my-gcs-bucket/data.db",
           "azure_replica": "abs://mycontainer/db.sqlite3",
       }
   }

Supported URL Formats
~~~~~~~~~~~~~~~~~~~~~

- ``s3://bucket/path`` - Amazon S3
- ``gcs://bucket/path`` - Google Cloud Storage
- ``abs://container/path`` - Azure Blob Storage
- ``file:///path/to/file`` - Local file
- ``sftp://host/path`` - SFTP server

Extension Management
~~~~~~~~~~~~~~~~~~~~

The VFS extension is automatically downloaded if missing. Default install path: ``<venv>/lib/litestream-vfs.so``

Customize the path:

.. code-block:: python

   LITESTREAM = {
       "vfs_extension_path": "/custom/path/to/litestream-vfs.so",
       "vfs": {...},
   }

Manual installation:

.. code-block:: bash

   python manage.py litestream vfs-install

Supported platforms:

- Linux: x86_64, arm64
- macOS: x86_64, arm64
- Windows: x86_64, arm64

Usage Patterns
--------------

Basic Read Operations
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from myapp.models import User, Order

   # Read from VFS replica
   users = User.objects.using('prod_replica').all()
   user = User.objects.using('prod_replica').get(id=1)

   # Aggregate queries
   total = Order.objects.using('prod_replica').count()
   revenue = Order.objects.using('prod_replica').aggregate(Sum('amount'))

Analytics Queries
~~~~~~~~~~~~~~~~~

Use VFS replicas for heavy analytics without impacting your primary database:

.. code-block:: python

   # Heavy analytics on replica
   stats = Order.objects.using('analytics_replica').annotate(
       month=TruncMonth('created_at')
   ).values('month').annotate(
       total=Sum('amount'),
       count=Count('id')
   ).order_by('month')

Monitoring Health
~~~~~~~~~~~~~~~~~

Check replica health status:

.. code-block:: python

   from django_litestream import get_vfs_status

   status = get_vfs_status("prod_replica")

   if status["lag_seconds"] and status["lag_seconds"] < 60:
       print(f"Replica is healthy (lag: {status['lag_seconds']}s)")
   else:
       print("Replica is stale or unavailable")

Or use the management command:

.. code-block:: bash

   python manage.py litestream vfs-status

Limitations
-----------

**VFS replicas are read-only:**

- Write operations will fail with an error
- Use the primary database for all writes
- See :doc:`advanced` for automatic read/write routing

**Platform support:**

- Only x86_64 and arm64 architectures
- Linux, macOS, and Windows only

**Performance:**

- First access to pages requires network fetch
- Subsequent access served from memory cache
- Polling interval is 1 second (configurable in VFS extension)

Best Practices
--------------

1. **Use for read-heavy workloads:**

   - Analytics and reporting
   - Background jobs that don't modify data
   - Read-only APIs

2. **Monitor replication lag:**

   Use ``vfs-status`` command to ensure replicas are healthy

3. **Separate concerns:**

   - Primary database: all writes
   - VFS replicas: heavy reads, analytics

4. **Consider using the router:**

   See :doc:`advanced` for automatic read distribution

Troubleshooting
---------------

**"VFS extension not found"**

Install the extension:

.. code-block:: bash

   python manage.py litestream vfs-install

**"Failed to fetch from replica"**

Check:

- Replica URL is correct
- Cloud credentials are configured
- Network connectivity to storage provider

**"Replica is stale"**

Check replication status:

.. code-block:: bash

   python manage.py litestream databases
   python manage.py litestream vfs-status

Ensure the primary replication process is running:

.. code-block:: bash

   python manage.py litestream replicate

Next Steps
----------

- See :doc:`advanced` for time-travel queries and automatic routing
- See `Litestream VFS documentation <https://litestream.io/guides/vfs/>`_
