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
    desc1 = "Operazione Mastercard del 01/03/2026 alle ore 10:52 con Carta xxxxxxxxxxxx3352 Div=EUR Importo in divisa=62 / Importo in Euro=62 presso ACTION GYM SSD SRL - Transazione C-less"
    desc2 = "Operazione Mastercard del 16/06/2025 alle ore 19:09 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=28.9 / Importo in Euro=28.9 presso ARTICIOK SRLS - Transazione C-less"

    # Generazione embedding
    emb1 = generate_embedding(desc1)
    emb2 = generate_embedding(desc2)
    from_db = [0.024521396,0.02608467,-0.068820804,-0.080346055,0.07683423,-0.0106682265,0.021228444,-0.0042578927,0.00044131355,-0.0061646616,-0.025406573,-0.009256821,-0.000585577,-0.08626875,-0.034097724,-0.10632068,-0.002807569,-0.030206656,0.005824496,-0.012016519,-0.051247668,-0.027747683,-0.03097605,0.05369047,-0.031458974,0.076682314,0.05467021,-0.011038294,0.0065255896,-0.033256806,0.10073846,0.014145508,0.03475442,-0.0024109948,0.013982326,0.12307226,-0.0031083804,-0.04259061,0.046056762,-0.04488423,0.022158146,-0.034080647,0.026278518,0.059191663,0.05982098,0.06138256,-0.017459694,0.021950763,-0.006170024,0.02532949,0.042135995,0.0042168666,-0.057766154,0.035161663,0.02526578,0.03402193,0.0073713064,0.048552405,0.012464131,0.05766674,0.0035289624,-0.025232181,-0.05517588,0.018428039,-0.03945961,0.067999,-0.0069004553,-0.0028322632,-0.06284017,0.035083357,-0.030658336,-0.07235332,-0.08556318,-0.036783613,0.032634996,0.049412645,-0.048944693,0.018478082,-0.031180281,0.07414887,0.012596962,0.053041577,-0.041580908,-0.011859956,-0.07554425,0.016702365,0.07158302,-0.0015723341,0.015010182,-0.07957835,0.048290573,-0.06538201,-0.012981697,-0.020654973,0.02373939,0.017916735,-0.01994388,0.06205187,0.065910794,0.10902411,0.06089926,0.08639802,-0.017998913,0.03666064,-0.14839172,0.08660354,0.052232128,0.027858023,-0.0006125334,0.02646135,-0.03800654,0.03803814,-0.012249056,-0.036710095,-0.02736572,0.03838583,-0.029032005,-0.035086762,0.096952826,0.054701034,-0.002920268,0.06237424,-0.018789446,0.06294488,-0.047183927,-0.06625382,0.101774655,0.029085217,-0.10740866,0.04649537,0.053550936,-0.05816993,-0.09675847,0.023803044,-0.06874101,-0.033018894,-0.0033933418,-0.006496329,0.03382371,-0.0076429853,-0.013107845,-0.0015080431,-0.078855306,-0.043343153,0.051224723,0.02085131,-0.07063304,0.047462516,0.094079815,-0.05052504,0.05972819,0.03311032,0.09123882,0.02936429,-0.028190697,0.030592596,0.115620166,-0.019940533,-0.032988593,-0.02036776,-0.029298468,0.005039712,-0.056989294,0.04756161,0.014692317,0.019513207,-0.018494653,0.014447017,0.0034404318,0.06472024,-0.03914137,0.02149529,-0.004866657,0.050300166,-0.05095042,-0.0777892,0.031307906,-0.002964326,-0.060856313,-0.08235874,-0.04995188,0.0047667027,0.05462446,-0.008978769,-0.08678791,0.049275696,0.006305894,-0.08633513,-0.014098585,0.0471448,0.026409745,0.034268312,0.04195451,0.00013736729,-0.02866141,-0.074635886,-0.047332104,-0.023964746,-0.018035032,0.049290206,-0.040104404,0.08949078,0.0080503635,0.01469772,0.044219058,0.023968048,0.059582464,-0.044866435,-0.08126171,-0.0059452076,0.067474164,-0.06271307,0.03315366,0.045261215,-0.07643825,0.06763698,0.012775674,0.0058995085,-0.015475853,-0.06258033,-0.08520368,0.017902993,-0.012613007,-0.040160656,0.044326194,-0.057911653,-0.016070757,-0.03711261,0.0017154122,0.103830636,0.0013323732,-0.011515184,0.06408943,0.071960166,0.020516774,-0.05268591,0.044687435,0.027619002,0.039275475,-0.010048602,0.07125512,0.057165213,-0.04628098,0.003836573,-0.015037444,0.08359166,-0.03497781,0.029542347,-0.066378325,-0.0816961,0.01049085,-0.06362753,-0.015104739,0.038750045,0.03485189,0.03122232,-0.009417867,0.08073212,-0.10627955,0.015084996,-0.034146804,0.07277189,0.0074885134,0.05081408,-0.032130994,-0.018669015,-0.045595825,-0.012009475,-0.026883172,-0.04929367,-0.01101929,-0.04277495,0.08134426,-0.020889003,0.061060913,0.04779651,0.057567433,-0.010451968,-0.11077024,0.08895897,0.008076481,-0.007459909,0.035552338,-0.04161964,-0.009804532,0.0069020106,0.006958152,-0.10998687,-0.006535505,-0.0033750634,-0.050118994,0.07473206,0.0456459,0.032074295,0.02793961,0.06899281,-0.045285232,-0.03606521,-0.01459398,0.03990691,-0.05454513,0.020298583,-8.723815e-05,-0.00338984,0.03377989,0.06332049,0.025595991,0.03768493,0.08219261,-0.06867687,-0.05653642,-0.143929,-0.022713672,-0.05272682,0.004667382,0.017390218,-0.0058267587,0.030834883,-0.078715436,-0.051453095,-0.030503351,-0.024742842,-0.02308065,0.05747019,-0.04269682,-0.04381454,-0.037874375,-0.024833405,-0.011782191,0.049258076,0.021321593,0.029177397,-0.0065214606,-0.034887362,-0.032422606,0.014722181,-0.050968874,-0.018184615,0.04641178,-0.020165741,0.011725824,0.008955149,0.039098896,-0.06724222,0.014257487,0.020804161,0.073045544,0.14452362,0.007284156,-0.0013807148,0.039379805,-0.26578063,0.13453263,0.03601571,0.05771053,-0.04471048,0.03389147,0.07055031,-0.005474852,0.011566827,0.0043311897,0.030989315,-0.021252735,-0.034217924,0.012537658,0.024547182,-0.08417855,0.048643153,0.0207836,0.04989613,-0.039221015,0.03237212,0.026797485,0.03158241,0.012426486,0.014627369,0.011551315,-0.06836715,0.05191934,0.036388926,-0.014529415,-0.08783297,0.042803973,-0.036848933]
    # Calcolo similarità
    sim_1_2 = cosine_similarity(from_db,emb1)

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


