from django.test import TestCase
from processors.embeddings import EmbeddingEngine
import time

class EmbeddingsInitTest(TestCase):
    def test_embeddings_initialized(self):
        # Since it's initialized in a thread, we might need to wait a bit
        # but in tests, ready() is called when the app starts.
        
        # We wait up to 5 seconds for the instance to be initialized
        start_time = time.time()
        while EmbeddingEngine._instance is None and time.time() - start_time < 5:
            time.sleep(0.1)
            
        self.assertIsNotNone(EmbeddingEngine._instance, "EmbeddingEngine should be initialized on startup")
