## Expense Categorizer 
The agent just asks gemini to categorize the input according to the hard-coded categories with a state-of-the-art prompt:
```python
    def build_batch_prompt_with_memory(self, batch: List[Dict], batch_num: int) -> str:
        """Build prompt that includes memory of previous classifications"""

        transactions_text = ""
        for i, tx in enumerate(batch, 1):
            transactions_text += f"{i}. ID: {tx['id']}\n"
            for column, value in tx['raw_data'].items():
                # Truncate very long descriptions to prevent token overflow
                display_value = value[:200] + "..." if len(value) > 200 else value
                transactions_text += f"   {column}: {display_value}\n"
            transactions_text += "\n"

        # Add memory section if we have classifications
        memory_section = ""
        if self.classification_memory:
            # Show most recent/frequent classifications
            sorted_memory = sorted(
                self.classification_memory.items(),
                key=lambda x: x[1].get("count", 1),
                reverse=True
            )

            memory_examples = []
            for merchant, data in sorted_memory[:15]:  # Show top 15
                count_info = f" ({data.get('count', 1)}x)" if data.get('count', 1) > 1 else ""
                memory_examples.append(f"- {merchant}: {data['category']}{count_info}")

            memory_section = f"""
CLASSIFICAZIONI PRECEDENTI (usa per consistenza):
{chr(10).join(memory_examples)}

IMPORTANTE: Mantieni consistenza con queste classificazioni quando vedi merchant simili o identici.
"""

        return f"""Sei un assistente per categorizzare spese bancarie italiane.

{memory_section}

CATEGORIE DISPONIBILI:
{chr(10).join('- ' + cat for cat in self.available_categories)}

ISTRUZIONI:
1. Analizza ogni transazione e determina se è una SPESA (uscita)
2. Se è spesa: estrai merchant e categorizza
3. Se NON è spesa: usa "not_expense"
4. Mantieni consistenza con le classificazioni precedenti mostrate sopra

ESEMPI:
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
      "description": "Descrizione completa dal CSV"
    }}
  ],
  "new_categories_created": [],
  "reasoning_summary": "Breve riassunto",
  "batch_info": "Batch {batch_num}"
}}

TRANSAZIONI:
{transactions_text}

RISPONDI SOLO JSON:"""
```
## Run
Activate the virtual environment and run:
```bash
export GEMINI_API_KEY=<the-gemini-api-key>
pip install pandas scikit-learn numpy requests
python agent.py
```
## How to see the results.
Check the `output.json` file. Its content should be copied in the data field in the [index.html](templates/main/index.html).
The transaction data is real data.

