import numpy as np
from django.test import TestCase
from processors.similarity_matcher import is_rag_reliable, generate_embedding

class SimilarityMatcherTest(TestCase):
    def test_embedding_cosine_distance(self):
        desc1 = "Operazione Mastercard del 27/01/2026 alle ore 13:49 con Carta xxxxxxxxxxxx3352 Div=EUR Importo in divisa=5.99 / Importo in Euro=5.99 presso VERY - ACQUISTO OFFERT"
        desc2 = "Operazione Mastercard del 23/12/2025 alle ore 04:10 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=106.08 / Importo in Euro=106.08 presso SQUARELIFE INSURANCE"
        
        emb1 = generate_embedding(desc1)
        emb2 = generate_embedding(desc2)
        
        # Calculate cosine distance
        u = np.array(emb1)
        v = np.array(emb2)
        dist = 1.0 - np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v))
        
        # The calculated distance was 0.018731
        self.assertAlmostEqual(dist, 0.018731, places=5)

    def test_is_rag_reliable_with_provided_inputs(self):
        new_desc = "Operazione Mastercard del 27/01/2026 alle ore 13:49 con Carta xxxxxxxxxxxx3352 Div=EUR Importo in divisa=5.99 / Importo in Euro=5.99 presso VERY - ACQUISTO OFFERT"
        match_desc = "Operazione Mastercard del 23/12/2025 alle ore 04:10 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=106.08 / Importo in Euro=106.08 presso SQUARELIFE INSURANCE"
        target_merchant_name = "SQUARELIFE INSURANCE"
        
        result = is_rag_reliable(new_desc, match_desc, target_merchant_name)
        
        self.assertFalse(result, "is_rag_reliable should return False for different merchants")

    def test_is_rag_reliable_with_same_merchant(self):
        new_desc = "Operazione Mastercard del 27/01/2026 alle ore 13:49 presso SQUARELIFE INSURANCE"
        match_desc = "Operazione Mastercard del 23/12/2025 alle ore 04:10 presso SQUARELIFE INSURANCE"
        target_merchant_name = "SQUARELIFE INSURANCE"
        
        # Even if there are differences (date/time), if they are digits they are ignored.
        # But wait, 'xxxxxxxxxxxx3352' is NOT all digits.
        # In this simplified case, "SQUARELIFE" and "INSURANCE" are in both.
        # "Operazione", "Mastercard", "del", "alle", "ore", "presso" are in both.
        # Differences will be dates/times/card numbers.
        
        result = is_rag_reliable(new_desc, match_desc, target_merchant_name)
        self.assertTrue(result, "is_rag_reliable should return True for same merchant even with different dates")

    def test_is_rag_reliable_with_same_merchant_different_cards(self):
        new_desc = "Operazione Mastercard presso SQUARELIFE INSURANCE con Carta xxxxxxxxxxxx3352"
        match_desc = "Operazione Mastercard presso SQUARELIFE INSURANCE con Carta xxxxxxxxxxxx7329"
        target_merchant_name = "SQUARELIFE INSURANCE"
        
        # Differences will include the card numbers, which are NOT all digits.
        # So important_diffs will not be empty.
        # But since the merchant is the same, find() will succeed.
        
        result = is_rag_reliable(new_desc, match_desc, target_merchant_name)
        self.assertTrue(result, "is_rag_reliable should return True for same merchant even if card numbers differ")
