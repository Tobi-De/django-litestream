from __future__ import annotations

import pytest
from django.test import override_settings
from yaml import Loader, load

from django_litestream.management.commands.litestream import Command

from .conftest import LITESTREAM


@pytest.fixture
def parser():
    return Command().create_parser("manage", "litestream")


@pytest.fixture
def temp_config_file(tmp_path):
    return tmp_path / "litestream.yml"


config_file = LITESTREAM["config_file"]


@pytest.mark.parametrize(
    "input_args,parsed_args",
    [
        ("databases", f"databases -config {config_file}"),
        ("generations default", f"generations -config {config_file} db.sqlite3"),
        (
            "generations -replica s3 default",
            f"generations -config {config_file} -replica s3 db.sqlite3",
        ),
        ("replicate", f"replicate -config {config_file}"),
        # (
        #     "replicate -exec 'python manage.py runserver'",
        #     f"replicate -config {config_file} -exec 'python manage.py runserver'",
        # ),
        ("restore default", f"restore -config {config_file} db.sqlite3"),
        (
            "restore -replica s3 -if-db-not-exists default -if-replica-exists",
            f"restore -config {config_file} -replica s3 -if-replica-exists -if-db-not-exists db.sqlite3",
        ),
        (
            "restore -replica s3 -if-db-not-exists default -if-replica-exist -o db2.sqlite2",
            f"restore -config {config_file} -replica s3 -o db2.sqlite2 -if-replica-exists -if-db-not-exists db.sqlite3",
        ),
        (
            "snapshots default -replica s3",
            f"snapshots -config {config_file} -replica s3 db.sqlite3",
        ),
        (
            "wal default -replica s3",
            f"wal -config {config_file} -replica s3 db.sqlite3",
        ),
    ],
)
def test_parse_args(parser, input_args, parsed_args):
    input_list = input_args.split(" ")
    parsed_args_list = parsed_args.split(" ")

    namespace = parser.parse_args(input_list)
    ls_args = Command().parse_args(subcommand=input_list[0], options=vars(namespace))
    assert ls_args == parsed_args_list


def test_init(temp_config_file):
    Command().init(temp_config_file)
    with open(temp_config_file) as f:
        config = load(f, Loader=Loader)

    assert config == {
        "dbs": [
            {
                "path": "db.sqlite3",
                "replicas": [
                    {
                        "type": "s3",
                        "bucket": "$LITESTREAM_REPLICA_BUCKET",
                        "path": "db.sqlite3",
                        "access-key-id": "$LITESTREAM_ACCESS_KEY_ID",
                        "secret-access-key": "$LITESTREAM_SECRET_ACCESS_KEY",
                    }
                ],
            }
        ]
    }


def test_init_override_db(temp_config_file):
    litestream_config = {
        "config_file": temp_config_file,
        "dbs": [
            {
                "path": "db2.sqlite3",
                "replicas": [
                    {
                        "type": "s3",
                        "bucket": "bucket",
                        "path": "db2.sqlite3",
                        "access-key-id": "access-key",
                        "secret-access": "secret",
                    }
                ],
            }
        ]
    }
    with override_settings(LITESTREAM=litestream_config):
        Command().init(temp_config_file)
        with open(temp_config_file) as f:
            config = load(f, Loader=Loader)

    assert config == {"dbs": litestream_config["dbs"]}


def test_init_extend_dbs(temp_config_file):
    litestream_config = {
        "config_file": temp_config_file,
        "extend_dbs": [
            {
                "path": "db2.sqlite3",
                "replicas": [
                    {
                        "type": "s3",
                        "bucket": "bucket",
                        "path": "db2.sqlite3",
                        "access-key-id": "access-key",
                        "secret-access": "secret",
                    }
                ],
            }
        ],
    }
    with override_settings(LITESTREAM=litestream_config):
        Command().init(temp_config_file)
        with open(temp_config_file) as f:
            config = load(f, Loader=Loader)

    assert config == {
        "dbs": [
            {
                "path": "db.sqlite3",
                "replicas": [
                    {
                        "type": "s3",
                        "bucket": "$LITESTREAM_REPLICA_BUCKET",
                        "path": "db.sqlite3",
                        "access-key-id": "$LITESTREAM_ACCESS_KEY_ID",
                        "secret-access-key": "$LITESTREAM_SECRET_ACCESS_KEY",
                    }
                ],
            },
            litestream_config["extend_dbs"][0],
        ]
    }
