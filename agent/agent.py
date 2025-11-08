# agent.py
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from google import genai


def get_api_key() -> str:
    """Get API key from environment variable"""
    api_key = os.getenv('GEMINI_API_KEY', 'AIzaSyC7hR3okrohJCmAU_mgx3KSIeU8S2POjt4')
    if not api_key:
        raise ValueError(
            "❌ GEMINI_API_KEY environment variable not set.\n"
            "Get your key from: https://aistudio.google.com/app/apikey\n"
            "Then run: export GEMINI_API_KEY='your-key-here'"
        )
    return api_key


def call_gemini_api(prompt: str, client: genai.Client) -> str:
    """Make request to Gemini API using the new SDK"""
    try:
        config = genai.types.GenerateContentConfig(
            temperature=0.1,
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config=config
        )

        return response.text

    except Exception as e:
        raise Exception(f"API request failed: {e}")


def parse_json_array(response_text: str) -> list[dict]:
    """Parse JSON array response from LLM"""
    try:
        cleaned_text = response_text.strip()

        # Remove markdown formatting
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        cleaned_text = cleaned_text.strip()

        # Find JSON array boundaries
        start_bracket = cleaned_text.find("[")
        if start_bracket == -1:
            raise ValueError("No opening bracket found - expected JSON array")

        bracket_count = 0
        last_valid_pos = -1

        for i in range(start_bracket, len(cleaned_text)):
            if cleaned_text[i] == '[':
                bracket_count += 1
            elif cleaned_text[i] == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    last_valid_pos = i + 1
                    break

        if last_valid_pos == -1:
            raise ValueError("No matching closing bracket found - JSON array appears truncated")

        json_text = cleaned_text[start_bracket:last_valid_pos]
        result = json.loads(json_text)

        if not isinstance(result, list):
            raise ValueError("Expected JSON array, got object instead")

        return result

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}")


def parse_llm_response_json(llm_response_text: str) -> dict[str, Any]:
    """
    Safely extracts and parses a JSON string embedded within a markdown code block
    (```json ... ```) from the LLM's response.

    Args:
        llm_response_text: The full string response from the LLM agent.

    Returns:
        A dictionary representing the parsed JSON object, or an empty dictionary
        if parsing fails.
    """

    # Use a regular expression to find the JSON content inside the markdown block
    json_match = re.search(r"```json\s*(.*?)\s*```", llm_response_text, re.DOTALL)

    if not json_match:
        print("Error: Could not find JSON content inside ```json ... ``` block.")
        return {}

    # Extract the raw JSON string
    raw_json_string = json_match.group(1)

    # Clean the string: remove common LLM artifacts like backticks or extra whitespace
    raw_json_string = raw_json_string.strip()

    try:
        # Parse the JSON string into a Python dictionary
        parsed_data = json.loads(raw_json_string)
        return parsed_data

    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON. Check for malformed data.")
        print(f"JSON Error: {e}")
        print(f"Problematic string: {raw_json_string}")
        return {}


@dataclass
class TransactionCategorization:
    """Structured result for a single transaction categorization"""
    transaction_id: str
    date: str
    category: str
    merchant: str
    amount: float
    original_amount: str
    description: str
    applied_user_rule: str | None = None
    failure: str | None = None
    raw_data: dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'TransactionCategorization':
        """Create instance from dictionary"""
        return cls(
            transaction_id=data.get("transaction_id", ""),
            date=data.get("date", ""),
            category=data.get("category", ""),
            merchant=data.get("merchant", ""),
            amount=data.get("amount", 0.0),
            original_amount=data.get("original_amount", ""),
            description=data.get("description", ""),
            applied_user_rule=data.get("applied_user_rule"),
            failure=data.get("failure"),
            raw_data=data
        )


@dataclass
class AgentTransactionUpload:
    transaction_id: int
    raw_text: dict[str, Any]


class ExpenseCategorizerAgent:
    """Agent for categorizing expense transactions using LLM"""

    def __init__(self, api_key: str | None = None, user_rules: list[str] | None = None,
                 available_categories: list[str] | None = None):
        """
        Args:
            api_key: Gemini API key (optional, will try env var)
            user_rules: list of strict user-defined categorization rules
            available_categories: list of available categories
        """
        self.api_key = api_key or get_api_key()
        self.client = genai.Client(api_key=self.api_key)
        self.available_categories = available_categories or []
        self.user_rules = user_rules or []

    def build_batch_prompt(self, batch: list[AgentTransactionUpload]) -> str:
        """Costruisce il prompt per un batch di transazioni"""

        # Formatta le transazioni
        transactions_text = ""
        for i, tx in enumerate(batch, 1):
            transactions_text += f"{i}. TRANSACTION_ID: {tx.transaction_id}\n"
            transactions_text += "   RAW DATA:\n"
            for column, value in tx.raw_text.items():
                if column != 'id':
                    # Tronca i valori molto lunghi
                    display_value = str(value)[:200] + "..." if len(str(value)) > 200 else value
                    transactions_text += f"   - {column}: {column}: {display_value}\n"
            transactions_text += "\n"

        # Costruisce la sezione delle regole utente
        user_rules_section = ""

        # ------------------- REGOLA CRITICA: IGNORARE I SALDI -------------------
        critical_rules = [
            "IGNORA transazioni la cui descrizione contiene 'Saldo iniziale' o 'Saldo finale'. Non devono essere categorizzate e non devono apparire nell'output JSON.",
            # NUOVA REGOLA CRITICA: IGNORA ANCHE LE ENTRATE/RICAVI
            "IGNORA transazioni che sono Accrediti (denaro IN) o con importo positivo. Non devono essere categorizzate e non devono apparire nell'output JSON. Il tuo compito è solo categorizzare le SPESE (USCITE).",
        ]

        # Aggiunge le regole utente dinamiche
        dynamic_user_rules = [f"{i}. {rule}" for i, rule in enumerate(self.user_rules, 1)]

        all_user_rules = critical_rules + dynamic_user_rules

        if all_user_rules:
            user_rules_section = """
    ═══════════════════════════════════════════════════════════════════
    ⚠️  REGOLE UTENTE - PRIORITÀ ASSOLUTA - DEVONO ESSERE APPLICATE  ⚠️
    ═══════════════════════════════════════════════════════════════════

    QUESTE REGOLE SONO OBBLIGATORIE E SOVRASCRIVONO OGNI ALTRA LOGICA.

    """
            # Formatta le regole critiche e le regole utente
            user_rules_section += "\n".join(all_user_rules)

            user_rules_section += """
    ⚠️ CRITICO: Se UNA QUALSIASI transazione corrisponde a una regola utente (incluse le regole IGNORA), DEVI applicarla.
    Le regole utente hanno PRIORITÀ ASSOLUTA su tutto il resto.

    """

        # Formatta le categorie disponibili con struttura chiara
        categories_formatted = "\n".join([f"  • {cat}" for cat in self.available_categories if cat != 'not_expense'])

        return f"""Sei un assistente IA specializzato nella categorizzazione delle **spese** bancarie italiane.

    {user_rules_section}

    ═══════════════════════════════════════════════════════
    ⚠️⚠️⚠️ REQUISITO CATEGORIA STRETTO ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════

    DEVI usare SOLO categorie da questa ESATTA lista qui sotto.
    DEVI ASSOLUTAMENTE trovare una corrispondenza con la categoria più probabile.
    NON creare nuove categorie.
    NON usare variazioni o nomi simili.
    **TUTTE le categorie devono essere in ITALIANO.**

    CATEGORIE CONSENTITE (SOLO NOMI ESATTI - IN ITALIANO):
    {categories_formatted}

    REGOLE DI CORRISPONDENZA CATEGORIA:
    • Usa il nome ESATTO della categoria come mostrato sopra
    
    ⚠️ CRITICO: **NON DEVI USARE "Uncategorized".** DEVI assegnare la categoria più probabile basandoti sulla descrizione.
    NON inventare MAI un nuovo nome di categoria non presente nella lista sopra.

    ═══════════════════════════════════════════════════════
    ISTRUZIONI PRINCIPALI (ORDINE DI PRIORITÀ):
    ═══════════════════════════════════════════════════════

    1. CHECK USER RULES FIRST - **APPLICA LA REGOLA "IGNORA" PER I SALDI E GLI ACCREDITI.**
    2. Analizza ogni transazione rimanente (che saranno solo SPESE).
    3. Categorizza ogni transazione SPESA usando SOLO le categorie consentite sopra, trovando sempre la corrispondenza più probabile.
    4. Estrai il nome del commerciante e tutti i campi obbligatori.

    ═══════════════════════════════════════════════════════
    ⚠️⚠️⚠️ CAMPI OBBLIGATORI - DEVONO ESSERE ESTRATTI PER OGNI TRANSAZIONE ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════

    DEVI estrarre questi 5 campi per OGNI transazione di SPESA, indipendentemente dal formato CSV o dai nomi delle colonne:

    ┌─────────────────────────────────────────────────────┐
    │ 1. DATE (DATA) (OBBLIGATORIO)                       │
    └─────────────────────────────────────────────────────┘

       DOVE TROVARLO:
       • Cerca in QUALSIASI campo contenente: "data", "date", "valuta", "contabile", "operazione"
       • Intestazioni Italiane comuni: "Data", "Data valuta", "Data contabile", "DATA VALUTA", "DATA CONTABILE"

       FORMATO: **MANTIENI IL FORMATO ORIGINALE ESATTO** così come appare nei dati
       
       ⚠️ CRITICO: NON convertire o riformattare la data. Preserva ESATTAMENTE il formato originale.
       • Se la data è "15/10/2025" → usa "15/10/2025"
       • Se la data è "2025-10-15" → usa "2025-10-15"
       • Se la data è "15/10/25" → usa "15/10/25"

       STRATEGIA DI ESTRAZIONE:
       • Se esistono più date, preferisci "Data valuta" rispetto a "Data contabile".
       • Il formato italiano è di solito GG/MM/AAAA - converti in YYYY-MM-DD

       FALLBACK: Se non viene trovata alcuna data, usa la data corrente.

    ┌─────────────────────────────────────────────────────┐
    │ 2. AMOUNT (IMPORTO) (OBBLIGATORIO)                  │
    └─────────────────────────────────────────────────────┘

       DOVE TROVARLO:
       • Cerca in QUALSIASI campo contenente: "importo", "amount", "movimento", "uscite", "entrate", "dare", "avere"

       FORMATO: Numero decimale positivo (es. 45.50)

       STRATEGIA DI ESTRAZIONE:
       • **AMOUNT FINALE ESTRATTO:** Il valore numerico nel campo "amount" del JSON DEVE SEMPRE essere POSITIVO (valore assoluto).
       • Il formato italiano usa la virgola per i decimali: "45,50" → converti in 45.50

       FALLBACK: Se non viene trovato alcun importo, usa 0.00.

    ┌──────────────────────────────────────────────────────┐
    │ 3. ORIGINAL_AMOUNT (IMPORTO ORIGINALE) (OBBLIGATORIO)│
    └──────────────────────────────────────────────────────┘

       La rappresentazione ESATTA della stringa così come appare nei dati, mantenendo il segno originale (che dovrebbe essere negativo o senza segno ma associato a USCITE).

       NON modificare o riformattare - preserva esattamente la stringa originale.

    ┌────────────────────────────────────────────────────────────┐
    │ 4. MERCHANT (COMMERCIANTE) (OBBLIGATORIO) - CAMPO CRITICO  │
    └────────────────────────────────────────────────────────────┘

       DOVE TROVARLO:
       • Cerca in TUTTI i campi: "Causale", "Descrizione", "Concetto", "Descrizione operazione", "Osservazioni", "Note" e simili.

       STRATEGIA DI ESTRAZIONE:
       • Per pagamenti con carta, estrai il nome del commerciante (es. "ESSELUNGA").
       • IMPORTANTE: Se nella descrizione ci sono Addebiti o SDD, estrai il nome dell' ordinante/creditore, evita assolutamente il debitore. 
       • Rimuovi: "S.p.A.", "SRL", "presso", numeri di carta, codici.

       VALORI DI FALLBACK:
       • Bonifico bancario senza beneficiario → "Bonifico"
       • Prelievo bancomat → "Prelievo"

    ┌─────────────────────────────────────────────────────┐
    │ 5. DESCRIPTION (DESCRIZIONE) (OBBLIGATORIO)         │
    └─────────────────────────────────────────────────────┘

       La descrizione è solitamente un campo contente una string che spiega la transazione.

       STRATEGIA:
       • Usare direttamente la stringa
       • NON aggiungere dettagli

       ⚠️ NON lasciare MAI la descrizione vuota.

    ═══════════════════════════════════════════════════════
    GESTIONE DEI FALLIMENTI
    ═══════════════════════════════════════════════════════

    Se la categorizzazione è *estremamente* incerta:
    • **NON USARE** "Uncategorized", "Unkwown" eccetera.
    • **USA IL CAMPO FAILURE** .
    Se il commerciante non è possibile da individuare:
    • **NON USARE** "Unkwown" o simili.
    • **USA IL CAMPO FAILURE** .
    
    IMPORTANTE: DEVI comunque estrarre date, amount, original_amount, e description.
    
    Il seguente è un esempio di fallimento:
    {{
        "transaction_id": "1201",
        "date": "2025-10-14",
        "category": "null",
        "merchant": "Negozio di Gianna",
        "amount": 12.50,
        "original_amount": "-12,50",
        "description": "Operazione Mastercard presso Negozio di Gianna"
        "failure": true
      }}

    ═══════════════════════════════════════════════════════
    OUTPUT FORMAT
    ═══════════════════════════════════════════════════════

    Restituisci SOLO un array JSON con oggetti di categorizzazione.
    **DEVI ESCLUDERE DALL'OUTPUT JSON LE TRANSAZIONI CHE CORRISPONDONO ALLA REGOLA "IGNORA SALDI E ACCREDITI".**
    NON includere oggetti wrapper o testo esplicativo.
    Restituisci l'array JSON direttamente.

    FORMATO (Le categorie devono essere in ITALIANO):
    [
      {{
        "transaction_id": "1200",
        "date": "2025-10-15",
        "category": "Alimentari",
        "merchant": "ESSELUNGA",
        "amount": 161.32,
        "original_amount": "-161,32",
        "description": "Addebito SDD CORE Esselunga S.p.A. ADDEB.FIDATY ORO",
        "applied_user_rule": null,
        "failure": False
      }},
      {{
        "transaction_id": "1201",
        "date": "2025-10-14",
        "category": "Ristoranti e Bar",
        "merchant": "FRAGESA",
        "amount": 46.50,
        "original_amount": "-46,50",
        "description": "Operazione Mastercard presso FRAGESA SRL"
      }}
    ]

    ═══════════════════════════════════════════════════════
    TRANSAZIONI DA ANALIZZARE:
    ═══════════════════════════════════════════════════════

    {transactions_text}

    ═══════════════════════════════════════════════════════
    CHECKLIST FINALE PRIMA DI RISPONDERE:
    ═══════════════════════════════════════════════════════

    ✓ Ho controllato prima le regole utente, **inclusa la regola IGNORA SALDI e ACCREDITI**?
    ✓ Ho **escluso Saldi e Accrediti** dal JSON finale?
    ✓ OGNI transazione restante (solo spese) ha i 5 campi obbligatori estratti?
    ✓ Ho ASSOLUTAMENTE EVITATO "Uncategorized"?
    ✓ La categoria è della lista ESATTA consentita (e in ITALIANO)?
    ✓ La mia risposta è SOLO l'array JSON (senza markdown, senza testo)?

    RISPONDI SOLO CON L'ARRAY JSON:"""

    def process_batch(self, batch: list[AgentTransactionUpload]) -> list[TransactionCategorization]:
        """
        Process a single batch through LLM and deserialize into structured objects.

        Args:
            batch: list of transactions with 'id' and raw data

        Returns:
            list[TransactionCategorization]: Array of categorization objects
        """
        try:
            print(f"👀 Analyzing batch with length {len(batch)}...")
            # Build prompt
            prompt = self.build_batch_prompt(batch)

            # Send to API using new SDK
            response_text = call_gemini_api(prompt, self.client)

            # Parse JSON array response
            categorizations_data = parse_json_array(response_text)

            # Deserialize into structured objects
            categorizations = [
                TransactionCategorization.from_dict(item)
                for item in categorizations_data
            ]

            # Log completion
            expense_count = len([c for c in categorizations if c.category != "not_expense"])
            print(f"✅ Analysis completed: {expense_count}/{len(batch)} expenses categorized! 🔥🔥")

            return categorizations

        except Exception as e:
            print(f"❌ Analysis failed: {str(e)}")
            return []
        """
        Sei un assistente IA specializzato nella categorizzazione delle **spese** bancarie italiane.

    
    ═══════════════════════════════════════════════════════════════════
    ⚠️  REGOLE UTENTE - PRIORITÀ ASSOLUTA - DEVONO ESSERE APPLICATE  ⚠️
    ═══════════════════════════════════════════════════════════════════

    QUESTE REGOLE SONO OBBLIGATORIE E SOVRASCRIVONO OGNI ALTRA LOGICA.

    IGNORA transazioni la cui descrizione contiene 'Saldo iniziale' o 'Saldo finale'. Non devono essere categorizzate e non devono apparire nell'output JSON.
IGNORA transazioni che sono Accrediti (denaro IN) o con importo positivo. Non devono essere categorizzate e non devono apparire nell'output JSON. Il tuo compito è solo categorizzare le SPESE (USCITE).
1. Tutte le operazioni che riguardano Paypal, o che compare in qualunque forma il Paypal, verranno categorizzate in Trasporti
2. Tutte le operazioni che riguardano Retitalia, o che compare in qualunque forma il Retitalia, verranno categorizzate in Carburante
3. Tutte le operazioni che riguardano Yada energia, o che compare in qualunque forma il Yada energia, verranno categorizzate in Bollette
4. Tutte le operazioni che riguardano Aida Pedretti, o che compare in qualunque forma il Aida Pedretti, verranno categorizzate in Affitto
    ⚠️ CRITICO: Se UNA QUALSIASI transazione corrisponde a una regola utente (incluse le regole IGNORA), DEVI applicarla.
    Le regole utente hanno PRIORITÀ ASSOLUTA su tutto il resto.

    

    ═══════════════════════════════════════════════════════
    ⚠️⚠️⚠️ REQUISITO CATEGORIA STRETTO ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════

    DEVI usare SOLO categorie da questa ESATTA lista qui sotto.
    DEVI ASSOLUTAMENTE trovare una corrispondenza con la categoria più probabile.
    NON creare nuove categorie.
    NON usare variazioni o nomi simili.
    **TUTTE le categorie devono essere in ITALIANO.**

    CATEGORIE CONSENTITE (SOLO NOMI ESATTI - IN ITALIANO):
      • Affitto
  • Bollette
  • Carburante
  • Trasporti

    REGOLE DI CORRISPONDENZA CATEGORIA:
    • Usa il nome ESATTO della categoria come mostrato sopra
    
    ⚠️ CRITICO: **NON DEVI USARE "Uncategorized".** DEVI assegnare la categoria più probabile basandoti sulla descrizione.
    NON inventare MAI un nuovo nome di categoria non presente nella lista sopra.

    ═══════════════════════════════════════════════════════
    ISTRUZIONI PRINCIPALI (ORDINE DI PRIORITÀ):
    ═══════════════════════════════════════════════════════

    1. CHECK USER RULES FIRST - **APPLICA LA REGOLA "IGNORA" PER I SALDI E GLI ACCREDITI.**
    2. Analizza ogni transazione rimanente (che saranno solo SPESE).
    3. Categorizza ogni transazione SPESA usando SOLO le categorie consentite sopra, trovando sempre la corrispondenza più probabile.
    4. Estrai il nome del commerciante e tutti i campi obbligatori.

    ═══════════════════════════════════════════════════════
    ⚠️⚠️⚠️ CAMPI OBBLIGATORI - DEVONO ESSERE ESTRATTI PER OGNI TRANSAZIONE ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════

    DEVI estrarre questi 5 campi per OGNI transazione di SPESA, indipendentemente dal formato CSV o dai nomi delle colonne:

    ┌─────────────────────────────────────────────────────┐
    │ 1. DATE (DATA) (OBBLIGATORIO)                       │
    └─────────────────────────────────────────────────────┘

       DOVE TROVARLO:
       • Cerca in QUALSIASI campo contenente: "data", "date", "valuta", "contabile", "operazione"
       • Intestazioni Italiane comuni: "Data", "Data valuta", "Data contabile", "DATA VALUTA", "DATA CONTABILE"

       FORMATO: **MANTIENI IL FORMATO ORIGINALE ESATTO** così come appare nei dati
       
       ⚠️ CRITICO: NON convertire o riformattare la data. Preserva ESATTAMENTE il formato originale.
       • Se la data è "15/10/2025" → usa "15/10/2025"
       • Se la data è "2025-10-15" → usa "2025-10-15"
       • Se la data è "15/10/25" → usa "15/10/25"

       STRATEGIA DI ESTRAZIONE:
       • Se esistono più date, preferisci "Data valuta" rispetto a "Data contabile".
       • Il formato italiano è di solito GG/MM/AAAA - converti in YYYY-MM-DD

       FALLBACK: Se non viene trovata alcuna data, usa la data corrente.

    ┌─────────────────────────────────────────────────────┐
    │ 2. AMOUNT (IMPORTO) (OBBLIGATORIO)                  │
    └─────────────────────────────────────────────────────┘

       DOVE TROVARLO:
       • Cerca in QUALSIASI campo contenente: "importo", "amount", "movimento", "uscite", "entrate", "dare", "avere"

       FORMATO: Numero decimale positivo (es. 45.50)

       STRATEGIA DI ESTRAZIONE:
       • **AMOUNT FINALE ESTRATTO:** Il valore numerico nel campo "amount" del JSON DEVE SEMPRE essere POSITIVO (valore assoluto).
       • Il formato italiano usa la virgola per i decimali: "45,50" → converti in 45.50

       FALLBACK: Se non viene trovato alcun importo, usa 0.00.

    ┌──────────────────────────────────────────────────────┐
    │ 3. ORIGINAL_AMOUNT (IMPORTO ORIGINALE) (OBBLIGATORIO)│
    └──────────────────────────────────────────────────────┘

       La rappresentazione ESATTA della stringa così come appare nei dati, mantenendo il segno originale (che dovrebbe essere negativo o senza segno ma associato a USCITE).

       NON modificare o riformattare - preserva esattamente la stringa originale.

    ┌────────────────────────────────────────────────────────────┐
    │ 4. MERCHANT (COMMERCIANTE) (OBBLIGATORIO) - CAMPO CRITICO  │
    └────────────────────────────────────────────────────────────┘

       DOVE TROVARLO:
       • Cerca in TUTTI i campi: "Causale", "Descrizione", "Concetto", "Descrizione operazione", "Osservazioni", "Note" e simili.

       STRATEGIA DI ESTRAZIONE:
       • Per pagamenti con carta, estrai il nome del commerciante (es. "ESSELUNGA").
       • IMPORTANTE: Se nella descrizione ci sono Addebiti o SDD, estrai il nome dell' ordinante/creditore, evita assolutamente il debitore. 
       • Rimuovi: "S.p.A.", "SRL", "presso", numeri di carta, codici.

       VALORI DI FALLBACK:
       • Bonifico bancario senza beneficiario → "Bonifico"
       • Prelievo bancomat → "Prelievo"

    ┌─────────────────────────────────────────────────────┐
    │ 5. DESCRIPTION (DESCRIZIONE) (OBBLIGATORIO)         │
    └─────────────────────────────────────────────────────┘

       La descrizione è solitamente un campo contente una string che spiega la transazione.

       STRATEGIA:
       • Usare direttamente la stringa
       • NON aggiungere dettagli

       ⚠️ NON lasciare MAI la descrizione vuota.

    ═══════════════════════════════════════════════════════
    GESTIONE DEI FALLIMENTI
    ═══════════════════════════════════════════════════════

    Se la categorizzazione è *estremamente* incerta:
    • **NON USARE** "Uncategorized", "Unkwown" eccetera.
    • **USA IL CAMPO FAILURE** .
    Se il commerciante non è possibile da individuare:
    • **NON USARE** "Unkwown" o simili.
    • **USA IL CAMPO FAILURE** .
    
    IMPORTANTE: DEVI comunque estrarre date, amount, original_amount, e description.
    
    Il seguente è un esempio di fallimento:
    {
        "transaction_id": "1201",
        "date": "2025-10-14",
        "category": "null",
        "merchant": "Negozio di Gianna",
        "amount": 12.50,
        "original_amount": "-12,50",
        "description": "Operazione Mastercard presso Negozio di Gianna"
        "failure": true
      }

    ═══════════════════════════════════════════════════════
    OUTPUT FORMAT
    ═══════════════════════════════════════════════════════

    Restituisci SOLO un array JSON con oggetti di categorizzazione.
    **DEVI ESCLUDERE DALL'OUTPUT JSON LE TRANSAZIONI CHE CORRISPONDONO ALLA REGOLA "IGNORA SALDI E ACCREDITI".**
    NON includere oggetti wrapper o testo esplicativo.
    Restituisci l'array JSON direttamente.

    FORMATO (Le categorie devono essere in ITALIANO):
    [
      {
        "transaction_id": "1200",
        "date": "2025-10-15",
        "category": "Alimentari",
        "merchant": "ESSELUNGA",
        "amount": 161.32,
        "original_amount": "-161,32",
        "description": "Addebito SDD CORE Esselunga S.p.A. ADDEB.FIDATY ORO",
        "applied_user_rule": null,
        "failure": False
      },
      {
        "transaction_id": "1201",
        "date": "2025-10-14",
        "category": "Ristoranti e Bar",
        "merchant": "FRAGESA",
        "amount": 46.50,
        "original_amount": "-46,50",
        "description": "Operazione Mastercard presso FRAGESA SRL"
      }
    ]

    ═══════════════════════════════════════════════════════
    TRANSAZIONI DA ANALIZZARE:
    ═══════════════════════════════════════════════════════

    1. TRANSACTION_ID: 1335
   RAW DATA:
   - USCITE: USCITE: 
   - CAUSALE: CAUSALE: 
   - ENTRATE: ENTRATE: -35,88
   - DATA VALUTA: DATA VALUTA: 
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Saldo finale

2. TRANSACTION_ID: 1334
   RAW DATA:
   - USCITE: USCITE: -145,74
   - CAUSALE: CAUSALE: Addebito Diretto
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 30/09/2025
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Addebito SDD CORE Scad. 30/09/2025 Imp. 145.74 Creditor id. IT16TAD0000080050050154 REGIONE LOMBARDIA Id Mandato 1000000000000000058423048 Debitore MUSICCO GIOVANNA Rif. 

3. TRANSACTION_ID: 1333
   RAW DATA:
   - USCITE: USCITE: -24,60
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 28/09/2025
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 28/09/2025 alle ore 19:06 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=24.6 / Importo in Euro=24.6 presso A21AP - AUTOVIA PADAN - Transazione C-less

4. TRANSACTION_ID: 1332
   RAW DATA:
   - USCITE: USCITE: -1,60
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 28/09/2025
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 28/09/2025 alle ore 16:59 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=1.6 / Importo in Euro=1.6 presso HERMES 2004ADS Campog - Transazione C-less

5. TRANSACTION_ID: 1331
   RAW DATA:
   - USCITE: USCITE: -4,00
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 28/09/2025
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 28/09/2025 alle ore 14:52 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=4 / Importo in Euro=4 presso CHIOSCO DELL'ANGOLO DI - Transazione C-less

6. TRANSACTION_ID: 1330
   RAW DATA:
   - USCITE: USCITE: -26,50
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 28/09/2025
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 28/09/2025 alle ore 14:22 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=26.5 / Importo in Euro=26.5 presso CHIOSCO DELL'ANGOLO DI - Transazione C-less

7. TRANSACTION_ID: 1329
   RAW DATA:
   - USCITE: USCITE: -18,50
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 27/09/2025
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 27/09/2025 alle ore 12:52 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=18.5 / Importo in Euro=18.5 presso CHIOSCO DELL'ANGOLO DI - Transazione C-less

8. TRANSACTION_ID: 1328
   RAW DATA:
   - USCITE: USCITE: -17,40
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 27/09/2025
   - DATA CONTABILE: DATA CONTABILE: 30/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 27/09/2025 alle ore 08:32 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=17.4 / Importo in Euro=17.4 presso LA RONDINE - SOCIETA' - Transazione C-less

9. TRANSACTION_ID: 1327
   RAW DATA:
   - USCITE: USCITE: -2,20
   - CAUSALE: CAUSALE: Addebito Diretto
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 29/09/2025
   - DATA CONTABILE: DATA CONTABILE: 29/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Addebito SDD CORE Scad. 29/09/2025 Imp. 2.2 Creditor id. LU96ZZZ0000000000000000058 PayPal Europe S.a.r.l. et Cie S.C.A Id Mandato 54V22258E3N8U Debitore Giacomo Zanotti Rif. 1045083168164/PAYPAL

10. TRANSACTION_ID: 1326
   RAW DATA:
   - USCITE: USCITE: -64,47
   - CAUSALE: CAUSALE: Addebito Diretto
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 29/09/2025
   - DATA CONTABILE: DATA CONTABILE: 29/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Addebito SDD CORE Scad. 29/09/2025 Imp. 64.47 Creditor id. LU96ZZZ0000000000000000058 PayPal Europe S.a.r.l. et Cie S.C.A Id Mandato 54V22258E3N8U Debitore Giacomo Zanotti Rif. 1045084628552/PAYPAL

11. TRANSACTION_ID: 1325
   RAW DATA:
   - USCITE: USCITE: 
   - CAUSALE: CAUSALE: Accredito Bonifico
   - ENTRATE: ENTRATE: +10,00
   - DATA VALUTA: DATA VALUTA: 29/09/2025
   - DATA CONTABILE: DATA CONTABILE: 29/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Bonifico N. 16940937202 BIC Ordinante INGBITD1XXX Data Ordine  Codifica Ordinante IT03E0347501605CC0012553485 Anagrafica Ordinante Gemma Musicco Note: Sacchetti asilo

12. TRANSACTION_ID: 1324
   RAW DATA:
   - USCITE: USCITE: -23,60
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 27/09/2025
   - DATA CONTABILE: DATA CONTABILE: 29/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 27/09/2025 alle ore 12:42 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=23.6 / Importo in Euro=23.6 presso ASPIT BRESCIA OVEST  - - Transazione C-less

13. TRANSACTION_ID: 1323
   RAW DATA:
   - USCITE: USCITE: -17,30
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 27/09/2025
   - DATA CONTABILE: DATA CONTABILE: 29/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 27/09/2025 alle ore 12:13 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=17.3 / Importo in Euro=17.3 presso STAZ.SERV. ESSO BEVANO - Transazione C-less

14. TRANSACTION_ID: 1322
   RAW DATA:
   - USCITE: USCITE: -7,42
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 26/09/2025
   - DATA CONTABILE: DATA CONTABILE: 28/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 26/09/2025 alle ore 10:50 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=7.42 / Importo in Euro=7.42 presso FARMACIA FORNACI SRL - Transazione C-less

15. TRANSACTION_ID: 1321
   RAW DATA:
   - USCITE: USCITE: -10,64
   - CAUSALE: CAUSALE: Pagamento Carta
   - ENTRATE: ENTRATE: 
   - DATA VALUTA: DATA VALUTA: 26/09/2025
   - DATA CONTABILE: DATA CONTABILE: 28/09/2025
   - DESCRIZIONE OPERAZIONE: DESCRIZIONE OPERAZIONE: Operazione Mastercard del 26/09/2025 alle ore 08:34 con Carta xxxxxxxxxxxx7329 Div=EUR Importo in divisa=10.64 / Importo in Euro=10.64 presso FERRARINI SAS IDEA VER



    ═══════════════════════════════════════════════════════
    CHECKLIST FINALE PRIMA DI RISPONDERE:
    ═══════════════════════════════════════════════════════

    ✓ Ho controllato prima le regole utente, **inclusa la regola IGNORA SALDI e ACCREDITI**?
    ✓ Ho **escluso Saldi e Accrediti** dal JSON finale?
    ✓ OGNI transazione restante (solo spese) ha i 5 campi obbligatori estratti?
    ✓ Ho ASSOLUTAMENTE EVITATO "Uncategorized"?
    ✓ La categoria è della lista ESATTA consentita (e in ITALIANO)?
    ✓ La mia risposta è SOLO l'array JSON (senza markdown, senza testo)?

    RISPONDI SOLO CON L'ARRAY JSON:
        """