import re

import numpy as np
import pytest
from processors.embeddings import EmbeddingEngine

def preprocess_text(text):
    """
    Cleans and enriches the text to improve vector focus.
    Using English names and comments as per instructions.
    """

    # Context injection: tells the model these are 'financial categories'
    # This helps distinguish 'Abbonamenti' (subscriptions) from 'Abbigliamento' (clothes)
    return f"Pagamento per la categoria: {text}"

def generate_embedding(text: str) -> list[float]:
    """
    Generates embedding for a string without using the database.
    """
    processed_text = preprocess_text(text)
    texts = [(processed_text or '').strip()]
    embeddings = list(EmbeddingEngine.get_model().embed(texts))
    return embeddings[0].tolist() if embeddings else []

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

def test_compute_embeddings_for_lists():
    list1 = [
        "Spesa", "Shopp", "Affitto", "Sport", "Partita IVA", "Auto", "Regali",
        "Carburante", "Shopping", "Abbonamenti", "Scuola", "Bollette", "Vacanze",
        "Trasporti", "Spese mediche", "Vita sociale", "Casa", "Bambini",
        "Cure Personali", "Donazioni", "Tasse"
    ]

    list2 = [
        "Affitto/Mutuo", "Utenze", "Internet e Telefono",
        "Casa - Spese e Manutenzione", "Spesa Alimentare", "Bar e Caffè",
        "Ristoranti e Pranzi Fuori", "Carburante", "Trasporti e Spostamenti",
        "Auto - Gestione", "Abbigliamento", "Casa e Arredamento",
        "Libri e Cartoleria", "Regali", "Salute", "Cura Personale",
        "Sport e Fitness", "Intrattenimento Fuori Casa", "Abbonamenti Digitali",
        "Viaggi e Vacanze", "Hobby e Passioni", "Animali Domestici",
        "Istruzione", "Corsi e Formazione", "Assistenza Familiare",
        "Servizi Bancari e Assicurativi", "Tasse e Professionisti",
        "Finanziamenti", "Beneficenza", "Shopping Online"
    ]

    print("\nComputing embeddings for list 1:")
    for val in list1:
        emb = generate_embedding(val)
        print(f"Value: {val}, Embedding size: {len(emb)}")
        assert len(emb) == 384  # paraphrase-multilingual-MiniLM-L12-v2 embedding size is 384

    print("\nComputing embeddings for list 2:")
    for val in list2:
        emb = generate_embedding(val)
        print(f"Value: {val}, Embedding size: {len(emb)}")
        assert len(emb) == 384

def test_similarity_matrix():
    list1 = [
        "Spesa", "Shopping", "Affitto", "Sport", "Partita IVA", "Auto", "Regali",
        "Carburante", "Shopping", "Abbonamenti", "Scuola", "Bollette", "Vacanze",
        "Trasporti", "Spese mediche", "Vita sociale", "Casa", "Bambini",
        "Cure Personali", "Donazioni", "Tasse"
    ]

    list2 = [
        "Affitto/Mutuo", "Utenze", "Internet e Telefono",
        "Casa - Spese e Manutenzione", "Spesa Alimentare", "Bar e Caffè",
        "Ristoranti e Pranzi Fuori", "Carburante", "Trasporti e Spostamenti",
        "Auto - Gestione", "Abbigliamento", "Casa e Arredamento",
        "Libri e Cartoleria", "Regali", "Salute", "Cura Personale",
        "Sport e Fitness", "Intrattenimento Fuori Casa", "Abbonamenti Digitali",
        "Viaggi e Vacanze", "Hobby e Passioni", "Animali Domestici",
        "Istruzione", "Corsi e Formazione", "Assistenza Familiare",
        "Servizi Bancari e Assicurativi", "Tasse e Professionisti",
        "Finanziamenti", "Beneficenza", "Shopping Online"
    ]

    # Pre-compute embeddings for both lists
    embs1 = {val: generate_embedding(val) for val in list1}
    embs2 = {val: generate_embedding(val) for val in list2}

    # Compute similarity matrix in a dictionary
    similarity_matrix = {}
    top_matches = {}
    for val1 in list1:
        similarity_matrix[val1] = {}
        matches = []
        for val2 in list2:
            sim = cosine_similarity(embs1[val1], embs2[val2])
            similarity_matrix[val1][val2] = float(sim)
            matches.append({"match": val2, "similarity": float(sim)})
        
        # Ordina per similarità decrescente e prendi i primi 3
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        top_matches[val1] = matches[:3]

    # Stampa i risultati per verifica
    print("\nSimilarity Matrix (top 3 matches per ogni voce della lista 1):")
    for val1, matches in top_matches.items():
        match_strings = [f"'{m['match']}' ({m['similarity']:.4f})" for m in matches]
        print(f"'{val1}' -> Top 3 matches: {', '.join(match_strings)}")


