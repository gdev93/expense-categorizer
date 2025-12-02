
# agent.py
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any
from google import genai

from api.models import CsvUpload, Category

# Configure logger
logger = logging.getLogger(__name__)


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


def call_gemini_api(prompt: str, client: genai.Client, temperature: float = 0.1) -> str:
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
        logger.error("Could not find JSON content inside ```json ... ``` block.")
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
        logger.error(f"Failed to decode JSON. Check for malformed data. JSON Error: {e}")
        logger.debug(f"Problematic string: {raw_json_string}")
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
                 available_categories: list[Category] | None = None):
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
        """

        # Sample first few transactions
        sample_size = min(5, len(transactions))
        sample_transactions = transactions[:sample_size]

        # Build the prompt
        samples_text = ""
        for i, tx in enumerate(sample_transactions, 1):
            samples_text += f"Transazione {i}:\n"
            samples_text += f"  ID: {tx.transaction_id}\n"
            samples_text += "  Campi:\n"
            for column, value in tx.raw_text.items():
                # Truncate long values for token efficiency
                display_value = str(value)[:100] + "..." if len(str(value)) > 100 else value
                samples_text += f"    - {column}: {display_value}\n"
            samples_text += "\n"

        prompt = f"""Sei un esperto nell'analisi di strutture CSV di transazioni bancarie italiane.

Analizza i seguenti campioni di transazioni e identifica quali campi corrispondono a:
1. **description_field**: Il campo contenente la descrizione/dettagli della transazione
2. **merchant_field**: Il campo contenente il nome del commerciante/beneficiario
3. **transaction_date_field**: Il campo contenente la data della transazione
4. **amount_field**: Il campo contenente l'importo della transazione
5. **operation_type_field**: Il campo contenente il tipo di operazione

CAMPIONI DI TRANSAZIONI:
{samples_text}

ISTRUZIONI GENERALI:
- Restituisci SOLO i nomi dei campi esattamente come appaiono nei dati
- Se un campo non può essere determinato con sicurezza, restituisci null
- Fornisci un livello di confidenza: "high", "medium", o "low"

⚠️ ISTRUZIONI CRITICHE PER LA DATA TRANSAZIONE:
- Il campo transaction_date_field DEVE essere una colonna dedicata ESCLUSIVAMENTE alle date (es. "Data", "Data Valuta", "Data Contabile").
- **CRITERIO DI ESCLUSIONE:** Ignora qualsiasi colonna che contenga testo narrativo insieme alla data. Cerca formati puri (GG/MM/AAAA, AAAA-MM-GG, ecc.).
- **CRITERIO "DATA MAGGIORE":** Se nel CSV sono presenti più colonne valide di date (es. sia "Data Operazione" che "Data Valuta"):
  1. Confronta i valori delle date nei campioni forniti.
  2. Seleziona la colonna che contiene sistematicamente la data cronologicamente PIÙ RECENTE (la data maggiore).
  3. NON basare la scelta sul nome della colonna (es. non preferire a priori "Data Contabile"), ma basa la scelta sui valori effettivi.

⚠️ ISTRUZIONI CRITICHE PER L'IMPORTO:
- Il campo amount_field DEVE permettere di identificare le SPESE.
- Cerca colonne con importi negativi o indicatori di addebito.
- Se esistono colonne separate (es. "Dare"/"Avere"), scegli la colonna degli addebiti ("Dare", "Uscite").
- Se c'è una colonna unica ("Importo"), selezionala.

FORMATO OUTPUT (JSON):
{{
  "description_field": "nome_colonna_esatto_o_null",
  "merchant_field": "nome_colonna_esatto_o_null",
  "transaction_date_field": "nome_colonna_esatto_o_null",
  "amount_field": "nome_colonna_esatto_o_null",
  "operation_type_field": "nome_colonna_esatto_o_null",
  "confidence": "high|medium|low",
  "notes": "string"
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
            logger.error(f"CSV structure detection failed: {e}")
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

    def build_batch_prompt(self, batch: list[AgentTransactionUpload], csv_upload: CsvUpload) -> str:
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
        critical_rules = [
            "IGNORA transazioni la cui descrizione contiene 'Saldo'. Non devono essere categorizzate e non devono apparire nell'output JSON.",
            "IGNORA transazioni che sono Accrediti (denaro IN) o con importo positivo. Non devono essere categorizzate e non devono apparire nell'output JSON. Il tuo compito è solo categorizzare le SPESE (USCITE).",
        ]
        dynamic_user_rules = [f"{i}. {rule}" for i, rule in enumerate(self.user_rules, 1)]
        all_user_rules = critical_rules + dynamic_user_rules

        if all_user_rules:
            user_rules_section = """
═══════════════════════════════════════════════════════════════════
⚠️  REGOLE UTENTE - PRIORITÀ ASSOLUTA - DEVONO ESSERE APPLICATE  ⚠️
═══════════════════════════════════════════════════════════════════
QUESTE REGOLE SONO OBBLIGATORIE E SOVRASCRIVONO OGNI ALTRA LOGICA.
"""
            user_rules_section += "\n".join(all_user_rules)
            user_rules_section += """
⚠️ CRITICO: Se UNA QUALSIASI transazione corrisponde a una regola utente (incluse le regole IGNORA), DEVI applicarla.
Le regole utente hanno PRIORITÀ ASSOLUTA su tutto il resto.
"""

        # ---------------------------------------------------------------------
        # FIX APPLIED HERE: Format categories as "KEY": Description
        # This clearly separates the output value from the helper text
        # ---------------------------------------------------------------------
        categories_formatted_list = []
        for cat in self.available_categories:
            if cat.name != 'not_expense':
                if cat.description:
                    # Enclose the NAME in quotes so the LLM knows it's a discrete token
                    categories_formatted_list.append(f'  • "{cat.name}": {cat.description}')
                else:
                    categories_formatted_list.append(f'  • "{cat.name}"')

        categories_formatted = "\n".join(categories_formatted_list)

        return f"""Sei un assistente IA specializzato nella categorizzazione delle **spese** bancarie italiane.

{csv_hints_section}

{user_rules_section}

═══════════════════════════════════════════════════════
⚠️⚠️⚠️ REQUISITO TRANSACTION_ID OBBLIGATORIO ⚠️⚠️⚠️
═══════════════════════════════════════════════════════

**REQUISITO CRITICO ASSOLUTO:**
• OGNI oggetto JSON nell'output DEVE contenere il campo "transaction_id"
• Il valore di "transaction_id" DEVE essere ESATTAMENTE IDENTICO al TRANSACTION_ID fornito nei dati di input.

═══════════════════════════════════════════════════════
⚠️⚠️⚠️ REQUISITO CATEGORIA STRETTO (STRICT ENUM) ⚠️⚠️⚠️
═══════════════════════════════════════════════════════

DEVI scegliere la categoria da questa lista.

LISTA CATEGORIE VALIDE:
{categories_formatted}

⚠️⚠️⚠️ ISTRUZIONI DI FORMATTAZIONE CATEGORIA ⚠️⚠️⚠️
1. L'output per il campo "category" DEVE essere SOLO la stringa tra le virgolette.
2. NON includere la descrizione che segue i due punti.
3. NON includere trattini o testo esplicativo.

Esempio Corretto:
Input lista: "Trasporti": biglietti bus, treni
Output JSON: "category": "Trasporti"

Esempio SBAGLIATO (NON FARE QUESTO):
Input lista: "Trasporti": biglietti bus, treni
Output JSON: "category": "Trasporti - biglietti bus, treni"  <-- ERRORE GRAVE

⚠️ CRITICO: **NON DEVI USARE "Uncategorized".** DEVI assegnare la categoria più probabile.

═══════════════════════════════════════════════════════
ISTRUZIONI PRINCIPALI (ORDINE DI PRIORITÀ):
═══════════════════════════════════════════════════════

1. CHECK USER RULES FIRST - APPLICA LA REGOLA "IGNORA" PER I SALDI E GLI ACCREDITI.
2. Analizza ogni transazione rimanente (che saranno solo SPESE).
3. Categorizza ogni transazione SPESA usando SOLO le categorie consentite sopra.
4. Estrai il nome del commerciante e tutti i campi obbligatori.

═══════════════════════════════════════════════════════
⚠️⚠️⚠️ CAMPI OBBLIGATORI - DEVONO ESSERE ESTRATTI PER OGNI TRANSAZIONE ⚠️⚠️⚠️
═══════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────┐
│ 0. TRANSACTION_ID (OBBLIGATORIO - MASSIMA PRIORITÀ) │
└─────────────────────────────────────────────────────┘
   • Copia ESATTAMENTE il valore così come appare nell'input.

┌─────────────────────────────────────────────────────┐
│ 1. DATE (DATA) (OBBLIGATORIO)                       │
└─────────────────────────────────────────────────────┘
   • Formato YYYY-MM-DD preferito, o originale.

┌─────────────────────────────────────────────────────┐
│ 2. AMOUNT (IMPORTO) (OBBLIGATORIO)                  │
└─────────────────────────────────────────────────────┘
   • Numero decimale positivo (valore assoluto).

┌──────────────────────────────────────────────────────┐
│ 3. ORIGINAL_AMOUNT (IMPORTO ORIGINALE) (OBBLIGATORIO)│
└──────────────────────────────────────────────────────┘
   • Stringa esatta dai dati originali.

┌────────────────────────────────────────────────────────────┐
│ 4. MERCHANT (COMMERCIANTE) (OBBLIGATORIO) - CAMPO CRITICO  │
└────────────────────────────────────────────────────────────┘
   • Pulisci il nome (rimuovi SPA, SRL).
   • Se addebito SDD, trova il creditore.

┌─────────────────────────────────────────────────────┐
│ 5. DESCRIPTION (DESCRIZIONE) (OBBLIGATORIO)         │
└─────────────────────────────────────────────────────┘
   • Stringa originale della descrizione.

═══════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════

Restituisci SOLO un array JSON.

FORMATO ESEMPIO:
[
  {{
    "transaction_id": "1200",
    "date": "2025-10-15",
    "category": "Alimentari",
    "merchant": "ESSELUNGA",
    "amount": 161.32,
    "original_amount": "-161,32",
    "description": "Addebito SDD CORE Esselunga S.p.A.",
    "applied_user_rule": null,
    "failure": False
  }}
]

TRANSAZIONI DA ANALIZZARE:
{transactions_text}

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
            logger.info(f"Analyzing batch with {len(batch)} transactions...")
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
            logger.info(f"Analysis completed: {expense_count}/{len(batch)} expenses categorized")

            return categorizations

        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            return []