from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import override

from django.conf import settings


DJANGO_LITESTREAM_SETTINGS_NAME = "LITESTREAM"


@dataclass(frozen=True)
class AppSettings:
    config_file: Path | str = "/etc/litestream.yml"
    path_prefix: str | None = None
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
