# agent.py
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from google import genai

from api.models import CsvUpload


def get_api_key() -> str:
    """Get API key from environment variable"""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError(
            "❌ GEMINI_API_KEY environment variable not set.\n"
            "Get your key from: https://aistudio.google.com/app/apikey\n"
            "Then run: export GEMINI_API_KEY='your-key-here'"
        )
    return api_key


def call_gemini_api(prompt: str, client: genai.Client, temperature:float=0.1) -> str:
    """Make request to Gemini API using the new SDK"""
    try:
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
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


@dataclass
class CsvStructure:
    """Structured CSV structure detection result"""
    description_field: str | None
    merchant_field: str | None
    transaction_date_field: str | None
    amount_field: str | None
    operation_type_field: str | None
    confidence: str  # "high", "medium", "low"
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> 'CsvStructure':
        """Create instance from dictionary"""
        return cls(
            description_field=data.get("description_field"),
            merchant_field=data.get("merchant_field"),
            transaction_date_field=data.get("transaction_date_field"),
            amount_field=data.get("amount_field"),
            operation_type_field=data.get("operation_type_field"),
            confidence=data.get("confidence", "low"),
            notes=data.get("notes")
        )


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

    def detect_csv_structure(
            self,
            transactions: list[AgentTransactionUpload]
    ) -> CsvStructure:
        """
        Analyze the CSV structure using Gemini to identify column mappings.

        Args:
            transactions: List of AgentTransactionUpload objects to analyze
            client: Gemini API client

        Returns:
            CsvStructure: Detected field mappings for description, merchant, date, amount, and operation type
        """

        # Sample first few transactions to reduce token usage
        sample_size = min(5, len(transactions))
        sample_transactions = transactions[:sample_size]

        # Build the prompt
        samples_text = ""
        for i, tx in enumerate(sample_transactions, 1):
            samples_text += f"Transazione {i}:\n"
            samples_text += f"  ID: {tx.transaction_id}\n"
            samples_text += "  Campi:\n"
            for column, value in tx.raw_text.items():
                display_value = str(value)[:100] + "..." if len(str(value)) > 100 else value
                samples_text += f"    - {column}: {display_value}\n"
            samples_text += "\n"

        prompt = f"""Sei un esperto nell'analisi di strutture CSV di transazioni bancarie italiane.

    Analizza i seguenti campioni di transazioni e identifica quali campi corrispondono a:
    1. **description_field**: Il campo contenente la descrizione/dettagli della transazione
    2. **merchant_field**: Il campo contenente il nome del commerciante/beneficiario
    3. **transaction_date_field**: Il campo contenente la data della transazione
    4. **amount_field**: Il campo contenente l'importo della transazione
    5. **operation_type_field**: Il campo contenente il tipo di operazione (es. "Pagamento", "Bonifico", "Prelievo", "Addebito", "Accredito", ecc.)

    CAMPIONI DI TRANSAZIONI:
    {samples_text}

    ISTRUZIONI GENERALI:
    - Restituisci SOLO i nomi dei campi esattamente come appaiono nei dati (nomi esatti delle colonne)
    - Se un campo non può essere determinato con sicurezza, restituisci null
    - Il campo operation_type_field contiene tipicamente parole chiave come: "Pagamento", "Bonifico", "Prelievo", "Addebito", "SDD", "Accredito", o descrittori di operazioni simili
    - Fornisci un livello di confidenza: "high", "medium", o "low"
    - Aggiungi note se ci sono ambiguità o osservazioni importanti

    ⚠️ ISTRUZIONI CRITICHE PER LA DATA TRANSAZIONE:
    - Il campo transaction_date_field DEVE essere una colonna dedicata alle date (es. "Data", "Data Valuta", "Data Contabile", "Data Operazione")
    - NON selezionare campi che contengono date all'interno di descrizioni testuali o campi narrativi
    - Cerca colonne con SOLO valori di date (formati come: GG/MM/AAAA, AAAA-MM-GG, GG/MM/AA)
    - IGNORA date che appaiono come parte di stringhe di testo più lunghe o descrizioni
    - Se esistono più colonne di date (es. "Data Operazione", "Data Valuta", "Data Contabile"), preferisci "Data Valuta" o la data più specifica della transazione
    - Esempio: Scegli la colonna "Data Valuta", NON un campo "Descrizione" che menziona casualmente una data

    ⚠️ ISTRUZIONI CRITICHE PER L'IMPORTO:
    - Il campo amount_field DEVE contenere SOLO importi NEGATIVI o importi contrassegnati come spese/addebiti
    - IGNORA colonne con importi positivi (accrediti/entrate)
    - Cerca colonne con segni negativi (es. "-45,50", "-100,00") o chiari indicatori di addebito
    - L'obiettivo è identificare SOLO LE SPESE, non le entrate
    - Se gli importi sono in più colonne (es. "Dare" per addebiti, "Avere" per accrediti), scegli la colonna degli addebiti
    - Nomi comuni di colonne italiane per addebiti: "Importo", "Dare", "Uscite", "Addebito", "Movimenti" (se negativi)
    - Se c'è una singola colonna "Importo" o "Movimenti" con valori sia positivi che negativi, selezionala comunque (verranno filtrati i valori negativi successivamente)

    FORMATO OUTPUT (solo JSON, niente markdown):
    {{
      "description_field": "nome_colonna_esatto_o_null",
      "merchant_field": "nome_colonna_esatto_o_null",
      "transaction_date_field": "nome_colonna_esatto_o_null",
      "amount_field": "nome_colonna_esatto_o_null",
      "operation_type_field": "nome_colonna_esatto_o_null",
      "confidence": "high|medium|low",
      "notes": "eventuali osservazioni rilevanti o null"
    }}

    Restituisci SOLO l'oggetto JSON, nient'altro."""

        try:

            response = call_gemini_api(prompt=prompt, client=self.client, temperature=1.0)

            # Parse the response
            result_dict = parse_llm_response_json(response)

            if not result_dict:
                # Fallback: try direct JSON parsing
                import json
                result_dict = json.loads(response.strip())

            return CsvStructure.from_dict(result_dict)

        except Exception as e:
            print(f"❌ Rilevamento struttura CSV fallito: {e}")
            # Return empty structure on failure
            return CsvStructure(
                description_field=None,
                merchant_field=None,
                transaction_date_field=None,
                amount_field=None,
                operation_type_field=None,
                confidence="low",
                notes=f"Rilevamento fallito: {str(e)}"
            )

    def build_batch_prompt(self, batch: list[AgentTransactionUpload], csv_upload:CsvUpload) -> str:
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

            # Build CSV structure hints section
        csv_hints_section = ""
        if csv_upload:
            csv_hints_section = """
    ═══════════════════════════════════════════════════════════════════
    📋 INFORMAZIONI STRUTTURA CSV - SUGGERIMENTI PER L'ESTRAZIONE 📋
    ═══════════════════════════════════════════════════════════════════

    Per aiutarti nell'estrazione dei dati, ecco le informazioni sulla struttura CSV identificata:

    """

            if csv_upload.description_column_name:
                csv_hints_section += f"📝 **DESCRIPTION FIELD**: Il campo '{csv_upload.description_column_name}' contiene la descrizione della transazione.\n"

            if csv_upload.merchant_column_name:
                csv_hints_section += f"🏪 **MERCHANT FIELD**: Il campo '{csv_upload.merchant_column_name}' contiene informazioni sul commerciante/beneficiario.\n"

            if csv_upload.date_column_name:
                csv_hints_section += f"📅 **DATE FIELD**: Il campo '{csv_upload.date_column_name}' contiene la data della transazione.\n"

            if csv_upload.amount_column_name:
                csv_hints_section += f"💰 **AMOUNT FIELD**: Il campo '{csv_upload.amount_column_name}' contiene l'importo della transazione.\n"

            if csv_upload.operation_type_column_name:
                csv_hints_section += f"🔄 **OPERATION TYPE FIELD**: Il campo '{csv_upload.operation_type_column_name}' contiene il tipo di operazione.\n"

            if csv_upload.notes:
                csv_hints_section += f"\n📌 **NOTE SULLA STRUTTURA CSV**:\n{csv_upload.notes}\n"

            csv_hints_section += """
    ⚠️ IMPORTANTE: Usa questi suggerimenti come guida principale per identificare e estrarre i campi corretti.
    Questi mapping sono stati identificati automaticamente analizzando la struttura del CSV.

    """

        # Costruisce la sezione delle regole utente
        user_rules_section = ""

        # ------------------- REGOLA CRITICA: IGNORARE I SALDI -------------------
        critical_rules = [
            "IGNORA transazioni la cui descrizione contiene 'Saldo'. Non devono essere categorizzate e non devono apparire nell'output JSON.",
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
    
    {csv_hints_section}
    
    {user_rules_section}

    ═══════════════════════════════════════════════════════
    ⚠️⚠️⚠️ REQUISITO TRANSACTION_ID OBBLIGATORIO ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════

    **REQUISITO CRITICO ASSOLUTO:**
    • OGNI oggetto JSON nell'output DEVE contenere il campo "transaction_id"
    • Il valore di "transaction_id" DEVE essere ESATTAMENTE IDENTICO al TRANSACTION_ID fornito nei dati di input
    • NON modificare, NON riformattare, NON cambiare il transaction_id in alcun modo
    • Se il TRANSACTION_ID di input è "1200", l'output DEVE avere "transaction_id": "1200"
    • Se il TRANSACTION_ID di input è "TX_12345", l'output DEVE avere "transaction_id": "TX_12345"

    ⚠️ CRITICO: Il transaction_id è l'UNICO modo per collegare i risultati alle transazioni originali.
    Se questo campo è mancante o errato, l'intera analisi è INUTILIZZABILE.

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

    DEVI estrarre questi campi per OGNI transazione di SPESA, indipendentemente dal formato CSV o dai nomi delle colonne:

    ┌─────────────────────────────────────────────────────┐
    │ 0. TRANSACTION_ID (OBBLIGATORIO - MASSIMA PRIORITÀ) │
    └─────────────────────────────────────────────────────┘

       **QUESTO È IL CAMPO PIÙ IMPORTANTE DI TUTTI.**

       DOVE TROVARLO:
       • È fornito all'inizio di ogni transazione nel formato "TRANSACTION_ID: <valore>"
       • È la PRIMA informazione di ogni transazione nei dati di input

       FORMATO: Copia ESATTAMENTE il valore così come appare

       ⚠️ CRITICO: 
       • NON modificare il transaction_id
       • NON convertirlo in numero
       • NON aggiungere o rimuovere caratteri
       • Preserva ESATTAMENTE il formato originale (stringa o numero)

       ESEMPIO:
       • Input: "TRANSACTION_ID: 1200" → Output: "transaction_id": "1200"
       • Input: "TRANSACTION_ID: TX_ABC_123" → Output: "transaction_id": "TX_ABC_123"

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

    ✓ OGNI oggetto JSON ha il campo "transaction_id" con il valore ESATTO dell'input?
    ✓ Ho controllato prima le regole utente, **inclusa la regola IGNORA SALDI e ACCREDITI**?
    ✓ Ho **escluso Saldi e Accrediti** dal JSON finale?
    ✓ OGNI transazione restante (solo spese) ha i 5 campi obbligatori estratti?
    ✓ Ho ASSOLUTAMENTE EVITATO "Uncategorized"?
    ✓ La categoria è della lista ESATTA consentita (e in ITALIANO)?
    ✓ La mia risposta è SOLO l'array JSON (senza markdown, senza testo)?

    RISPONDI SOLO CON L'ARRAY JSON:"""

    def process_batch(self, batch: list[AgentTransactionUpload], csv_upload: CsvUpload) -> list[
        TransactionCategorization]:
        """
        Process a single batch through LLM and deserialize into structured objects.

        Args:
            batch: list of transactions with 'id' and raw data
            csv_upload: CsvUpload instance with column mappings and notes

        Returns:
            list[TransactionCategorization]: Array of categorization objects
        """
        try:
            print(f"👀 Analyzing batch with length {len(batch)}...")
            # Build prompt with CSV column hints
            prompt = self.build_batch_prompt(batch, csv_upload)

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