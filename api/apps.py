from django.apps import AppConfig
from django.db.models.signals import post_save



class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        import threading
        import logging
        from processors.embeddings import EmbeddingEngine
        import api.signals  # noqa: F401

        def initialize_embeddings():
            try:
                EmbeddingEngine.get_model()
            except Exception as e:
                logging.error(f"Failed to initialize EmbeddingEngine: {e}")

        threading.Thread(target=initialize_embeddings, daemon=True).start()
