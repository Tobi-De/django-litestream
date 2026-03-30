Configuration
=============

django-litestream is configured via the ``LITESTREAM`` dictionary in your Django settings. Configuration is dynamically generated when you run commands—no config file needed!

Basic Configuration
-------------------

All configuration options (such as ``dbs``, ``logging``, ``addr``, ``mcp-addr``, ``access-key-id``, ``secret-access-key``, etc.) follow the same structure as the `Litestream configuration file <https://litestream.io/reference/config/>`_.

Configuration Options
---------------------

path_prefix
~~~~~~~~~~~

A string that will be prepended to the path of every database in the ``dbs`` configuration. This is useful if you are replicating databases from different projects to the same bucket.

.. code-block:: python

   LITESTREAM = {
       "path_prefix": "myproject",
       "dbs": [{"path": "default"}],
   }

   # Results in replica path: myproject/db.sqlite3

bin_path
~~~~~~~~

The path to the Litestream binary. If not found, the binary will be automatically downloaded on first use. You can specify a custom installation path here if needed.

Default: ``./venv/bin/litestream``

.. code-block:: python

   LITESTREAM = {
       "bin_path": "/custom/path/to/litestream",
       "dbs": [{"path": "default"}],
   }

dbs
~~~

List of databases to replicate. Each database entry can use a Django database alias or full path.

.. code-block:: python

   LITESTREAM = {
       "dbs": [
           {"path": "default"},  # Django alias
           {"path": "/full/path/to/db.sqlite3"},  # Full path
       ]
   }

vfs
~~~

VFS replica configuration for read-only access to cloud-stored databases. See :doc:`vfs` for details.

.. code-block:: python

   LITESTREAM = {
       "vfs": {
           "prod_replica": "s3://mybucket/db.sqlite3",
           "analytics_replica": "s3://analytics/db.sqlite3",
           "max_lag_seconds": 60,  # Optional, for router
       }
   }

Configuration Examples
----------------------

Simple Auto-Generated Replica
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The simplest configuration uses environment variables for credentials:

.. code-block:: python

   # settings.py
   LITESTREAM = {
       "dbs": [
           {"path": "default"},  # Use Django database alias
       ]
   }

This uses environment variables:

- ``LITESTREAM_REPLICA_BUCKET`` (or ``AWS_BUCKET``)
- ``LITESTREAM_ACCESS_KEY_ID`` (or ``AWS_ACCESS_KEY_ID``)
- ``LITESTREAM_SECRET_ACCESS_KEY`` (or ``AWS_SECRET_ACCESS_KEY``)

Manual Replica Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For more control, specify the replica configuration manually:

.. code-block:: python

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

Multiple Databases with Path Prefix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.sqlite3",
           "NAME": BASE_DIR / "db.sqlite3"
       },
       "cache": {
           "ENGINE": "django.db.backends.sqlite3",
           "NAME": BASE_DIR / "cache.sqlite3"
       },
   }

   LITESTREAM = {
       "path_prefix": "myproject",  # Prepended to replica paths
       "dbs": [
           {"path": "default"},  # → myproject/db.sqlite3
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

This generates the following configuration:

.. code-block:: yaml

   access-key-id: $LITESTREAM_ACCESS_KEY_ID
   secret-access-key: $LITESTREAM_SECRET_ACCESS_KEY
   dbs:
   - path: /home/user/myproject/db.sqlite3
     replica:
       type: s3
       bucket: $LITESTREAM_REPLICA_BUCKET
       path: myproject/db.sqlite3
   - path: /home/user/myproject/cache.sqlite3
     replica:
       type: s3
       bucket: my-cache-bucket
       path: custom-cache.sqlite3

VFS Read Replicas
~~~~~~~~~~~~~~~~~

Configure VFS replicas for read-only cloud access:

.. code-block:: python

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

See :doc:`vfs` for complete VFS documentation.

Environment Variables
---------------------

Litestream config uses environment variables for credentials. You can use either:

**Litestream-specific:**

- ``LITESTREAM_ACCESS_KEY_ID``
- ``LITESTREAM_SECRET_ACCESS_KEY``
- ``LITESTREAM_REPLICA_BUCKET``

**AWS-compatible:**

- ``AWS_ACCESS_KEY_ID``
- ``AWS_SECRET_ACCESS_KEY``
- ``AWS_BUCKET``

To disable environment variable expansion, use the ``-no-expand-env`` flag:

.. code-block:: bash

   python manage.py litestream replicate -no-expand-env

Cloud Provider Configuration
-----------------------------

S3 (AWS)
~~~~~~~~

.. code-block:: python

   LITESTREAM = {
       "dbs": [{
           "path": "default",
           "replica": {
               "type": "s3",
               "bucket": "my-bucket",
               "path": "db.sqlite3",
               "region": "us-east-1",
           }
       }]
   }

Google Cloud Storage
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   LITESTREAM = {
       "dbs": [{
           "path": "default",
           "replica": {
               "type": "gcs",
               "bucket": "my-bucket",
               "path": "db.sqlite3",
           }
       }]
   }

Azure Blob Storage
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   LITESTREAM = {
       "dbs": [{
           "path": "default",
           "replica": {
               "type": "abs",
               "bucket": "my-container",
               "path": "db.sqlite3",
               "account_name": "$AZURE_STORAGE_ACCOUNT",
               "account_key": "$AZURE_STORAGE_KEY",
           }
       }]
   }

SFTP
~~~~

.. code-block:: python

   LITESTREAM = {
       "dbs": [{
           "path": "default",
           "replica": {
               "type": "sftp",
               "host": "sftp.example.com",
               "user": "myuser",
               "path": "/backups/db.sqlite3",
               "key_path": "/home/user/.ssh/id_rsa",
           }
       }]
   }

For more configuration options, see the `Litestream configuration reference <https://litestream.io/reference/config/>`_.
