# agent.py
import os
import json
import requests
from typing import Dict, List, Optional, Any


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


def call_gemini_api(prompt: str, api_key: str) -> Dict:
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


def parse_gemini_response(response: Dict) -> str:
    """Extract text content from Gemini response"""
    try:
        return response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Invalid response structure: {e}")


def parse_json_categorization(response_text: str) -> Dict:
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


class ExpenseCategorizerAgent:
    """Agent for categorizing expense transactions using LLM"""

    def __init__(self, api_key: Optional[str] = None, user_rules: Optional[List[str]] = None):
        """
        Args:
            api_key: Gemini API key (optional, will try env var)
            user_rules: List of strict user-defined categorization rules
        """
        self.api_key = api_key or get_api_key()

        # Italian expense categories
        self.available_categories = [
            "casa", "spesa", "sport", "partita iva", "spese mediche",
            "trasporti", "affitto", "abbonamenti", "shopping", "scuola",
            "bollette", "vacanze", "regali", "vita sociale", "carburante", "auto"
        ]

        # User-defined strict rules
        self.user_rules = user_rules or []

    def build_batch_prompt(self, batch: List[Dict], batch_num: int) -> str:
        """Build prompt for a batch of transactions"""

        # Format transactions
        transactions_text = ""
        for i, tx in enumerate(batch, 1):
            transactions_text += f"{i}. ID: {tx['id']}\n"
            for column, value in tx.items():
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
4. Se NON è spesa: usa "not_expense"

ESEMPI (MA REGOLE UTENTE HANNO PRIORITÀ):
- AMAZON, shopping → "shopping"
- Benzina → "carburante" 
- Ristoranti → "vita sociale"
- Supermercati → "spesa"
- Farmacie → "spese mediche"

RISPOSTA RICHIESTA - SOLO JSON VALIDO:
{{
  "categorizations": [
    {{
      "transaction_id": "tx_001",
      "category": "spesa",
      "merchant": "SUPERMERCATO XYZ",
      "amount": 45.50,
      "original_amount": "-45,50",
      "description": "Descrizione completa",
      "applied_user_rule": "Regola 1: descrizione della regola applicata" (SOLO se applicata una regola utente)
    }}
  ],
  "new_categories_created": [],
  "reasoning_summary": "Breve riassunto",
  "batch_info": "Batch {batch_num}"
}}

TRANSAZIONI:
{transactions_text}

RICORDA: Le regole utente sono OBBLIGATORIE e hanno PRIORITÀ ASSOLUTA su tutto.

RISPONDI SOLO JSON:"""

    def process_batch(self, batch: List[Dict], batch_num: int) -> Dict[str, Any]:
        """
        Process a single batch through LLM.

        Args:
            batch: List of transactions with 'id' and raw data
            batch_num: Batch number for tracking

        Returns:
            Dictionary with categorization results
        """
        try:
            # Build prompt
            prompt = self.build_batch_prompt(batch, batch_num)

            # Send to API
            raw_response = call_gemini_api(prompt, self.api_key)
            response_text = parse_gemini_response(raw_response)

            # Parse response
            parsed_json = parse_json_categorization(response_text)

            # Extract categorizations
            all_categorizations = {}
            expense_categorizations = {}

            for item in parsed_json.get("categorizations", []):
                tx_id = item.get("transaction_id")
                category = item.get("category")

                if tx_id and category:
                    merchant_value = item.get("merchant")
                    merchant = merchant_value.strip() if merchant_value else ""

                    description_value = item.get("description")
                    description = description_value if description_value else ""

                    all_categorizations[tx_id] = {
                        "category": category,
                        "merchant": merchant,
                        "amount": item.get("amount", 0),
                        "original_amount": item.get("original_amount", ""),
                        "description": description,
                        "reason": item.get("reason", ""),
                        "applied_user_rule": item.get("applied_user_rule", "")
                    }

                    if category != "not_expense":
                        expense_categorizations[tx_id] = category

            # Log completion
            print(f"✅ Batch {batch_num} complete: {len(expense_categorizations)} expenses categorized")

            return {
                'categorizations': expense_categorizations,
                'all_results': all_categorizations,
                'parsed_json': parsed_json,
                'batch_num': batch_num,
                'batch_size': len(batch),
                'success': True
            }

        except Exception as e:
            print(f"❌ Batch {batch_num} failed: {str(e)}")

            return {
                'categorizations': {},
                'all_results': {},
                'parsed_json': {},
                'batch_num': batch_num,
                'batch_size': len(batch),
                'success': False,
                'error': str(e)
            }