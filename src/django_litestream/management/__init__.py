def _get_sqlite_db_path() -> str:
    """Return the path to the SQLite database file."""
    from django.conf import settings

    db_settings = settings.DATABASES.get("default")
    if db_settings and db_settings.get("ENGINE") == "django.db.backends.sqlite3":
        return db_settings["NAME"]
    exit("No SQLite database found in settings")


def run_setup(_):
    """Run some project setup tasks"""
    import os
    import subprocess
    from pathlib import Path
    from django.core.management import execute_from_command_line
    from django.core.management.base import CommandError
    from contextlib import suppress

    db_path = _get_sqlite_db_path()
    # The Litestream configuration uses this environment variable, so it needs
    # to be injected into every function that runs the Litestream command.
    os.environ.setdefault("DATABASE_PATH", db_path)

    replica_url = os.getenv("REPLICA_URL")

    if not replica_url:
        exit("REPLICA_URL environment variable not set")

    if Path(db_path).exists():
        print("Database already exists, skipping restore")
    else:
        print("No database found, restoring from replica if exists")
        subprocess.run(["litestream", "restore", "-if-replica-exists", "-o", db_path, replica_url])

    execute_from_command_line(["manage", "migrate"])
    execute_from_command_line(["manage", "setup_periodic_tasks"])

    with suppress(CommandError):
        execute_from_command_line(["manage", "createsuperuser", "--noinput", "--traceback"])
