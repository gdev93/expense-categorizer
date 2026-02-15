import re

import numpy as np
import pytest
from processors.similarity_matcher import generate_embedding

def cosine_similarity(v1, v2):
    """
    Calcola la similarità del coseno tra due vettori.
    """
    v1 = np.array(v1)
    v2 = np.array(v2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def test_embedding_cosine_similarity():
    # Descrizioni simili
    desc1 = "Operazione Mastercard del 14/01/2026 alle ore 00:06 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=146.28 / Importo in Euro=146.28 presso FISCOZEN* FISCOZEN"
    desc2 = "5179090005496786 FISCOZEN* FISCOZEN       MILANO       IT"

    def clean_for_ema(text):
        # 1. Rimuovi numeri lunghi (ID transazione, carte, IBAN)
        text = re.sub(r'\d{10,}', '<ID>', text)
        # 2. Rimuovi date
        text = re.sub(r'\d{2}/\d{2}/\d{4}', '<DATE>', text)
        # 3. Porta tutto minuscolo
        return text.lower().strip()

    # Generazione embedding
    emb1 = generate_embedding(clean_for_ema(text=desc1))
    emb2 = generate_embedding(clean_for_ema(text=desc2))

    # Calcolo similarità
    sim_1_2 = cosine_similarity(emb1, emb2)

    print(f"\nDescrizione 1: {desc1}")
    print(f"Descrizione 2: {desc2}")
    print(f"Similarità (1, 2): {sim_1_2:.4f}")

