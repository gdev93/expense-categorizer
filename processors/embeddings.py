import os
import threading
from fastembed import TextEmbedding


class EmbeddingEngine:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_model(cls):
        with cls._lock:
            if cls._instance is None:
                # Define the cache directory from environment or default to a local folder
                cache_dir = os.environ.get('FASTEMBED_CACHE_PATH', './model_cache')

                cls._instance = TextEmbedding(
                    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                    threads=int(os.environ.get('EMBEDDED_THREADS_NUMBER', 4)),
                    cache_dir=cache_dir  # This ensures it looks into the persistent volume
                )
        return cls._instance