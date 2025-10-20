# agent.py
import os
import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests


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


def call_gemini_api(prompt: str, api_key: str) -> dict:
    """Make request to Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    headers = {"Content-Type": "application/json"}

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4000
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API request failed: {e}")


def parse_gemini_response(response: dict) -> str:
    """Extract text content from Gemini response"""
    try:
        return response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Invalid response structure: {e}")


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


def parse_json_categorization(response_text: str) -> dict:
    """Parse JSON response from LLM categorization"""
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

        # Find JSON boundaries
        start_brace = cleaned_text.find("{")
        if start_brace == -1:
            raise ValueError("No opening brace found")

        brace_count = 0
        last_valid_pos = -1

        for i in range(start_brace, len(cleaned_text)):
            if cleaned_text[i] == '{':
                brace_count += 1
            elif cleaned_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    last_valid_pos = i + 1
                    break

        if last_valid_pos == -1:
            raise ValueError("No matching closing brace found - JSON appears truncated")

        json_text = cleaned_text[start_brace:last_valid_pos]
        result = json.loads(json_text)

        if "categorizations" not in result:
            raise ValueError("Missing 'categorizations' field in response")

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

    # 1. Use a regular expression to find the JSON content inside the markdown block.
    # The pattern looks for ```json followed by any characters (non-greedy, including newlines)
    # and ends at ```. The content is captured in group 1.
    json_match = re.search(r"```json\s*(.*?)\s*```", llm_response_text, re.DOTALL)

    if not json_match:
        print("Error: Could not find JSON content inside ```json ... ``` block.")
        return {}

    # Extract the raw JSON string
    raw_json_string = json_match.group(1)

    # 2. Clean the string: remove common LLM artifacts like backticks or extra whitespace
    raw_json_string = raw_json_string.strip()

    # 3. Handle a common issue where LLMs might use non-standard quotes or formatting
    # Although your example uses standard formatting, this is good practice for LLM output.
    try:
        # 4. Parse the JSON string into a Python dictionary
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
    failure_code: str | None = None

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
            failure_code=data.get("failure_code")
        )

@dataclass
class AgentTransactionUpload:
    transaction_id: id
    raw_text: dict[str, Any]

class ExpenseCategorizerAgent:
    """Agent for categorizing expense transactions using LLM"""

    def __init__(self, api_key: str | None = None, user_rules: list[str] | None = None, available_categories: list[str] | None = None):
        """
        Args:
            api_key: Gemini API key (optional, will try env var)
            user_rules: list of strict user-defined categorization rules
        """
        self.api_key = api_key or get_api_key()

        self.available_categories = available_categories or []

        # User-defined strict rules
        self.user_rules = user_rules or []

    def get_transaction_rule_prompt(self, user_input_text: str) -> str:
        """
        Generates the string representation of the internal instruction prompt
        for the LLM agent, including validation for slurs, category existence,
        and detailed failure reason codes.

        Args:
            user_input_text: The free-text rule provided by the user (in Italian).

        Returns:
            The detailed prompt string for the LLM.
        """

        # Format the list of valid categories for insertion into the prompt
        categories_list_str = ", ".join([f"'{c}'" for c in self.available_categories])

        prompt = f"""
        # Istruzioni per l'Analisi e la Validazione Avanzata della Regola di Categorizzazione

        **TASK:** Analizza il seguente testo libero fornito dall'utente per estrarre una regola di categorizzazione delle transazioni. Il tuo output deve essere **esclusivamente** un oggetto JSON conforme allo schema specificato e deve eseguire le seguenti convalide:

        1. **Controllo Contenuto:** Verifica la presenza di linguaggio inappropriato o ingiurioso (slurs). Se presente, la regola non è valida.
        2. **Controllo Categoria:** La categoria identificata nel testo utente **deve** corrispondere esattamente a uno dei seguenti valori validi: [{categories_list_str}].
        3. **Estrazione Dati:** Estrai l'intervallo di date e la lista di commercianti.

        **TESTO UTENTE DA ANALIZZARE:**
        ---
        {user_input_text}
        ---

        ---

        ## SCHEMA JSON RICHIESTO PER L'OUTPUT

        **ATTENZIONE:** L'output deve essere un **singolo** oggetto JSON valido, **senza** alcun testo esplicativo, note o markdown aggiuntivo.

        ```json
        {{
          "dateFrom": "YYYY-MM-DD",
          "dateTo": "YYYY-MM-DD",
          "merchants": ["nome_commerciante_1", "nome_commerciante_2"],
          "valid": "true|false",
          "category": "nome_categoria",
          "reason": ""
        }}
        ```

        ---

        ## REGOLE DI ESTRAZIONE E VALIDAZIONE

        1.  **Category (Categoria):** * Estrai la singola parola o frase che definisce la categoria desiderata.
            * Se la categoria estratta non corrisponde esattamente a **uno** dei valori in [{categories_list_str}], il campo `category` viene mantenuto come estratto, ma `valid` deve essere **"false"**.

        2.  **Merchants (Commercianti):** * Identifica tutti i nomi di commercianti (aziende, negozi, servizi) specificati.
            * Inserisci come un **array di stringhe**. Inserire un array vuoto (`[]`) se non sono stati trovati commercianti.

        3.  **Date Range (Intervallo di Date):** * Convalida e formatta le date rigorosamente in **YYYY-MM-DD**.
            * Se non specificato, lascia `dateFrom` e `dateTo` **vuoti** (`""`). Se le date sono malformate o incoerenti (es. 'dateFrom' dopo 'dateTo'), `valid` deve essere **"false"**.

        4.  **Valid (Validità) e Reason (Codice Motivo):**
            * **"true"**: Solo se sono stati identificati: 
                a) Una `category` **valida** che corrisponda a una della lista.
                b) Almeno un `merchant`.
                c) Nessun contenuto inappropriato o ingiurioso.
                d) L'intervallo di date è valido o vuoto.

            * **"false"**: Se la regola non è valida, imposta il campo `valid` su `"false"` e riempi il campo `reason` con il codice appropriato:
                * **Motivo 0 (Contenuto Inappropriato/Ingiurioso):** Se il testo utente contiene slurs o linguaggio inappropriato. **(Priorità massima)**
                * **Motivo 1 (Categoria non valida/mancante):** Se non è stata trovata una categoria o la categoria non è presente in [{categories_list_str}].
                * **Motivo 2 (Intervallo di date non valido):** Se le date sono malformate o l'intervallo è logicamente impossibile (es. data di inizio successiva alla data di fine).
                * **Motivo 3 (Impossibile da comprendere/Commerciante mancante):** Se la richiesta è vaga, manca un commerciante, o è impossibile estrarre elementi chiave diversi dalla categoria.

            * Se `valid` è `"true"`, il campo `reason` deve essere **vuoto** (`""`).

        ---

        **RESTITUISCI SOLO L'OGGETTO JSON COME STRINGA.** NON AGGIUNGERE ALTRO TESTO.
        """
        return prompt

    def process_user_rule(self, user_input_text: str) -> dict[str, Any]:
        try:
            prompt = self.get_transaction_rule_prompt(user_input_text)
            raw_response = call_gemini_api(prompt, self.api_key)
            response_text = parse_gemini_response(raw_response)
            parsed_json = parse_llm_response_json(response_text)
            return parsed_json
        except Exception as e:
            return {"valid": False, "reason": str(e)}

    def build_batch_prompt(self, batch: list[AgentTransactionUpload]) -> str:
        """Build prompt for a batch of transactions"""

        # Format transactions
        transactions_text = ""
        for i, tx in enumerate(batch, 1):
            transactions_text += f"{i}. ID: {tx.transaction_id}\n"
            for column, value in tx.raw_text.items():
                if column != 'id':
                    # Truncate very long values
                    display_value = str(value)[:200] + "..." if len(str(value)) > 200 else value
                    transactions_text += f"   {column}: {display_value}\n"
            transactions_text += "\n"

        # Build user rules section
        user_rules_section = ""
        if self.user_rules:
            user_rules_section = """
⚠️ ⚠️ ⚠️ REGOLE UTENTE OBBLIGATORIE - PRIORITÀ ASSOLUTA ⚠️ ⚠️ ⚠️

QUESTE REGOLE DEVONO ESSERE RISPETTATE IN MODO ASSOLUTO E HANNO PRIORITÀ SU QUALSIASI ALTRA LOGICA.

"""
            for i, rule in enumerate(self.user_rules, 1):
                user_rules_section += f"{i}. {rule}\n"

            user_rules_section += """
⚠️ IMPORTANTE: Se una transazione corrisponde a qualsiasi regola utente sopra, DEVI applicare quella regola.
Le regole utente hanno PRIORITÀ ASSOLUTA su qualsiasi altra considerazione.

"""

        return f"""Sei un assistente per categorizzare spese bancarie italiane.

{user_rules_section}

CATEGORIE DISPONIBILI:
{chr(10).join('- ' + cat for cat in self.available_categories)}

ISTRUZIONI (IN ORDINE DI PRIORITÀ):
1. VERIFICA PRIMA LE REGOLE UTENTE - Se una transazione corrisponde, applica quella categoria OBBLIGATORIAMENTE
2. Analizza ogni transazione e determina se è una SPESA (uscita)
3. Se è spesa: estrai merchant e categorizza
4. Se non è una spesa categorizza come 'not_expense'.

ESEMPI (MA REGOLE UTENTE HANNO PRIORITÀ):
- AMAZON, shopping → "shopping"
- Benzina → "carburante" 
- Ristoranti → "vita sociale"
- Supermercati → "spesa"
- Farmacie → "spese mediche"

IN CASO DI FALLIMENTO (IMPOSSIBILE CAPIRE LA TRANSAZIONE):
Aggiungere un campo "failure_code" con i seguenti codici:
0 -> Incomprensibile
1 -> Non ho trovato la categoria
IL FALLIMENTO SI APPLICA SE E SOLO SE TROVARE UNA CATEGORIA NUOVA RISULTA INEFFICACE OPPURE SI TRATTA DI UN'ENTRATA.

⚠️ FORMATO OUTPUT RICHIESTO ⚠️
Devi restituire SOLO un array JSON contenente gli oggetti di categorizzazione.
NON includere wrapper o oggetti esterni.
Restituisci DIRETTAMENTE l'array JSON.

FORMATO:
[
  {{
    "transaction_id": "tx_001",
    "date": "2023-01-01",
    "category": "spesa",
    "merchant": "SUPERMERCATO XYZ",
    "amount": 45.50,
    "original_amount": "-45,50",
    "description": "Descrizione completa",
    "applied_user_rule": "Regola 1: descrizione" (SOLO se applicata),
    "failure_code": 0 (SOLO se fallimento)
  }},
  {{
    "transaction_id": "tx_002",
    "date": "2023-01-02",
    "category": "carburante",
    "merchant": "STAZIONE SERVIZIO",
    "amount": 60.00,
    "original_amount": "-60,00",
    "description": "Benzina"
  }}
]

TRANSAZIONI:
{transactions_text}

RICORDA: 
- Le regole utente sono OBBLIGATORIE e hanno PRIORITÀ ASSOLUTA
- Restituisci SOLO l'array JSON, senza wrapper o oggetti esterni

RISPONDI SOLO CON L'ARRAY JSON:"""

    def process_batch(self, batch: list[AgentTransactionUpload]) -> list[TransactionCategorization]:
        """
        Process a single batch through LLM and deserialize into structured objects.

        Args:
            batch: list of transactions with 'id' and raw data
            batch_num: Batch number for tracking

        Returns:
            list[TransactionCategorization]: Array of categorization objects
        """
        try:
            # Build prompt
            prompt = self.build_batch_prompt(batch)

            print(f"📤 Sending batch to API...")

            # Send to API
            raw_response = call_gemini_api(prompt, self.api_key)
            response_text = parse_gemini_response(raw_response)

            # Parse JSON array response
            categorizations_data = parse_json_array(response_text)

            # Deserialize into structured objects
            categorizations = [
                TransactionCategorization.from_dict(item)
                for item in categorizations_data
            ]

            # Log completion
            expense_count = len([c for c in categorizations if c.category != "not_expense"])
            print(f"✅ Batch completed: {expense_count}")
            return categorizations

        except Exception as e:
            print(f"❌ Batch failed: {str(e)}")
            # Return empty list on error
            return []