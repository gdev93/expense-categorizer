import pytest
import re
import numpy as np
from processors.embeddings import EmbeddingEngine

def generate_embedding(text: str) -> list[float]:
    """
    Generates embedding for a string using the project's EmbeddingEngine.
    """
    texts = [(text or '').strip()]
    embeddings = list(EmbeddingEngine.get_model().embed(texts))
    return embeddings[0].tolist() if embeddings else []

def cosine_distance(v1: list[float], v2: list[float]) -> float:
    """
    Calculates cosine distance (1 - cosine similarity) between two vectors.
    """
    a = np.array(v1)
    b = np.array(v2)
    # Cosine similarity calculation
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    
    similarity = np.dot(a, b) / (norm_a * norm_b)
    return 1.0 - float(similarity)

def test_calculate_issue_description_embedding():
    """
    Test requested by user to calculate embedding and cosine distance for specific descriptions.
    """
    description1 = "Operazione Mastercard del 29/06/2025 alle ore 15:20 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=3 / Importo in Euro=3 presso 9                 -"
    description2 = "Operazione Mastercard del 18/01/2026 alle ore 08:08 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=10.6 / Importo in Euro=10.6 presso LA RONDINE - SOCIETA' - Transazione C-less"
    
    # Raw comparison
    emb1 = generate_embedding(description1)
    emb2 = generate_embedding(description2)
    dist = cosine_distance(emb1, emb2)
    
    print(f"\n--- Description 1: {description1}")
    print(f"--- Description 2: {description2}")
    print(f"Cosine Distance: {dist:.6f}")
    
    # Dimensions check
    assert len(emb1) == 384
    
    # Verify distance is within reasonable range [0, 2]
    assert 0 <= dist <= 2
