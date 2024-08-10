import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand
from yaml import dump

from ...conf import app_settings

CONFIG_ARG = {
    "name": "-config",
    "type": Path,
    "help": f"Path to the litestream configuration file, default: {app_settings.config_file}",
    "default": app_settings.config_file,
    "required": False,
}

DB_PATH_ARG = {
    "name": "db_path",
    "type": Path,
    "help": "Path to the SQLite database file",
}

DB_PATH_OR_REPLICA_URL_ARG = {
    "name": "db_path",
    "help": "Path to the SQLite database file or replica URL",
}

NO_EXPAND_ENV_ARG = {
    "name": "-no-expand-env",
    "action": "store_true",
    "help": "Disables environment variable expansion in configuration file.",
    "required": False,
}


def _get_replica_arg(subcommand: str) -> dict:
    return {
        "name": "-replica",
        "help": f"Optional, filters by replica. Only applies when listing database {subcommand}.",
        "required": False,
    }


litestream_commands = {
    "databases": {
        "description": "List databases specified in config file",
        "arguments": [CONFIG_ARG, NO_EXPAND_ENV_ARG],
    },
    "generations": {
        "description": "List available generations for a database",
        "arguments": [
            CONFIG_ARG,
            NO_EXPAND_ENV_ARG,
            DB_PATH_OR_REPLICA_URL_ARG,
            _get_replica_arg("generations"),
        ],
    },
    "replicate": {
        "description": "Runs a server to replicate databases",
        "arguments": [
            CONFIG_ARG,
            NO_EXPAND_ENV_ARG,
            {
                "name": "-exec",
                "help": "Executes a subcommand. Litestream will exit when the child process exits. "
                "Useful for simple process management.",
                "required": False,
            },
            # {
            #     **DB_PATH_ARG,
            # },
            # {"name": "replica_url", "help": "URL of the replicas", "action": "append"}
        ],
    },
    "restore": {
        "description": "Recovers database backup from a replica",
        "arguments": [
            DB_PATH_OR_REPLICA_URL_ARG,
            CONFIG_ARG,
            NO_EXPAND_ENV_ARG,
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
                "help": "Determines the number of WAL files downloaded in parallel. Defaults to 8",
                "default": 8,
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
                "help": "Restore up to a specific WAL index (inclusive). Defaults to use the highest available index.",
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
    "snapshots": {
        "description": "List available snapshots for a database",
        "arguments": [
            DB_PATH_OR_REPLICA_URL_ARG,
            CONFIG_ARG,
            NO_EXPAND_ENV_ARG,
            _get_replica_arg("snapshots"),
        ],
    },
    "version": {"description": "Prints the binary version", "arguments": []},
    "wal": {
        "description": "List available WAL files for a database",
        "arguments": [
            CONFIG_ARG,
            NO_EXPAND_ENV_ARG,
            {
                "name": "-generation",
                "help": "Optional, filter by a specific generation.",
                "required": False,
            },
            _get_replica_arg("snapshots"),
        ],
    },
}


class Command(BaseCommand):
    help = "Litestream is a tool for replicating SQLite databases."

    def add_arguments(self, parser: ArgumentParser) -> None:
        subcommands = parser.add_subparsers(help="subcommands", dest="subcommand")
        init_cmd = subcommands.add_parser(
            "init",
            help="Initialize a new Litestream configuration",
            description="Initialize a new Litestream configuration",
        )

        _add_argument(init_cmd, CONFIG_ARG)

        for ls_cmd, details in litestream_commands.items():
            parser = subcommands.add_parser(
                ls_cmd,
                help=details["description"],
                description=details["description"],
            )
            for args in details["arguments"]:
                _add_argument(parser, args)

    def handle(self, *args, **options) -> None:
        if options["subcommand"] == "init":
            _init(filepath=options["config"])
            self.stdout.write(self.style.SUCCESS("Litestream configuration file created"))
        elif len(sys.argv) == 2:
            self.print_help("manage", "litestream")
        else:
            ls_args = sys.argv[2:]
            if "db_path" in options:
                # if database alias specified, replace it by the file location
                original_value = options["db_path"]
                db_path = _db_location_from_alias(original_value)
                index_original_value = ls_args.index(original_value)
                ls_args[index_original_value] = db_path
            if "-config" not in ls_args and options["subcommand"] != "version":
                ls_args.extend(["-config", str(options["config"])])
            # print(ls_args)
            subprocess.run([app_settings.bin_path, *ls_args])


def _db_location_from_alias(alias: str) -> str:
    db_settings = settings.DATABASES.get(alias, {})
    if db_settings.get("ENGINE") == "django.db.backends.sqlite3":
        return db_settings["NAME"]
    return alias


def _init(filepath: Path):
    if app_settings.dbs:
        dbs = app_settings.dbs
    else:
        dbs = []
        for db_settings in settings.DATABASES.values():
            if db_settings["ENGINE"] == "django.db.backends.sqlite3":
                location = str(db_settings["NAME"])
                dbs.append(
                    {
                        "path": location,
                        "replicas": [
                            {
                                "type": "s3",
                                "bucket": "$LITESTREAM_REPLICA_BUCKET",
                                "path": Path(location).name,
                                "access-key-id": "$LITESTREAM_ACCESS_KEY_ID",
                                "secret-access-key": "$LITESTREAM_SECRET_ACCESS_KEY",
                            }
                        ],
                    }
                )
        if app_settings.extra_dbs:
            dbs.extend(app_settings.extra_dbs)
    with open(filepath, "w") as f:
        dump({"dbs": dbs}, f, sort_keys=False)


def _add_argument(parser: ArgumentParser, args: dict) -> None:
    copied_args = args.copy()
    parser.add_argument(copied_args.pop("name"), **copied_args)
