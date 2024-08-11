from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

if sys.version_info >= (3, 12):
    from typing import override as typing_override
else:  # pragma: no cover
    from typing_extensions import (
        override as typing_override,  # pyright: ignore[reportUnreachable]
    )

override = typing_override


DJANGO_LITESTREAM_SETTINGS_NAME = "LITESTREAM"


@dataclass(frozen=True)
class AppSettings:
    config_file: Path | str = "/etc/litestream.yml"
    bin_path: Path | str = "litestream"
    dbs: list[dict[str, str]] = None
    extend_dbs: list[dict[str, str]] = None
    logging: dict[str, str] = None
    addr: str | None = None

    @override
    def __getattribute__(self, __name: str) -> object:
        user_settings = getattr(settings, DJANGO_LITESTREAM_SETTINGS_NAME, {})
        return user_settings.get(__name, super().__getattribute__(__name))  # pyright: ignore[reportAny]


app_settings = AppSettings()
