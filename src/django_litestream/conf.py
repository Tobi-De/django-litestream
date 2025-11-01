from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


DJANGO_LITESTREAM_SETTINGS_NAME = "LITESTREAM"


@dataclass(frozen=True)
class AppSettings:
    @property
    def user_settings(self) -> dict[str, object]:
        return getattr(settings, DJANGO_LITESTREAM_SETTINGS_NAME, {})

    @property
    def path_prefix(self) -> str:
        return self.user_settings.get("path_prefix", "")

    @property
    def bin_path(self) -> Path:
        return Path(
            self.user_settings.get(
                "bin_path",
                Path(sys.executable).parent / "litestream",
            )
        )

    def litestream_settings(self) -> dict[str, object]:
        config = {}
        for key in [
            "dbs",
            "logging",
            "addr",
            "exec",
            "mcp-addr",
            "levels",
            "snapshot",
            "access-key-id",
            "secret-access-key",
        ]:
            if key in self.user_settings:
                config[key] = self.user_settings[key]
        return config


app_settings = AppSettings()
