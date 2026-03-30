Installation
============

Requirements
------------

- Python 3.12+
- Django 5.0+
- SQLite database

Installation Steps
------------------

1. Install via pip:

.. code-block:: bash

   pip install django-litestream

2. Add to ``INSTALLED_APPS`` in your Django settings:

.. code-block:: python

   # settings.py
   INSTALLED_APPS = [
       # ...
       "django_litestream",
   ]

3. Configure Litestream:

.. code-block:: python

   # settings.py
   LITESTREAM = {
       "dbs": [
           {"path": "default"},  # Use Django database alias
       ]
   }

4. Set up environment variables for cloud storage credentials:

.. code-block:: bash

   # .env or environment
   export LITESTREAM_REPLICA_BUCKET=my-backup-bucket
   export LITESTREAM_ACCESS_KEY_ID=your-access-key
   export LITESTREAM_SECRET_ACCESS_KEY=your-secret-key

   # Or use AWS environment variables
   export AWS_BUCKET=my-backup-bucket
   export AWS_ACCESS_KEY_ID=your-access-key
   export AWS_SECRET_ACCESS_KEY=your-secret-key

Binary Auto-Download
--------------------

The Litestream binary is automatically downloaded on first use. By default, it's installed to ``<venv>/bin/litestream``.

You can customize the installation path:

.. code-block:: python

   # settings.py
   LITESTREAM = {
       "bin_path": "/custom/path/to/litestream",
       "dbs": [{"path": "default"}],
   }

Or manually download:

.. code-block:: bash

   python manage.py litestream version  # Triggers auto-download

Verify Installation
-------------------

Check that everything is set up correctly:

.. code-block:: bash

   # View generated configuration
   python manage.py litestream config

   # Check binary version
   python manage.py litestream version

   # List configured databases
   python manage.py litestream databases

Next Steps
----------

- See :doc:`configuration` for detailed configuration options
- See :doc:`commands` for available management commands
- See :doc:`vfs` for VFS replica setup
