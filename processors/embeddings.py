import os

from fastembed import TextEmbedding

class EmbeddingEngine:
    _instance = None

    @classmethod
    def get_model(cls):
        if cls._instance is None:
            cls._instance = TextEmbedding(
                model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                threads= os.environ.get('EMBEDDED_THREADS_NUMBER', 4)
            )
        return cls._instance
