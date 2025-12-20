from django.apps import AppConfig


class DjangoLitestreamConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_litestream"

    def ready(self):
        from django_litestream.vfs import ensure_vfs_loaded
        from django_litestream.conf import app_settings

        # load vfs if user has configured VFS databases
        vfs_config = app_settings.user_settings.get("vfs", {})
        if bool(vfs_config):
            try:
                ensure_vfs_loaded()
            except Exception:
                # Don't crash Django startup if VFS loading fails
                # The database backend will try again and show a proper error
                pass
