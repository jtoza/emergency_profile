from django.apps import AppConfig


class MedicalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'medical'

    def ready(self):
        # Import signals so they are registered when the app is ready
        try:
            import medical.signals  # noqa: F401
        except Exception:
            # Avoid hard crash if migrations not yet applied; logs can be added if needed
            pass
