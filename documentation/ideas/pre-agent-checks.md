# Smart Transaction Pre-Categorization Logic (Final Implementation Guide) 🇮🇹

This document details the robust strategy for extracting core data and utilizing advanced database queries to categorize transactions, minimizing calls to the external expense categorization agent.

***

## Step 1: Data Extraction from `raw_data`

We use **key aliases** and **value heuristics** to reliably extract `transaction_date`, `amount`, and `description` from the non-standardized raw CSV data.

### Logic and Examples for Core Data Extraction

| Core Field | Strategy | Example `raw_data` Snippet | Extracted Value |
| :--- | :--- | :--- | :--- |
| **Date** | 1. Check for aliases (`DATA CONTABILE`, `DATA VALUTA`). 2. Use heuristics to parse `DD/MM/YYYY` formats. | **Key Alias Match:** `{"DATA CONTABILE": "14/10/2025"}` | `2025-10-14` (as a Date object) |
| **Amount** | 1. Check for aliases (`USCITE`, `IMPORTO`). 2. Find numeric values and convert the Italian decimal comma (`,`) to a dot (`.`). | **Key Alias Match:** `{"USCITE": "-4,42"}` | `-4.42` (as a Decimal object) |
| **Description** | 1. Check for aliases (`DESCRIZIONE OPERAZIONE`, `CAUSALE`). 2. Select the longest string value if no alias is found. | **Key Alias Match:** `{"DESCRIZIONE OPERAZIONE": "Op. Mastercard del... presso **ITALMARK ALBERTANO**"}` | `"Op. Mastercard del... presso ITALMARK ALBERTANO"` (Full string) |

***

## Step 2: Advanced Merchant Search & Categorization Flow

We use the full extracted `description` with a high-performance database query to find a matching merchant, using the match length as a proxy for confidence.

### A. Database Search Strategy

The query aims to find the **single merchant** with the **longest** `normalized_name` that is a substring of the transaction's full description. This length is the primary factor for assigning high confidence ($>0.95$).

**Strategy Summary:**

1.  Search the `Merchant` table where `Merchant.normalized_name` is **contained within** the transaction's description string (case-insensitive).
2.  Order the results by the **length** of the matching merchant name in descending order.
3.  Select the top result.

### B. Categorization Logic

The decision to call the agent is based on the quality of the match from the database.

| Condition | Merchant Match Result | Action | Agent Call? | Confidence Score |
| :--- | :--- | :--- | :--- | :--- |
| **1. HIGH CONFIDENCE Match** | Unique best merchant found (long `match_length`) **AND** it has a `default_category`. | Assign the found `merchant` and its default `category`. | **NO (Bypass)** | $1.0$ |
| **2. LOW CONFIDENCE Match** | Match found, but `match_length` is too short (e.g., $<5$ chars), or no default category exists. | **Call the Agent** to confirm/disambiguate. | **YES** | $0.0$ (Agent will set) |
| **3. NO Match** | The database query returned zero results. | **Call the Agent** to identify, create, and categorize the new merchant. | **YES (Required)** | $0.0$ (Agent will set) |

***

## Step 3: Actionable Scenarios

### Scenario 1: Existing Merchant Found (Agent AVOIDED)

SQL query example:
```sql
SELECT merchant_raw_name,
       description,
       -- Calculates similarity based on word overlap
       word_similarity(
               lower(merchant_raw_name),
               lower('5179090005496786 FISCOZEN* FISCOZEN MILANO IT')
       ) AS confidence_score
FROM api_transaction
WHERE status != 'pending'
  AND merchant_raw_name != ''
  and confidence_score > 0.95
ORDER BY confidence_score DESC
LIMIT 1;
```

A unique match with high confidence (e.g., `match_length` is 18) is found, and the merchant has a default category.

| Check | Result | Action |
| :--- | :--- | :--- |
| Merchant Search | **HIGH CONFIDENCE Match:** `merchant_match` found (`name='Italmark Albertano'`, single `default_category='Groceries'`). | Assign `merchant_match` and the default `category` to the transaction. Set status to `categorized`. |
| Agent Call | | **AVOIDED** |
| **Transaction State** | | `merchant=Italmark Albertano`, `category=Groceries`, `status=categorized`, `confidence_score=1.0` |

### Scenario 2: New Merchant OR Low Confidence (Agent REQUIRED)

No match, or a generic match with low confidence is found (e.g., only "BAR" is matched).

| Check | Result | Action |
| :--- | :--- | :--- |
| Merchant Search | **NO Match** **OR** **LOW CONFIDENCE Match** (e.g., match length $<5$). | **Call the Categorization Agent** (with `raw_data` and extracted `description`). |
| Agent Call | | **REQUIRED** |
| Agent Task | | The agent will: 1. Confirm/Identify the merchant name. 2. Determine the category. 3. **Create a new `Merchant`** entry. 4. Return the IDs and set the confidence score. |
| **Transaction State** | | `merchant=Nuovo Caffè Roma`, `category=Restaurants & Bars`, `status=categorized`, `confidence_score=0.9` (Agent's confidence) |