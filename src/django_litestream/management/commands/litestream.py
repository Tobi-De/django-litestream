import subprocess
import sys
from argparse import ArgumentParser
from itertools import chain
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
    "help": "Path to the SQLite database file or django database alias",
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


class Command(BaseCommand):
    help = "Litestream is a tool for replicating SQLite databases."

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
                    "nargs": "+",
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
                DB_PATH_OR_REPLICA_URL_ARG,
                {
                    "name": "-generation",
                    "help": "Optional, filter by a specific generation.",
                    "required": False,
                },
                _get_replica_arg("snapshots"),
            ],
        },
    }

    def add_arguments(self, parser: ArgumentParser) -> None:
        subcommands = parser.add_subparsers(help="subcommands", dest="subcommand")
        init_cmd = subcommands.add_parser(
            "init",
            help="Initialize a new Litestream configuration",
            description="Initialize a new Litestream configuration",
        )

        _add_argument(init_cmd, CONFIG_ARG)

        for ls_cmd, details in self.litestream_commands.items():
            parser = subcommands.add_parser(
                ls_cmd,
                help=details["description"],
                description=details["description"],
            )
            for args in details["arguments"]:
                _add_argument(parser, args)

    def handle(self, *_, **options) -> None:
        if options["subcommand"] == "init":
            self.init(filepath=options["config"])
            self.stdout.write(self.style.SUCCESS("Litestream configuration file created"))
        elif options["subcommand"] == "version":
            subprocess.run([app_settings.bin_path, "version"])
        elif len(sys.argv) == 2:
            self.print_help("manage", "litestream")
        else:
            ls_args = self._parse_args(options["subcommand"], options)
            if options["verbosity"] > 1:
                self.stdout.write(f"Litestream bin: {app_settings.bin_path}")
                self.stdout.write(f"Litestream args: {ls_args}")
            try:
                subprocess.run([app_settings.bin_path, *ls_args])
            except KeyboardInterrupt:
                self.stdout.write(self.style.ERROR("Litestream command interrupted"))

    def _parse_args(self, subcommand: str, options: dict) -> list[str]:
        positionals = []
        optionals = []
        for argument in self.litestream_commands[subcommand]["arguments"]:
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

    def init(self, filepath: Path):
        dbs = app_settings.dbs if app_settings.dbs else []
        config = {"dbs": dbs}
        if app_settings.logging:
            config["logging"] = app_settings.logging
        if app_settings.addr:
            config["addr"] = app_settings.addr
        if not dbs:
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
        if app_settings.extend_dbs:
            dbs.extend(app_settings.extend_dbs)
        with open(filepath, "w") as f:
            dump(config, f, sort_keys=False)


def _db_location_from_alias(alias: str) -> str:
    db_settings = settings.DATABASES.get(alias, {})
    if db_settings.get("ENGINE") == "django.db.backends.sqlite3":
        return db_settings["NAME"]
    return alias


def _add_argument(parser: ArgumentParser, args: dict) -> None:
    copied_args = args.copy()
    parser.add_argument(copied_args.pop("name"), **copied_args)
