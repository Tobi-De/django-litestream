django-litestream
=================

**Litestream integration for Django - SQLite replication made simple**

.. important::

   VFS support is currently in beta. The core replication features are production-ready.

django-litestream integrates `Litestream <https://litestream.io>`_ into Django, providing:

- ✅ Continuous SQLite replication to S3, GCS, Azure Blob Storage, and more
- ✅ Read-only VFS replicas for zero-download database access
- ✅ All Litestream commands via Django management commands
- ✅ Auto-download of Litestream binary on first use

Quick Start
-----------

.. code-block:: bash

   pip install django-litestream

.. code-block:: python

   # settings.py
   INSTALLED_APPS = [
       # ...
       "django_litestream",
   ]

   LITESTREAM = {
       "dbs": [
           {"path": "default"},  # Replicate default database
       ]
   }

.. code-block:: bash

   # Start continuous replication
   python manage.py litestream replicate

See :doc:`installation` for detailed setup instructions.

Features
--------

**Continuous Replication**

Replicate your SQLite databases to cloud storage in real-time:

.. code-block:: bash

   python manage.py litestream replicate
   python manage.py litestream restore default

**VFS Read Replicas**

Access cloud-stored replicas without downloading the entire database:

.. code-block:: python

   from django_litestream import get_vfs_databases

   DATABASES = {
       "default": {...},
       **get_vfs_databases(),  # Auto-configure VFS replicas
   }

   # Query from cloud replica
   users = User.objects.using('prod_replica').all()

Documentation
-------------

.. toctree::
   :maxdepth: 2

   installation
   configuration
   commands
   vfs

Community
---------

- `GitHub Repository <https://github.com/Tobi-De/django-litestream>`_
- `Issue Tracker <https://github.com/Tobi-De/django-litestream/issues>`_
- `Discussions <https://github.com/Tobi-De/django-litestream/discussions>`_

License
-------

django-litestream is distributed under the terms of the `MIT <https://spdx.org/licenses/MIT.html>`_ license.
