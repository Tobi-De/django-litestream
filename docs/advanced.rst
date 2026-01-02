Advanced Features
=================

This page covers advanced VFS features including time-travel queries, automatic read distribution, and monitoring.

Time-Travel Queries
-------------------

Query VFS databases at specific points in time using the ``time_travel()`` context manager.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from django_litestream import time_travel
   from myapp.models import User, Order

   # Query data from 1 hour ago
   with time_travel("prod_replica", "1 hour ago") as db:
       old_users = User.objects.using(db).all()
       old_count = old_users.count()

   # Query at specific timestamp
   with time_travel("prod_replica", "2024-12-20 14:00:00") as db:
       orders = Order.objects.using(db).filter(status='pending')

Supported Time Formats
~~~~~~~~~~~~~~~~~~~~~~

- **Natural language**: ``"5 minutes ago"``, ``"1 hour ago"``, ``"2 days ago"``
- **ISO timestamps**: ``"2024-12-20 15:00:00"``
- **Any format supported by Litestream VFS**

How It Works
~~~~~~~~~~~~

1. Creates a temporary database alias with the same VFS configuration
2. Opens a connection and executes ``PRAGMA litestream_time='{time_point}'``
3. Yields the temporary alias for use with ``.using()``
4. Automatically cleans up the connection and removes the temporary database on exit

Use Cases
~~~~~~~~~

**Compare current vs historical data:**

.. code-block:: python

   current_users = User.objects.all().count()

   with time_travel("prod_replica", "24 hours ago") as db:
       yesterday_users = User.objects.using(db).all().count()

   growth = current_users - yesterday_users
   print(f"User growth: {growth} (+{growth/yesterday_users*100:.1f}%)")

**Investigate incidents:**

.. code-block:: python

   # Find what orders were pending before the system went down
   incident_time = "2024-12-20 14:30:00"

   with time_travel("prod_replica", incident_time) as db:
       pending_orders = Order.objects.using(db).filter(status='pending')
       print(f"Pending orders at incident: {pending_orders.count()}")

**Generate historical reports:**

.. code-block:: python

   from datetime import datetime, timedelta

   # Generate daily user counts for last week
   for days_ago in range(7):
       date = datetime.now() - timedelta(days=days_ago)
       timestamp = date.strftime("%Y-%m-%d 23:59:59")

       with time_travel("prod_replica", timestamp) as db:
           count = User.objects.using(db).count()
           print(f"{date.date()}: {count} users")

Automatic Read Distribution
----------------------------

The ``LitestreamRouter`` automatically routes read queries to VFS replicas and writes to the primary database.

Setup
~~~~~

.. code-block:: python

   # settings.py
   from django_litestream import get_vfs_databases

   LITESTREAM = {
       "vfs": {
           "prod_replica": "s3://mybucket/db.sqlite3",
           "analytics_replica": "s3://analytics/db.sqlite3",
           "max_lag_seconds": 60,  # Only use replicas with lag < 60s
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
   DATABASE_ROUTERS = ['django_litestream.db.routers.LitestreamRouter']

Usage
~~~~~

Once configured, the router works automatically - no code changes needed:

.. code-block:: python

   # Reads go to VFS replicas (automatic)
   users = User.objects.all()
   user = User.objects.get(id=1)
   total = Order.objects.count()

   # Writes go to primary database (automatic)
   new_user = User.objects.create(username="alice")
   user.save()
   Order.objects.filter(status='pending').update(status='processing')

   # Force specific database (bypasses router)
   primary_users = User.objects.using("default").all()
   replica_users = User.objects.using("prod_replica").all()

Router Behavior
~~~~~~~~~~~~~~~

- **Reads**: Randomly distributed across healthy VFS replicas (lag < ``max_lag_seconds``)
- **Writes**: Always routed to primary database
- **Migrations**: Only allowed on primary database
- **Relations**: Allowed between any databases (replicas are copies of primary)
- **Fallback**: Uses primary for reads if no healthy replicas available

Configuration
~~~~~~~~~~~~~

The only configuration option is ``max_lag_seconds`` in the VFS config:

.. code-block:: python

   LITESTREAM = {
       "vfs": {
           "prod_replica": "s3://mybucket/db.sqlite3",
           "max_lag_seconds": 60,  # Default: 60 seconds
       }
   }

The router auto-discovers all VFS databases and uses this threshold to determine which replicas are healthy.

Performance Considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~

- Router checks replica health on every read operation (calls ``get_vfs_status()``)
- For high-traffic applications, consider caching status checks
- Replica selection is random to distribute load evenly
- VFS extension polls for updates every 1 second

VFS Monitoring
--------------

Monitor VFS replica health using the ``get_vfs_status()`` function or management command.

Programmatic Monitoring
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from django_litestream import get_vfs_status

   status = get_vfs_status("prod_replica")

   # Returns:
   # {
   #     "is_vfs": True,
   #     "alias": "prod_replica",
   #     "replica_url": "s3://mybucket/db.sqlite3",
   #     "txid": 12345,  # Current transaction ID (or None)
   #     "lag_seconds": 2.5,  # Seconds since last poll (or None)
   # }

   # Check if replica is healthy
   if status["lag_seconds"] and status["lag_seconds"] < 60:
       print("✓ Replica is healthy")
   else:
       print("✗ Replica is stale or unavailable")

Management Command
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   python manage.py litestream vfs-status

Example output:

.. code-block:: text

   Found 2 VFS database(s):

   prod_replica:
     Replica URL: s3://mybucket/db.sqlite3
     Transaction ID: 12345
     Replication Lag: 2.5s
     Status: ✓ Healthy

   analytics_replica:
     Replica URL: s3://analytics/db.sqlite3
     Transaction ID: 8901
     Replication Lag: 125.0s (2.1m)
     Status: ⚠ Lagging

Status Indicators
~~~~~~~~~~~~~~~~~

- ✓ **Healthy**: Lag < 60s (green)
- ⚠ **Lagging**: Lag 60-300s (yellow)
- ✗ **Stale**: Lag > 300s (red)
- ? **Unknown**: Status unavailable

Integration with Monitoring Systems
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Export metrics to Prometheus, Datadog, or other monitoring systems:

.. code-block:: python

   from django_litestream import get_vfs_databases, get_vfs_status

   def export_vfs_metrics():
       """Export VFS metrics for monitoring."""
       vfs_dbs = get_vfs_databases()

       for alias in vfs_dbs:
           try:
               status = get_vfs_status(alias)

               # Export to your monitoring system
               metrics.gauge(
                   'litestream.vfs.lag_seconds',
                   status['lag_seconds'],
                   tags={'database': alias}
               )

               metrics.gauge(
                   'litestream.vfs.txid',
                   status['txid'],
                   tags={'database': alias}
               )

           except Exception as e:
               metrics.increment(
                   'litestream.vfs.errors',
                   tags={'database': alias}
               )

Best Practices
--------------

1. **Monitor replication lag:**

   Set up alerts for lag > 60s to catch replication issues early

2. **Use time-travel for debugging:**

   When investigating incidents, query historical state to understand what happened

3. **Configure router lag threshold:**

   Set ``max_lag_seconds`` based on your tolerance for stale data

4. **Separate analytics workloads:**

   Use dedicated VFS replicas for analytics to avoid impacting primary database

5. **Test failover behavior:**

   Verify your application handles replica unavailability gracefully

Example: Complete Setup
-----------------------

Here's a complete example combining all advanced features:

.. code-block:: python

   # settings.py
   from django_litestream import get_vfs_databases

   LITESTREAM = {
       # Regular replication
       "dbs": [{"path": "default"}],

       # VFS replicas with router config
       "vfs": {
           "prod_replica": "s3://mybucket/db.sqlite3",
           "analytics_replica": "s3://analytics/db.sqlite3",
           "max_lag_seconds": 60,  # Router threshold
       }
   }

   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.sqlite3",
           "NAME": BASE_DIR / "db.sqlite3",
       },
       **get_vfs_databases(),
   }

   # Enable automatic read distribution
   DATABASE_ROUTERS = ['django_litestream.db.routers.LitestreamRouter']

.. code-block:: python

   # views.py
   from django_litestream import time_travel, get_vfs_status
   from myapp.models import User, Order

   def analytics_dashboard(request):
       # Check replica health
       status = get_vfs_status("analytics_replica")

       if status["lag_seconds"] > 300:
           # Replica is stale, use primary
           users = User.objects.using("default").all()
       else:
           # Reads automatically go to healthy replicas via router
           users = User.objects.all()

       # Time-travel for historical comparison
       with time_travel("analytics_replica", "24 hours ago") as db:
           yesterday_count = User.objects.using(db).count()

       current_count = users.count()
       growth = current_count - yesterday_count

       return render(request, 'dashboard.html', {
           'users': users,
           'growth': growth,
           'replica_lag': status["lag_seconds"],
       })
