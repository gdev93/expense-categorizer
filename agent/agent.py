
# agent.py
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from google import genai

from api.models import UploadFile, Category

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


@dataclass
class GeminiResponse:
    text: str
    prompt_tokens: int
    candidate_tokens: int
    model_name: str


def call_gemini_api(prompt: str, client: genai.Client, temperature: float = 0.1) -> GeminiResponse:
    """Make request to Gemini API using the new SDK"""
    model_id = 'gemini-2.5-flash-lite'
    try:
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
        )
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=config
        )

        return GeminiResponse(
            text=response.text,
            prompt_tokens=response.usage_metadata.prompt_token_count,
            candidate_tokens=response.usage_metadata.candidates_token_count,
            model_name=model_id
        )

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
    reasoning: str | None  # <--- NEW FIELD
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
            reasoning=data.get("reasoning", None),  # <--- Extract reasoning
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
    rag_context: list[dict[str, Any]] = None



@dataclass
class CsvStructure:
    """Structured CSV structure detection result"""
    description_field: str | None
    merchant_field: str | None
    transaction_date_field: str | None
    expense_amount_field: str | None  # Updated: specific field for expenses
    income_amount_field: str | None   # New: specific field for income
    operation_type_field: str | None
    confidence: str | None  # "high", "medium", "low"
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> 'CsvStructure':
        """Create instance from dictionary"""
        return cls(
            description_field=data.get("description_field"),
            merchant_field=data.get("merchant_field"),
            transaction_date_field=data.get("transaction_date_field"),
            expense_amount_field=data.get("expense_amount_field"),
            income_amount_field=data.get("income_amount_field"),
            operation_type_field=data.get("operation_type_field"),
            confidence=data.get("confidence", "low"),
            notes=data.get("notes")
        )


class ExpenseCategorizerAgent:
    """Agent for categorizing expense transactions using LLM"""

    def __init__(self, api_key: str | None = None, user_rules: list[str] | None = None,
                 available_categories: list[Category] | None = None) -> None:
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
            transactions: list[AgentTransactionUpload],
            known_date_column: str | None = None
    ) -> tuple[CsvStructure, GeminiResponse | None]:
        """
        Analyze the CSV structure using Gemini to identify column mappings.
        """
        # Build the prompt
        samples_text = ""
        for i, tx in enumerate(transactions):
            index = i + 1
            samples_text += f"Transazione {index}:\n"
            samples_text += f"  ID: {tx.transaction_id}\n"
            samples_text += "  Campi:\n"
            for column, value in tx.raw_text.items():
                # Truncate long values for token efficiency
                display_value = str(value)[:100] + "..." if len(str(value)) > 100 else value
                samples_text += f"    - {column}: {display_value}\n"
            samples_text += "\n"

        prompt_context = ""
        if known_date_column:
            prompt_context = f"\n\nNOTA: Abbiamo già identificato che il campo della data è '{known_date_column}'. Utilizzalo come transaction_date_field e concentrati sull'identificazione degli altri campi."

        prompt = f"""Sei un esperto nell'analisi di strutture dati di transazioni bancarie italiane.{prompt_context}

            Analizza i seguenti campioni di transazioni e identifica quali campi corrispondono a:
            1. **description_field**: Il campo contenente la descrizione/dettagli della transazione
            2. **merchant_field**: Il campo contenente SOLO il nome del commerciante/beneficiario (senza altra descrizione)
            3. **transaction_date_field**: Il campo contenente la data della transazione
            4. **expense_amount_field**: Il campo contenente SOLO gli importi delle SPESE (uscite, addebiti)
            5. **income_amount_field**: Il campo contenente SOLO gli importi degli ACCREDITI (entrate)
            6. **operation_type_field**: Il campo contenente il tipo di operazione

            ISTRUZIONI GENERALI:
            - Restituisci SOLO i nomi dei campi esattamente come appaiono nei dati
            - Se un campo non può essere determinato con sicurezza, restituisci null
            - Fornisci un livello di confidenza: "high", "medium", o "low"

            ⚠️ ISTRUZIONI CRITICHE PER IL CAMPO DESCRIPTION:
            - Il campo description_field DEVE contenere informazioni DESCRITTIVE e VARIABILI sulla transazione
            - **PRIORITÀ DI SELEZIONE per description_field:**
              1. Cerca campi con nomi come: "Osservazioni", "Note", "Dettagli", "Descrizione estesa", "Causale completa"
              2. Se non esistono, cerca campi come: "Movimento", "Descrizione", "Causale"
              3. **REGOLA CRITICA**: Se esistono PIÙ colonne descrittive (es. "Movimento" + "Osservazioni"):
                 - Scegli la colonna con il CONTENUTO PIÙ RICCO e DETTAGLIATO
                 - Le colonne "Osservazioni" o "Note" spesso contengono dettagli aggiuntivi come codici carta, località, riferimenti
                 - Confronta la LUNGHEZZA MEDIA dei valori tra le colonne: preferisci quella con valori più lunghi e informativi
            - **ESCLUSIONI per description_field:**
              * NON selezionare colonne che contengono SOLO tipi di operazione generici (es. "Bonifico ricevuto", "Pagamento con carta")
              * NON selezionare colonne con valori molto brevi e ripetitivi
              * Se una colonna contiene principalmente categorie/tipi (es. "Concetto", "Tipo Operazione") con valori fissi, questa è operation_type_field, NON description_field

            ⚠️ ISTRUZIONI CRITICHE PER IL CAMPO OPERATION_TYPE:
            - Il campo operation_type_field contiene il TIPO/CATEGORIA dell'operazione bancaria
            - Esempi di valori tipici: "Bonifico ricevuto", "Bonifico eseguito", "Pagamento con carta", "Addebito SDD", "Prelievo ATM"
            - Cerca colonne con nomi come: "Concetto", "Tipo", "Tipo Operazione", "Causale", "Operazione"
            - **REGOLA CRITICA**: Se una colonna ha valori RIPETITIVI e CATEGORICI (stesso valore per più transazioni), è probabilmente operation_type_field
            - **DISTINZIONE CHIAVE**: 
              * operation_type_field = valori fissi/categorici che si ripetono (es. sempre "Bonifico", "Pagamento carta")
              * description_field = valori variabili e unici per ogni transazione

            ⚠️ ISTRUZIONI CRITICHE PER IL CAMPO MERCHANT:
            - Il campo merchant_field DEVE contenere ESCLUSIVAMENTE il nome del commerciante/beneficiario
            - Se il nome del commerciante è mescolato con altra descrizione (date, importi, dettagli tecnici), il merchant_field DEVE essere null
            - NON selezionare campi che contengono solo tipi di operazione generici (es. "Pagamento Carta", "Addebito Diretto")
            - NON selezionare campi che contengono descrizioni lunghe con il nome embedded (es. "Operazione Mastercard... presso ESSELUNGA")
            - **REGOLA PRINCIPALE**: Se NON esiste una colonna dedicata solo ai nomi dei commercianti, restituisci merchant_field: null
            - **ECCEZIONE IMPORTANTE**: Se una colonna contiene nomi brevi e puliti di beneficiari/commercianti (es. "Meccanico auto", "Partita iva", "Bonifico"), può essere considerata merchant_field
            - Esempi di campi NON validi:
              * "CAUSALE" contenente solo "Pagamento Carta", "Bonifico In Uscita" → merchant_field: null
              * "DESCRIZIONE OPERAZIONE" con testo lungo che include il merchant → merchant_field: null
            - Esempi di campi validi:
              * Una colonna "Commerciante", "Merchant", "Beneficiario" con solo nomi → merchant_field: valido
              * Una colonna "Movimento" con nomi brevi come "Meccanico auto", "Gruppo carmeli spa" → merchant_field: valido

            ⚠️ ISTRUZIONI CRITICHE PER LA DATA TRANSAZIONE:
            - Il campo transaction_date_field DEVE essere una colonna dedicata ESCLUSIVAMENTE alle date (es. "Data", "Data Valuta", "Data Contabile").
            - CRITERIO DI ESCLUSIONE: Ignora qualsiasi colonna che contenga testo narrativo insieme alla data.
            - **CRITERIO DI SELEZIONE FINALE (Massima Priorità):**
              1. Se è disponibile una sola colonna data valida: selezionala.
              2. Se sono presenti più colonne data valide (es. "Data Operazione" e "Data Valuta"):
                 a. **DEVI comparare le date tra le colonne per OGNI transazione del campione.**
                 b. **Conta quante volte ciascuna colonna contiene la data più recente (posteriore).**
                 c. **Seleziona la colonna che ha il maggior numero di date posteriori/più recenti.**
                 d. **REGOLA ASSOLUTA: Anche se una sola transazione ha una data più recente in una colonna rispetto all'altra, quella colonna DEVE essere considerata come candidata primaria.**
                 e. La data più recente rappresenta tipicamente la data contabile/di addebito effettivo (quando il pagamento è stato realmente processato dalla banca).
                 f. **In caso di parità (uguale numero di date più recenti), preferisci la colonna con nomi come "Data Contabile", "Data Valuta", "Data Addebito" rispetto a "Data Operazione".**

            ⚠️ ISTRUZIONI CRITICHE PER GLI IMPORTI:
            - **PRIORITÀ 1**: Cerca prima colonne SEPARATE per spese e entrate
              * Cerca nomi come: "Uscite"/"Entrate", "Dare"/"Avere", "Addebiti"/"Accrediti", "Spese"/"Introiti"
              * Se trovi colonne separate:
                - expense_amount_field: la colonna con importi di USCITA (negativi o nella colonna "Uscite"/"Dare")
                - income_amount_field: la colonna con importi di ENTRATA (positivi o nella colonna "Entrate"/"Avere")

            - **PRIORITÀ 2**: Se NON ci sono colonne separate, cerca una SOLA colonna importo
              * Se esiste una sola colonna "Importo" o "Amount" con valori sia positivi che negativi:
                - expense_amount_field: usa questa colonna (l'utente filtrerà i negativi)
                - income_amount_field: usa questa colonna (l'utente filtrerà i positivi)

            - **NOTA**: Esamina TUTTI i campioni per capire la struttura corretta

            ═══════════════════════════════════════════════════════════════════
            📋 ESEMPIO DI ANALISI CORRETTA 📋
            ═══════════════════════════════════════════════════════════════════

            Data CSV di esempio:
            | Data valuta | Data | Concetto | Movimento | Importo | Osservazioni |
            |-------------|------|----------|-----------|---------|--------------|
            | 17/12/2025 | 17/12/2025 | Bonifico ricevuto | Meccanico auto | 458 | Meccanico auto |
            | 15/12/2025 | 15/12/2025 | Pagamento con carta | Gruppo carmeli spa | -458 | 5179090005496786 GRUPPO CARMELI SPA SAN ZENO NAVIIT |

            Analisi CORRETTA:
            - "Concetto" contiene valori RIPETITIVI/CATEGORICI ("Bonifico ricevuto", "Pagamento con carta") → operation_type_field
            - "Movimento" contiene nomi brevi dei beneficiari/commercianti → merchant_field (o description_field se più appropriato)
            - "Osservazioni" contiene dettagli estesi con codici carta, località → description_field (contiene più informazioni)
            - "Importo" contiene valori numerici con segno → expense_amount_field E income_amount_field

            FORMATO OUTPUT (JSON):
            {{
              "description_field": "nome_colonna_esatto_o_null",
              "merchant_field": "nome_colonna_esatto_o_null",
              "transaction_date_field": "nome_colonna_esatto_o_null",
              "expense_amount_field": "nome_colonna_esatto_o_null",
              "income_amount_field": "nome_colonna_esatto_o_null",
              "operation_type_field": "nome_colonna_esatto_o_null",
              "confidence": "high|medium|low",
              "notes": "string con spiegazione dettagliata delle scelte fatte"
            }}

            CAMPIONI DI TRANSAZIONI:
            {samples_text}

            Restituisci SOLO l'oggetto JSON, nient'altro."""

        try:
            response = call_gemini_api(prompt=prompt, client=self.client, temperature=1.0)
            # Parse the response
            result_dict = parse_llm_response_json(response.text)

            if not result_dict:
                # Fallback: try direct JSON parsing
                import json
                result_dict = json.loads(response.text.strip())

            return CsvStructure.from_dict(result_dict), response

        except Exception as e:
            logger.error(f"CSV structure detection failed: {e}")
            # Return empty structure on failure
            return CsvStructure(
                description_field=None,
                merchant_field=None,
                transaction_date_field=None,
                expense_amount_field=None,
                income_amount_field=None,
                operation_type_field=None,
                confidence="low",
                notes=f"Rilevamento fallito: {str(e)}"
            ), None

    def build_batch_prompt(self, batch: list[AgentTransactionUpload], upload_file: UploadFile) -> str:
        """Costruisce il prompt per un batch di transazioni"""

        logic_constraints = """
            ══════════════════════════════════════════════════════
            ⚠️ REGOLE UNIVERSALI DI CLASSIFICAZIONE
            ═══════════════════════════════════════════════════════
            1. **Identificazione del Circuito vs Esercente**:
               - Molte descrizioni contengono nomi di carte di credito, circuiti locali o programmi fedeltà (es. nomi che finiscono in 'Card', 'Pay', 'Azzurra', 'SMAC').
               - Questi termini indicano COME il cliente ha pagato, NON COSA ha comprato. 
               - IGNORA i termini legati ai circuiti per la scelta della categoria; focalizzati esclusivamente sul nome del negozio o dell'azienda.

            2. **Strategia di Categorizzazione Approfondita - DEVI ANALIZZARE A FONDO**:
               - PRIMA analizza il nome del merchant: cerca parole chiave che identifichino il settore (es. "BAR", "RISTORANTE", "FARMACIA", "BENZINA", "SUPERMERCATO", "NEGOZIO", "PALESTRA", "HOTEL").
               - POI analiza la descrizione completa: cerca indizi sul tipo di acquisto, il destinatario, il tipo di operazione.
               - USA la tua conoscenza: se riconosci un brand italiano o internazionale (es. CONAD, LIDL, COOP, IKEA, DECATHLON, ZALANDO, NETFLIX, SPOTIFY, ENEL, ENI), assegna la categoria corretta.
               - CONSIDERA il contesto: addebiti SDD da società energetiche = Bollette, pagamenti a scuole/università = Scuola, addebiti bancari = Bollette, assicurazioni = Assicurazioni, ecc.
               - ANALIZZA OGNI PAROLA: spesso il tipo di spesa è nascosto nella descrizione (es. "BOOKING.COM" = Vacanze, "RYANAIR" = Trasporti, "FARMACIE COMUNALI" = Spese mediche).

            3. **Esempi Simili dal Passato (RAG Context)**:
               - Per ogni transazione potresti trovare una sezione "ESEMPI SIMILI DAL PASSATO".
               - Questi sono esempi reali di transazioni passate dell'utente già categorizzate.
               - **IMPORTANTE**: Se un esempio simile corrisponde bene alla transazione attuale, segui la stessa categorizzazione (categoria e merchant) per garantire coerenza con lo storico dell'utente.
        """

        # Formatta le transazioni
        transactions_text = ""
        for i, tx in enumerate(batch, 1):
            transactions_text += f"{i}. TRANSACTION_ID: {tx.transaction_id}\n"
            transactions_text += "   RAW DATA:\n"
            for column, value in tx.raw_text.items():
                if column != 'id':
                    # Tronca i valori molto lunghi
                    display_value = str(value)[:200] + "..." if len(str(value)) > 200 else value
                    transactions_text += f"   - {column}: {display_value}\n"
            
            if tx.rag_context:
                transactions_text += "   ESEMPI SIMILI DAL PASSATO:\n"
                for ctx in tx.rag_context:
                    transactions_text += f"     • Descrizione: {ctx['description']} | Mercante: {ctx['merchant']} | Categoria: {ctx['category']}\n"
            
            transactions_text += "\n"

        # Build CSV structure hints section
        csv_hints_section = ""
        if upload_file:
            csv_hints_section = """
            ═══════════════════════════════════════════════════════════════════
            📋 INFORMAZIONI STRUTTURA CSV - SUGGERIMENTI PER L'ESTRAZIONE 📋
            ═══════════════════════════════════════════════════════════════════

            Per aiutarti nell'estrazione dei dati, ecco le informazioni sulla struttura CSV identificata:
            """
            if upload_file.description_column_name:
                csv_hints_section += f"📝 **DESCRIPTION FIELD**: Il campo '{upload_file.description_column_name}' contiene la descrizione della transazione.\n"
            if upload_file.merchant_column_name:
                csv_hints_section += f"🏪 **MERCHANT FIELD**: Il campo '{upload_file.merchant_column_name}' contiene informazioni sul commerciante/beneficiario.\n"
            if upload_file.date_column_name:
                csv_hints_section += f"📅 **DATE FIELD**: Il campo '{upload_file.date_column_name}' contiene la data della transazione.\n"
            if upload_file.income_amount_column_name or upload_file.expense_amount_column_name:
                csv_hints_section += f"💰 **AMOUNT FIELD**: Il campo '{upload_file.income_amount_column_name} oppure {upload_file.expense_amount_column_name}' contiene l'importo della transazione.\n"
            if upload_file.operation_type_column_name:
                csv_hints_section += f"🔄 **OPERATION TYPE FIELD**: Il campo '{upload_file.operation_type_column_name}' contiene il tipo di operazione.\n"
            if upload_file.notes:
                csv_hints_section += f"\n📌 **NOTE SULLA STRUTTURA CSV**:\n{upload_file.notes}\n"

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

            ⚠️ IMPORTANTE: Devi processare OGNI transazione che sia una SPESA. 
            Non saltare transazioni a meno che non siano esplicitamente vietate dalle regole sopra (Saldo o Accrediti).
            """

        # Format categories as "KEY": Description
        categories_formatted_list = []
        for cat in self.available_categories:
            if cat.name not in ['not_expense', 'Altro', 'altro']:
                if cat.description:
                    categories_formatted_list.append(f'  • "{cat.name}": {cat.description}')
                else:
                    categories_formatted_list.append(f'  • "{cat.name}"')

        categories_formatted = "\n".join(categories_formatted_list)

        return f"""Sei un assistente IA specializzato nella categorizzazione delle **spese** bancarie italiane.

    {csv_hints_section}

    {user_rules_section}

    {logic_constraints}

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

    ═══════════════════════════════════════════════════════
    ⚠️⚠️⚠️ ISTRUZIONI DI FORMATTAZIONE CATEGORIA ⚠️⚠️⚠️
    ═══════════════════════════════════════════════════════
    1. L'output per il campo "category" DEVE essere SOLO la stringa tra le virgolette.
    2. NON includere la descrizione che segue i due punti.
    3. NON includere trattini o testo esplicativo.

    Esempio Corretto:
    Input lista: "Trasporti": biglietti bus, treni
    Output JSON: "category": "Trasporti"

    Esempio SBAGLIATO (NON FARE QUESTO):
    Input lista: "Trasporti": biglietti bus, treni
    Output JSON: "category": "Trasporti - biglietti bus, treni"  <-- ERRORE GRAVE

    ═══════════════════════════════════════════════════════
    🚨🚨🚨 REGOLA ANTI-"Altro" - MASSIMA PRIORITÀ 🚨🚨🚨
    ═══════════════════════════════════════════════════════

    ⛔ LA CATEGORIA "Altro" È ASSOLUTAMENTE VIETATA.

    NON USARE MAI "Altro". DEVI scegliere una delle categorie fornite nella lista, senza alcuna eccezione.

    Checklist di analisi obbligatoria:
    1. Ho analizzato il nome del merchant cercando parole chiave di settore?
    2. Ho cercato di identificare il brand (es. CONAD, ENEL, BOOKING, NETFLIX)?
    3. Ho letto OGNI parola della descrizione cercando indizi?
    4. Ho considerato il tipo di operazione (SDD, POS, Bonifico)?
    5. Ho verificato se potrebbe essere un'abbreviazione di un settore noto?
    6. Ho confrontato con TUTTE le categorie disponibili una per una e scelto quella PIÙ PROBABILE?

    DEVI sforzarti di trovare la categoria più attinente. Se sei in dubbio, scegli quella che ritieni più vicina per tipologia di spesa.

    ═══════════════════════════════════════════════════════
    ESEMPI DI CATEGORIZZAZIONE CORRETTA (NON usare "Altro"):
    ═══════════════════════════════════════════════════════

    MERCHANT: "PIZZERIA DA MARIO"
    → CATEGORIA: "Vita sociale" (non "Altro")
    → REASONING: "Pizzeria è un esercizio di ristorazione italiano, chiaramente rientra in Vita sociale"

    MERCHANT: "FARMACIA COMUNALE"
    → CATEGORIA: "Spese mediche" (non "Altro")
    → REASONING: "Farmacia è un esercizio che vende medicinali e prodotti di salute, categoria Spese mediche"

    MERCHANT: "STAZIONE SERVIZIO Q8"
    → CATEGORIA: "Carburante" (non "Altro")
    → REASONING: "Stazione Servizio è un punto vendita di carburante, categoria Carburante"

    MERCHANT: "LIBRERIA FELTRINELLI"
    → CATEGORIA: "Shopping" (non "Altro")
    → REASONING: "Feltrinelli è una catena libraria italiana, rientra in Shopping/Libri"

    MERCHANT: "PALESTRA FITNESS WORLD"
    → CATEGORIA: "Sport" (non "Altro")
    → REASONING: "Palestra è una struttura per attività sportiva, categoria Sport"

    MERCHANT: "NETFLIX"
    → CATEGORIA: "Abbonamenti" (non "Altro")
    → REASONING: "Netflix è un servizio di streaming in abbonamento, categoria Abbonamenti"

    MERCHANT: "SPOTIFY"
    → CATEGORIA: "Abbonamenti" (non "Altro")
    → REASONING: "Spotify è un servizio di musica in abbonamento, categoria Abbonamenti"

    MERCHANT: "ENEL" o "ENI GAS"
    → CATEGORIA: "Bollette" (non "Altro")
    → REASONING: "ENEL e ENI sono fornitori di energia e gas italiano, addebiti SDD ricorrenti, categoria Bollette"

    MERCHANT: "CONAD" o "COOP"
    → CATEGORIA: "Spesa" (non "Altro")
    → REASONING: "CONAD e COOP sono catene di supermercati italiani, categoria Spesa/Alimentari"

    MERCHANT: "RYANAIR"
    → CATEGORIA: "Trasporti" (non "Altro")
    → REASONING: "Ryanair è una compagnia aerea, categoria Trasporti"

    MERCHANT: "BOOKING.COM"
    → CATEGORIA: "Vacanze" (non "Altro")
    → REASONING: "Booking.com è una piattaforma di prenotazione hotel e alloggi, categoria Vacanze"

    DESCRIPTION: "Addebito SDD H2O BOLOGNA SPA" (senza nome merchant chiaro)
    → CATEGORIA: "Bollette" (non "Altro")
    → REASONING: "H2O Bologna è la società di gestione dell'acqua di Bologna, addebito SDD ricorrente, categoria Bollette"

    DESCRIPTION: "Pagamento Mastercard presso DECATHLON ITALIA"
    → CATEGORIA: "Sport" (non "Altro")
    → REASONING: "Decathlon vende articoli sportivi, categoria Sport"

    ═══════════════════════════════════════════════════════
    ISTRUZIONI PRINCIPALI (ORDINE DI PRIORITÀ):
    ═══════════════════════════════════════════════════════

    1. CHECK USER RULES FIRST - FILTRA SALDI E ACCREDITI.
    2. Elabora TUTTE le transazioni rimanenti (SPESE).
    3. Per OGNI spesa, completa l'analisi approfondita della categorizzazione.
    4. Assegna la categoria più specifica e probabile tra quelle fornite (MAI "Altro").
    5. Estrai il nome del commerciante e tutti i campi obbligatori.
    6. Scrivi un "reasoning" dettagliato che giustifichi la scelta.

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
       • Estrai il nome pulito del commerciante.
       • Rimuovi SPA, SRL, S.p.A., e altri suffissi legali.
       • Se è un addebito SDD, estrai il nome dell'azienda creditrice.
       • Se non è chiaro, usa il nome più riconoscibile dalla descrizione.

    ┌─────────────────────────────────────────────────────┐
    │ 5. DESCRIPTION (DESCRIZIONE) (OBBLIGATORIO)         │
    └─────────────────────────────────────────────────────┘
       • Stringa originale della descrizione dalla transazione.

    ┌─────────────────────────────────────────────────────┐
    │ 6. REASONING (RAGIONAMENTO) (OBBLIGATORIO)          │
    └─────────────────────────────────────────────────────┘
       • Spiega in 1-2 frasi perché hai scelto questa categoria specifica tra quelle disponibili.
       • Menziona gli elementi chiave che hanno guidato la decisione (merchant, tipo operazione, descrizione, ed eventuali esempi simili dal passato).
       • Esempi di buon reasoning:
         * "Categoria Alimentari per merchant ESSELUNGA, supermercato italiano tra i più noti"
         * "Categoria Trasporti per pagamento biglietto bus ATM Milano, confermato da descrizione"
         * "Categoria Bollette per addebito SDD ricorrente da ENEL ENERGIA, provider energia italiano"
         * "Categoria Sport per acquisto presso DECATHLON, negozio articoli sportivi"
         * "Categoria scelta per coerenza con transazioni passate dell'utente per lo stesso merchant/descrizione"

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
        "reasoning": "Categoria Alimentari scelta per merchant ESSELUNGA, uno dei principali supermercati italiani. Addebito SDD ricorrente conferma acquisti regolari di generi alimentari.",
        "applied_user_rule": null,
        "failure": false
      }},
      {{
        "transaction_id": "1201",
        "date": "2025-10-15",
        "category": "Trasporti",
        "merchant": "RYANAIR",
        "amount": 89.50,
        "original_amount": "-89,50",
        "description": "Pagamento RYANAIR volo Roma Milano",
        "reasoning": "Categoria Trasporti per pagamento compagnia aerea Ryanair, confermate da descrizione 'volo Roma Milano'",
        "applied_user_rule": null,
        "failure": false
      }}
    ]

    ═══════════════════════════════════════════════════════
    TRANSAZIONI DA ANALIZZARE:
    ═══════════════════════════════════════════════════════
    {transactions_text}

    RISPONDI SOLO CON L'ARRAY JSON:"""

    def process_batch(self, batch: list[AgentTransactionUpload], upload_file: UploadFile) -> tuple[list[
        TransactionCategorization], GeminiResponse | None]:
        """
        Process a single batch through LLM and deserialize into structured objects.

        Args:
            batch: list of transactions with 'id' and raw data
            upload_file: UploadFile instance with column mappings and notes

        Returns:
            list[TransactionCategorization]: Array of categorization objects
        """
        try:
            logger.info(f"Analyzing batch with {len(batch)} transactions...")
            # Build prompt with CSV column hints
            prompt = self.build_batch_prompt(batch, upload_file)

            # Send to API using new SDK
            response = call_gemini_api(prompt, self.client)

            # Parse JSON array response
            categorizations_data = parse_json_array(response.text)

            # Deserialize into structured objects
            categorizations = [
                TransactionCategorization.from_dict(item)
                for item in categorizations_data
            ]

            # Log completion
            expense_count = len([c for c in categorizations if c.category != "not_expense"])
            logger.info(f"Analysis completed: {expense_count}/{len(batch)} expenses categorized")

            return categorizations, response

        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            raise e