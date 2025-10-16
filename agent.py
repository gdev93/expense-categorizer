import os
import json
import requests
import pandas as pd
from typing import Dict, List, Optional, Any
from difflib import SequenceMatcher


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


def call_gemini_api(prompt: str, api_key: str) -> Dict:
    """Make request to Gemini API with increased token limit"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4000
        }
    }

    print("🚀 Making request to Gemini API...")
    print(f"📝 API Key: {api_key[:10]}...{api_key[-10:]}")
    print(f"🌐 Model: gemini-2.0-flash")
    print("=" * 60)

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
    """Parse JSON response from LLM categorization with better error handling"""
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

        # Try to find JSON boundaries more carefully
        start_brace = cleaned_text.find("{")
        if start_brace == -1:
            raise ValueError("No opening brace found")

        # Find the last complete closing brace
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


def extract_metadata(response: Dict) -> Dict:
    """Extract metadata from Gemini response"""
    usage = response.get("usageMetadata", {})

    return {
        "model_version": response.get("modelVersion", "unknown"),
        "total_tokens": usage.get("totalTokenCount", 0),
        "prompt_tokens": usage.get("promptTokenCount", 0),
        "response_tokens": usage.get("candidatesTokenCount", 0),
        "finish_reason": response["candidates"][0].get("finishReason", "unknown"),
    }


class PersistentMemoryPipeline:
    def __init__(self, csv_file_path: str, memory_file: str = "classification_memory.json",
                 api_key: Optional[str] = None, user_rules: Optional[List[str]] = None):
        """
        Initialize pipeline with persistent memory

        Args:
            csv_file_path: Path to the CSV file
            memory_file: Path to memory file for storing classifications
            api_key: Gemini API key (optional, will try env var)
            user_rules: List of strict user-defined categorization rules
        """
        self.csv_file_path = csv_file_path
        self.memory_file = memory_file
        self.api_key = api_key or get_api_key()
        self.batch_size = 15
        self.similarity_threshold = 0.8

        # Italian expense categories
        self.available_categories = [
            "casa", "spesa", "sport", "partita iva", "spese mediche",
            "trasporti", "affitto", "abbonamenti",
            "shopping", "scuola", "bollette", "vacanze",
            "regali", "vita sociale", "carburante", "auto"
        ]

        # User-defined strict rules
        self.user_rules = user_rules or []

        # Load existing memory
        self.classification_memory = self.load_memory()
        print(f"💾 Loaded {len(self.classification_memory)} classifications from memory")

        if self.user_rules:
            print(f"📋 Loaded {len(self.user_rules)} user-defined strict rules")

    def load_memory(self) -> Dict[str, Dict[str, Any]]:
        """Load previous classifications from file"""
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert old format if needed
                    if data and isinstance(list(data.values())[0], str):
                        # Old format: {"merchant": "category"} -> new format
                        return {k: {"category": v, "count": 1} for k, v in data.items()}
                    return data
            return {}
        except (FileNotFoundError, json.JSONDecodeError, IndexError):
            return {}

    def save_memory(self):
        """Save classifications to file"""
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.classification_memory, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved {len(self.classification_memory)} classifications to memory")

    def normalize_merchant(self, merchant: str) -> str:
        """Normalize merchant name for consistent matching"""
        if not merchant:
            return ""
        return merchant.upper().strip().replace("  ", " ")

    def fuzzy_match_memory(self, merchant: str) -> Optional[Dict[str, Any]]:
        """Find similar merchants in memory using fuzzy matching"""
        if not merchant:
            return None

        normalized_merchant = self.normalize_merchant(merchant)
        if not normalized_merchant:
            return None

        best_match = None
        best_score = 0.0

        for stored_merchant, classification_data in self.classification_memory.items():
            similarity = SequenceMatcher(None, normalized_merchant, stored_merchant.upper()).ratio()
            if similarity > best_score and similarity >= self.similarity_threshold:
                best_score = similarity
                best_match = {
                    "category": classification_data["category"],
                    "similarity": similarity,
                    "matched_merchant": stored_merchant,
                    "count": classification_data.get("count", 1)
                }

        return best_match

    def add_to_memory(self, merchant: str, category: str, description: str = ""):
        """Add or update merchant classification in memory"""
        if not merchant:
            return

        normalized_merchant = self.normalize_merchant(merchant)
        if not normalized_merchant:
            return

        if normalized_merchant in self.classification_memory:
            # Update count for existing merchant
            self.classification_memory[normalized_merchant]["count"] += 1
        else:
            # Add new merchant
            self.classification_memory[normalized_merchant] = {
                "category": category,
                "count": 1,
                "description": description[:100] if description else ""  # Store short description
            }

    def load_and_parse_csv(self) -> List[Dict[str, Any]]:
        """Load CSV and pass raw data to LLM for interpretation"""
        print("📄 Loading CSV file...")

        try:
            df = pd.read_csv(self.csv_file_path, encoding='utf-8')
            print(f"✅ Loaded {len(df)} rows from CSV")

            transactions = []

            for idx, row in df.iterrows():
                transaction = {
                    'id': f'tx_{idx:03d}',
                    'raw_data': {}
                }

                for column, value in row.items():
                    if pd.notna(value) and str(value).strip():
                        transaction['raw_data'][column] = str(value).strip()

                if transaction['raw_data']:
                    transactions.append(transaction)

            print(f"📊 Processed {len(transactions)} raw transactions")
            return transactions

        except Exception as e:
            raise Exception(f"Failed to load CSV: {e}")

    def create_simple_batches(self, transactions: List[Dict]) -> List[List[Dict]]:
        """Create simple batches of max 15 transactions without grouping"""
        batches = []

        for i in range(0, len(transactions), self.batch_size):
            batch = transactions[i:i + self.batch_size]
            batches.append(batch)

        return batches

    def build_batch_prompt_with_memory(self, batch: List[Dict], batch_num: int) -> str:
        """Build prompt that includes strict user rules (memory excluded from prompt)"""

        transactions_text = ""
        for i, tx in enumerate(batch, 1):
            transactions_text += f"{i}. ID: {tx['id']}\n"
            for column, value in tx['raw_data'].items():
                # Truncate very long descriptions to prevent token overflow
                display_value = value[:200] + "..." if len(value) > 200 else value
                transactions_text += f"   {column}: {display_value}\n"
            transactions_text += "\n"

        # Build strict user rules section
        user_rules_section = ""
        if self.user_rules:
            user_rules_section = f"""
⚠️ ⚠️ ⚠️ REGOLE UTENTE OBBLIGATORIE - PRIORITÀ ASSOLUTA ⚠️ ⚠️ ⚠️

QUESTE REGOLE DEVONO ESSERE RISPETTATE IN MODO ASSOLUTO E HANNO PRIORITÀ SU QUALSIASI ALTRA LOGICA.
NON PUOI MAI VIOLARE QUESTE REGOLE, NEMMENO SE SEMBRANO CONTRADDIRE LA LOGICA NORMALE.

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
      "description": "Descrizione completa dal CSV",
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

    def process_batch_with_memory(self, batch: List[Dict], batch_num: int) -> Dict[str, Any]:
        """Process a single batch through LLM with memory enhancement"""
        print(f"🤖 Processing batch {batch_num} ({len(batch)} transactions)...")

        # First check: see if we can resolve any from memory
        memory_hits = 0
        memory_resolved = {}

        for tx in batch:
            # Try to extract likely merchant from raw data for memory lookup
            potential_merchant = self.extract_potential_merchant(tx)
            if potential_merchant:
                memory_match = self.fuzzy_match_memory(potential_merchant)
                if memory_match:
                    # Extract amount and description from raw data
                    amount, original_amount = self.extract_amount_from_raw(tx)
                    description = self.extract_description_from_raw(tx)

                    memory_resolved[tx['id']] = {
                        "category": memory_match["category"],
                        "merchant": potential_merchant,
                        "amount": amount,
                        "original_amount": original_amount,
                        "description": description,
                        "memory_match": True,
                        "similarity": memory_match["similarity"],
                        "matched_merchant": memory_match["matched_merchant"]
                    }
                    memory_hits += 1

        if memory_hits > 0:
            print(f"💾 Found {memory_hits} potential memory matches")

        try:
            prompt = self.build_batch_prompt_with_memory(batch, batch_num)
            raw_response = call_gemini_api(prompt, self.api_key)
            response_text = parse_gemini_response(raw_response)
            parsed_json = parse_json_categorization(response_text)

            all_categorizations = {}
            expense_categorizations = {}

            for item in parsed_json.get("categorizations", []):
                tx_id = item.get("transaction_id")
                category = item.get("category")

                if tx_id and category:
                    # Safely handle null/None values from Gemini
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
                        "applied_user_rule": item.get("applied_user_rule", ""),
                        "memory_match": False
                    }

                    # Add to memory for future use
                    if category != "not_expense" and merchant:
                        self.add_to_memory(merchant, category, description)

                    if category != "not_expense":
                        expense_categorizations[tx_id] = category

            # Merge memory-resolved items with LLM results
            # BUT: LLM results override memory if user rules were applied
            for tx_id, memory_data in memory_resolved.items():
                # Only use memory if LLM didn't process this transaction
                if tx_id not in all_categorizations:
                    all_categorizations[tx_id] = memory_data
                    if memory_data["category"] != "not_expense":
                        expense_categorizations[tx_id] = memory_data["category"]

            metadata = extract_metadata(raw_response)

            return {
                'categorizations': expense_categorizations,
                'all_results': all_categorizations,
                'parsed_json': parsed_json,
                'metadata': metadata,
                'batch_num': batch_num,
                'batch_size': len(batch),
                'memory_hits': memory_hits,
                'success': True
            }

        except Exception as e:
            print(f"\n❌ BATCH {batch_num} ERROR DETAILS:")
            print("=" * 50)
            print(f"Error: {str(e)}")
            print(f"Error Type: {type(e).__name__}")

            try:
                prompt = self.build_batch_prompt_with_memory(batch, batch_num)
                raw_response = call_gemini_api(prompt, self.api_key)
                response_text = parse_gemini_response(raw_response)

                print(f"\n📥 RAW GEMINI RESPONSE (first 2000 chars):")
                print("-" * 30)
                print(response_text[:2000])
                if len(response_text) > 2000:
                    print(f"\n... [TRUNCATED - Total length: {len(response_text)} chars]")
                print("-" * 30)

            except Exception as response_error:
                print(f"\n🚫 Could not retrieve Gemini response: {response_error}")

            print("=" * 50)

            return {
                'categorizations': {},
                'all_results': {},
                'parsed_json': {},
                'metadata': {},
                'batch_num': batch_num,
                'batch_size': len(batch),
                'memory_hits': 0,
                'success': False,
                'error': str(e)
            }

    def extract_potential_merchant(self, transaction: Dict) -> Optional[str]:
        """Try to extract merchant name from raw transaction data for memory lookup"""
        raw_data = transaction.get('raw_data', {})

        # Look for common patterns in Italian bank data
        for key, value in raw_data.items():
            value_str = str(value).strip()

            # Check for "presso" pattern (card payments)
            if "presso" in value_str.lower():
                try:
                    merchant_part = value_str.split("presso")[1].split("-")[0].strip()
                    if len(merchant_part) > 3:
                        return merchant_part
                except:
                    pass

            # Check for direct debit patterns
            if "Addebito SDD" in value_str:
                if "AMAZON" in value_str:
                    return "AMAZON"
                elif "PayPal" in value_str:
                    return "PayPal"
                elif "TELECOM ITALIA" in value_str or "TIM" in value_str:
                    return "TELECOM ITALIA"
                elif "Esselunga" in value_str:
                    return "ESSELUNGA"
                elif "YADA ENERGIA" in value_str:
                    return "YADA ENERGIA"

        return None

    def extract_amount_from_raw(self, transaction: Dict) -> tuple[float, str]:
        """Extract amount from raw transaction data"""
        raw_data = transaction.get('raw_data', {})

        # Look for amount in common column names
        for key, value in raw_data.items():
            key_lower = key.lower()
            if any(keyword in key_lower for keyword in ['importo', 'amount', 'dare', 'uscite']):
                try:
                    value_str = str(value).strip()
                    # Handle Italian number format (e.g., "-45,50" or "45,50")
                    cleaned = value_str.replace('.', '').replace(',', '.').replace('€', '').strip()
                    amount = abs(float(cleaned))
                    return amount, value_str
                except (ValueError, AttributeError):
                    continue

        return 0, "unknown"

    def extract_description_from_raw(self, transaction: Dict) -> str:
        """Extract description from raw transaction data"""
        raw_data = transaction.get('raw_data', {})

        # Concatenate all raw data for description
        description_parts = []
        for key, value in raw_data.items():
            value_str = str(value).strip()
            if value_str and len(value_str) > 0:
                description_parts.append(f"{key}: {value_str}")

        full_description = " | ".join(description_parts)
        # Limit length
        return full_description[:200] if len(full_description) > 200 else full_description

    def run_pipeline(self) -> Dict[str, Any]:
        """Run the complete categorization pipeline with persistent memory"""
        print("🚀 Starting Persistent Memory Pipeline...")
        print("=" * 60)

        transactions = self.load_and_parse_csv()

        if not transactions:
            raise Exception("No valid transactions found in CSV")

        print(f"\n📦 Creating simple batches...")
        batches = self.create_simple_batches(transactions)
        print(f"✅ Created {len(batches)} simple batches")

        print(f"\n🤖 Processing {len(batches)} batches with memory enhancement...")
        all_results = []
        all_categorizations = {}
        all_detailed_results = {}
        all_new_categories = set()
        failed_batches = []
        total_memory_hits = 0
        user_rules_applied = 0

        for i, batch in enumerate(batches, 1):
            result = self.process_batch_with_memory(batch, i)
            all_results.append(result)

            if result['success']:
                all_categorizations.update(result['categorizations'])
                all_detailed_results.update(result['all_results'])
                total_memory_hits += result.get('memory_hits', 0)

                # Count user rules applied
                for tx_result in result['all_results'].values():
                    if tx_result.get('applied_user_rule'):
                        user_rules_applied += 1

                new_cats = result['parsed_json'].get('new_categories_created', [])
                all_new_categories.update(new_cats)

                expenses_found = len(result['categorizations'])
                total_processed = len(result['all_results'])
                memory_info = f" ({result.get('memory_hits', 0)} from memory)" if result.get('memory_hits',
                                                                                             0) > 0 else ""
                print(
                    f"✅ Batch {i} completed: {expenses_found} expenses, {total_processed - expenses_found} non-expenses{memory_info}")
            else:
                failed_batches.append(i)
                print(f"❌ Batch {i} failed: {result.get('error', 'Unknown error')}")

        # Save updated memory
        self.save_memory()

        final_results = {
            'total_transactions': len(transactions),
            'total_batches': len(batches),
            'successful_batches': len(batches) - len(failed_batches),
            'failed_batches': failed_batches,
            'successful_categorizations': len(all_categorizations),
            'categorizations': all_categorizations,
            'detailed_results': all_detailed_results,
            'new_categories_created': list(all_new_categories),
            'batch_results': all_results,
            'total_memory_hits': total_memory_hits,
            'user_rules_applied': user_rules_applied,
            'memory_size': len(self.classification_memory),
            'coverage': len(all_categorizations) / len(transactions) * 100 if transactions else 0
        }

        return final_results

    def print_final_results(self, results: Dict[str, Any]):
        """Print comprehensive final results with memory statistics"""
        print("\n" + "=" * 60)
        print("📊 RISULTATI FINALI CATEGORIZZAZIONE CON MEMORIA")
        print("=" * 60)

        total_processed = len(results['detailed_results'])
        expenses_found = len(results['categorizations'])
        non_expenses = total_processed - expenses_found

        print(f"Totale Transazioni: {results['total_transactions']}")
        print(f"Batch Riusciti: {results['successful_batches']}/{results['total_batches']}")

        if results['failed_batches']:
            print(f"Batch Falliti: {results['failed_batches']}")

        print(f"Transazioni Elaborate: {total_processed}")
        print(f"Spese Identificate: {expenses_found}")
        print(f"Non-Spese: {non_expenses}")
        print(f"Copertura: {results['coverage']:.1f}%")

        # User rules statistics
        if results.get('user_rules_applied', 0) > 0:
            print(f"\n📋 REGOLE UTENTE APPLICATE: {results['user_rules_applied']}")

        # Memory statistics
        print(f"\n💾 STATISTICHE MEMORIA:")
        print(f"Classificazioni in Memoria: {results['memory_size']}")
        print(f"Match da Memoria: {results['total_memory_hits']}")
        if results['total_memory_hits'] > 0 and expenses_found > 0:
            memory_percentage = (results['total_memory_hits'] / expenses_found) * 100
            print(f"Efficienza Memoria: {memory_percentage:.1f}% delle spese risolte da memoria")

        if results['new_categories_created']:
            print(f"\n🆕 NUOVE CATEGORIE:")
            for category in results['new_categories_created']:
                print(f"  - {category}")

        print(f"\n📋 SUDDIVISIONE SPESE:")
        category_counts = {}
        memory_counts = {}

        for tx_id, category in results['categorizations'].items():
            category_counts[category] = category_counts.get(category, 0) + 1

            # Count memory vs LLM
            if tx_id in results['detailed_results']:
                if results['detailed_results'][tx_id].get('memory_match', False):
                    memory_counts[category] = memory_counts.get(category, 0) + 1

        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / expenses_found) * 100 if expenses_found > 0 else 0
            memory_count = memory_counts.get(category, 0)
            memory_info = f" ({memory_count} da memoria)" if memory_count > 0 else ""
            print(f"  {category}: {count} ({percentage:.1f}%){memory_info}")

        # Show examples of user rules applied
        if results.get('user_rules_applied', 0) > 0:
            print(f"\n🎯 ESEMPI REGOLE UTENTE APPLICATE:")
            rule_examples = []
            for tx_id, details in results['detailed_results'].items():
                if details.get('applied_user_rule') and len(rule_examples) < 3:
                    rule_examples.append(
                        f"  {tx_id} - {details['merchant']} → {details['category']} (Regola: {details['applied_user_rule']})")

            for example in rule_examples:
                print(example)

        # Show some examples of memory matches
        if results['total_memory_hits'] > 0:
            print(f"\n🎯 ESEMPI MATCH DA MEMORIA:")
            memory_examples = []
            for tx_id, details in results['detailed_results'].items():
                if details.get('memory_match', False) and len(memory_examples) < 3:
                    similarity = details.get('similarity', 0)
                    matched_merchant = details.get('matched_merchant', 'N/A')
                    memory_examples.append(
                        f"  {details['merchant']} → {details['category']} (simile a: {matched_merchant}, {similarity:.2f})")

            for example in memory_examples:
                print(example)

        successful_batches = [b for b in results['batch_results'] if b['success']]
        if successful_batches:
            total_tokens = sum(batch['metadata']['total_tokens'] for batch in successful_batches)
            print(f"\n💰 Token utilizzati: {total_tokens}")

        print(f"\n💾 Memoria salvata in: {self.memory_file}")
        print("✅ Pipeline completata!")

    def print_memory_info(self):
        """Print current memory statistics"""
        if not self.classification_memory:
            print("📝 Memoria vuota")
            return

        print(f"\n📝 STATO MEMORIA CORRENTE:")
        print("=" * 40)
        print(f"Totale Merchant Memorizzati: {len(self.classification_memory)}")

        # Group by category
        category_breakdown = {}
        for merchant_data in self.classification_memory.values():
            category = merchant_data['category']
            category_breakdown[category] = category_breakdown.get(category, 0) + 1

        print("Distribuzione per categoria:")
        for category, count in sorted(category_breakdown.items(), key=lambda x: x[1], reverse=True):
            print(f"  {category}: {count} merchant")

        # Show most frequent
        frequent_merchants = sorted(
            self.classification_memory.items(),
            key=lambda x: x[1].get('count', 1),
            reverse=True
        )

        print(f"\nMerchant più frequenti:")
        for merchant, data in frequent_merchants[:5]:
            print(f"  {merchant}: {data['category']} ({data.get('count', 1)}x)")


def main():
    """Main execution function"""
    try:
        csv_file = "example.csv"

        if not os.path.exists(csv_file):
            print(f"❌ File CSV non trovato: {csv_file}")
            return

        # Define strict user rules
        user_rules = [
            "Every PayPal transaction with amounts 2.2, 69.0, or 10.0 MUST be categorized as 'trasporti' (transports). This rule is ABSOLUTE.",
            "RETITALIA is a fuel distributor and MUST ALWAYS be categorized as 'carburante' (fuel). This rule is ABSOLUTE."
        ]

        pipeline = PersistentMemoryPipeline(csv_file, user_rules=user_rules)

        # Show current memory state
        pipeline.print_memory_info()

        results = pipeline.run_pipeline()
        pipeline.print_final_results(results)

        output_file = "output.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Risultati salvati in '{output_file}'")

    except Exception as e:
        print(f"❌ Pipeline fallita: {e}")
        exit(1)


if __name__ == "__main__":
    main()