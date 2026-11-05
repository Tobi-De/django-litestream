from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


DJANGO_LITESTREAM_SETTINGS_NAME = "LITESTREAM"

# Keys consumed by the wrapper itself and therefore never written to the
# generated Litestream config. Everything else is forwarded verbatim so new
# upstream options work without a wrapper release.
WRAPPER_ONLY_SETTINGS = frozenset(
    {"path_prefix", "bin_path", "vfs", "vfs_extension_path"}
)


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
        return {
            key: value
            for key, value in self.user_settings.items()
            if key not in WRAPPER_ONLY_SETTINGS
        }


app_settings = AppSettings()
