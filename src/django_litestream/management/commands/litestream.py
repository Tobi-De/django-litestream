from __future__ import annotations

import datetime as dt
import secrets
import sqlite3
import subprocess
import tempfile
import time
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.management import BaseCommand
import yaml
import sys

from django_litestream.conf import app_settings

if TYPE_CHECKING:
    from argparse import ArgumentParser

LITESTREAM_COMMANDS = {
    "databases": {
        "description": "List databases specified in config file",
        "arguments": [],
    },
    "ltx": {
        "description": "List available LTX files for a database",
        "arguments": [
            {
                "name": "db_path",
                "help": "Path to the SQLite database file or replica URL",
            },
            {
                "name": "-replica",
                "help": "Optional, filters by replica. Only applies when listing database LTX files.",
                "required": False,
            },
        ],
    },
    "replicate": {
        "description": "Runs a server to replicate databases",
        "arguments": [
            {
                "name": "-exec",
                "nargs": "+",
                "help": "Executes a subcommand. Litestream will exit when the child process exits. "
                "Useful for simple process management.",
                "required": False,
            },
        ],
    },
    "restore": {
        "description": "Recovers database backup from a replica",
        "arguments": [
            {
                "name": "db_path",
                "help": "Path to the SQLite database file or replica URL",
            },
            {
                "name": "-replica",
                "help": "Restore from a specific replica.Defaults to replica with latest data.",
                "required": False,
            },
            {
                "name": "-o",
                "type": Path,
                "help": "Output path of the restored database. Defaults to original DB path.",
                "required": False,
            },
            {
                "name": "-if-replica-exists",
                "action": "store_true",
                "help": "Returns exit code of 0 if no backups found.",
                "required": False,
            },
            {
                "name": "-if-db-not-exists",
                "action": "store_true",
                "help": "Returns exit code of 0 if the database already exists.",
                "required": False,
            },
            {
                "name": "-parallelism",
                "type": int,
                "help": "Determines the number of LTX files downloaded in parallel. Defaults to 8",
                "required": False,
            },
            {
                "name": "-generation",
                "help": "Restore from a specific generation. Defaults to generation with latest data",
                "required": False,
            },
            {
                "name": "-index",
                "type": int,
                "help": "Restore up to a specific LTX index (inclusive). Defaults to use the highest available index.",
                "required": False,
            },
            {
                "name": "-timestamp",
                # "type": datetime,
                "help": "Restore to a specific point-in-time. Defaults to use the latest available backup.",
                "required": False,
            },
        ],
    },
    "version": {"description": "Prints the binary version", "arguments": []},
}


class Command(BaseCommand):
    help = "Litestream is a tool for replicating SQLite databases."

    def add_arguments(self, parser: ArgumentParser) -> None:
        subcommands = parser.add_subparsers(help="subcommands", dest="subcommand")

        subcommands.add_parser(
            "config",
            help="Show the current Litestream configuration",
            description="Show the current Litestream configuration generated from Django settings",
        )

        for ls_cmd, details in LITESTREAM_COMMANDS.items():
            parser = subcommands.add_parser(
                ls_cmd,
                help=details["description"],
                description=details["description"],
            )
            for args in details["arguments"]:
                copied_args = args.copy()
                name = copied_args.pop("name")
                parser.add_argument(name, **copied_args)
            parser.add_argument(
                "-no-expand-env",
                action="store_true",
                help="Disables environment variable expansion in configuration file.",
                required=False,
            )

        verify_cmd = subcommands.add_parser(
            name="verify",
            help="Verify the integrity of backed-up databases",
            description="Verify the integrity of backed-up databases",
        )
        verify_cmd.add_argument(
            "db_path",
            help="Path to the SQLite database file or django database alias",
        )

    def handle(self, *_, **options) -> None:
        if options["subcommand"] == "config":
            with generate_temp_config() as config:
                self.stdout.write(Path(config).read_text())
        elif options["subcommand"] == "version":
            subprocess.run([app_settings.bin_path, "version"])
        elif options["subcommand"] == "verify":
            with generate_temp_config() as config:
                exit_code, msg = self.verify(
                    _db_location_from_alias(options["db_path"]), config=config
                )
            style = self.style.ERROR if exit_code else self.style.SUCCESS
            self.stdout.write(style(msg))
            exit(exit_code)
        elif not options["subcommand"]:
            self.print_help("manage", "litestream")
        else:
            with generate_temp_config() as config:
                options["config"] = Path(config)
                ls_args = self.parse_args(options["subcommand"], options)
                if options["verbosity"] > 2:
                    self.stdout.write(f"Options: {options}")
                if options["verbosity"] > 1:
                    self.stdout.write(f"Litestream bin: {app_settings.bin_path}")
                    self.stdout.write(f"Litestream args: {ls_args}")
                try:
                    subprocess.run([app_settings.bin_path, *ls_args], check=False)
                except KeyboardInterrupt:
                    self.stdout.write("Litestream command interrupted")

    def parse_args(self, subcommand: str, options: dict) -> list[str]:
        """This method formats the command line arguments for litestream binary."""
        positionals = []
        optionals = ["-config", str(options["config"])]

        for argument in LITESTREAM_COMMANDS[subcommand]["arguments"]:
            arg_name = argument["name"]
            dest = arg_name.strip("-").replace("-", "_")
            if dest not in options:
                continue
            value = options[dest]
            is_bool = isinstance(value, bool)
            if is_bool and not value:
                continue
            if value is None:
                continue
            if dest == "db_path":
                value = _db_location_from_alias(value)
            if isinstance(value, list):
                value = " ".join(value).strip()

            if arg_name.startswith("-"):
                if is_bool:
                    optionals.append(arg_name)
                else:
                    optionals.extend([arg_name, str(value)])
            else:
                positionals.append(str(value))
        return [subcommand, *list(chain(optionals)), *positionals]

    def verify(self, db_path: str | Path, config: str | Path) -> tuple[int, str]:
        self.stdout.write("Verifying...")
        data = secrets.token_hex(), dt.datetime.now()
        with sqlite3.connect(db_path) as db:
            cursor = db.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS _litestream_verification(id INTEGER PRIMARY KEY, code TEXT, created TEXT) strict;"""
            )
            cursor.execute(
                "INSERT INTO _litestream_verification (code, created) VALUES (?, ?)",
                data,
            )
            db.commit()

        time.sleep(10)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_db_path = (Path(temp_dir) / db_path).with_suffix(".restored").name
            result = subprocess.run(
                [
                    app_settings.bin_path,
                    "restore",
                    "-config",
                    config,
                    "-o",
                    temp_db_path,
                    db_path,
                ],
                stdout=subprocess.PIPE,
            )
            if result.returncode != 0:
                return result.returncode, "Database restore failed"

            with sqlite3.connect(temp_db_path) as db:
                cursor = db.cursor()
                cursor.execute(
                    "SELECT code, created FROM _litestream_verification WHERE code = ? and created = ?",
                    data,
                )
                row = cursor.fetchone()

        if not row:
            return 1, "Oops! Backup data seems to be out of sync"
        return 0, "All good! Backup data is in sync"


def _db_location_from_alias(alias: str) -> str:
    db_settings = settings.DATABASES.get(alias, {})
    if db_settings.get("ENGINE") == "django.db.backends.sqlite3":
        return db_settings["NAME"]
    return alias


@contextmanager
def generate_temp_config():
    """Generate a temporary litestream config file from Django settings."""
    config = app_settings.litestream_settings()
    dbs = config.get("dbs", [])
    processed_dbs = []
    for user_db in dbs:
        path = _db_location_from_alias(user_db["path"])
        db_settings = next(
            (s for s in settings.DATABASES.values() if s["NAME"] == path), None
        )
        if not db_settings:
            continue
        if db_settings["ENGINE"] != "django.db.backends.sqlite3":
            continue
        db_conf = {"path": str(path)}
        if "replica" not in user_db:
            # since we are adding replica config, add global credentials too if missing
            if "access-key-id" not in config:
                config["access-key-id"] = "$LITESTREAM_ACCESS_KEY_ID"
            if "secret-access-key" not in config:
                config["secret-access-key"] = "$LITESTREAM_SECRET_ACCESS_KEY"
            backup_path = Path(path).name
            path_prefix = app_settings.path_prefix.rstrip("/")
            backup_path = f"{path_prefix}/{backup_path}" if path_prefix else backup_path
            db_conf["replica"] = {
                "type": "s3",
                "bucket": "$LITESTREAM_REPLICA_BUCKET",
                "path": backup_path,
            }
        else:
            db_conf["replica"] = user_db["replica"]
        # validate the config here before adding
        processed_dbs.append(db_conf)

    config["dbs"] = processed_dbs

    if not processed_dbs:
        print("No valid SQLite databases found for Litestream configuration")
        raise sys.exit(1)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config, f, sort_keys=False)
        config_path = f.name

    try:
        yield config_path
    finally:
        Path(config_path).unlink(missing_ok=True)
