from django.apps import AppConfig


class VfsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_litestream_vfs"

    def ready(self):
        from django_litestream_vfs.conf import vfs_settings
        from django_litestream_vfs.loader import ensure_vfs_loaded

        if not vfs_settings.vfs_config:
            return

        try:
            ensure_vfs_loaded()
        except Exception:
            pass
