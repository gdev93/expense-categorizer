# Claude.md — Product Requirements & Architecture (Synthetic)

## Objective
- Automate expense categorization from natural-language instructions with accuracy-first behavior, low LLM cost, and clear UX.
- Start with CSV uploads; evolve to Open Banking later.
- Semantic batching: default categories, user categories, merchant and categories computed on-the-go. It is possible to leverage vector search, similarity queries to query the transaction first. We can use very high threshold for similarity and then use LLM for unknown transactions.
---
## Scope (v1)
- Input: CSV upload; LLM-assisted column detection with manual correction fallback.
- Processing: Adaptive async pipeline (sample → learn → scale) with semantic batching.
- Actions: Create categories, add keyword rules, apply rules to transactions.
- Validation: Strict agent constraints + API validation.
---
## Non-Goals (v1)
- Complex conditional rules, date-based logic, exclusions. (See [natural-language-rules.md](ideas/natural-language-rules.md) for v2.)
---
## User Experience
- Single CSV upload per user at a time.
- Progress displayed during async processing; user reviews results and can correct.
- Cache-first categorization to minimize cost and latency.
---
## System Overview
- Tech: Python, FastAPI, DB (PostgreSQL or MongoDB).
- Layers:
  - Base Backend (CRUD): categories, rules, transactions.
  - LLM Agent (Interpreter): maps NL instructions to structured function calls.
---
## Data Flow
1) CSV Upload → Column Detection (LLM) → Smart Batching by semantic similarity.
2) Adaptive Processing: sample subset → learn mappings → apply at scale.
3) User Review → Manual corrections → Cache patterns for future similarity.
---
## APIs / Tools (exposed to Agent)
- POST /api/v1/categories → createCategory(name: str)
- POST /api/v1/rules → addKeywordRule(keyword: str, category_name: str)
- PUT  /api/v1/transactions/batch → applyRuleToTransactions(keyword: str, category_name: str)
- POST /agent/process_instruction → agent entrypoint

## Agent Invocation & Execution (FastAPI pseudo-code)
```python
@app.post("/agent/process_instruction")
async def process_instruction(data: AgentInput):
    llm_output = llm_model.generate_function_call(
        instruction=data.user_instruction,
        available_tools=[createCategory, addKeywordRule, applyRuleToTransactions]
    )
    function_name = llm_output.function_call.name
    function_args = llm_output.function_call.args

    if function_name == 'addKeywordRule':
        await addKeywordRule(function_args['keyword'], function_args['category_name'])
        return {"status": "success", "message": f"Rule created for {function_args['keyword']}."}
    # ... handle other functions ...
```
---
## Processing Strategy
- Priority: Accuracy and simplicity over raw speed.
- Batching: Group by semantic similarity to preserve context.
- Concurrency: One CSV per user (serial); natural rate limiting via cache.
---
## Caching & Rate Limiting (Fuzzy Similarity)
- Normalize merchant names; reuse categories when similarity ≥ 0.8.
- Only call LLM for new patterns.
```python
from difflib import SequenceMatcher
from typing import Optional, Dict

class TransactionCache:
    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
        self.cache: Dict[str, str] = {}  # merchant -> category

    def normalize_merchant(self, merchant: str) -> str:
        return merchant.upper().strip().replace("  ", " ")

    def calculate_similarity(self, text1: str, text2: str) -> float:
        return SequenceMatcher(None, text1, text2).ratio()

    def find_similar_merchant(self, merchant: str) -> Optional[str]:
        normalized_merchant = self.normalize_merchant(merchant)
        best_match, best_score = None, 0.0
        for cached_merchant in self.cache.keys():
            score = self.calculate_similarity(normalized_merchant, cached_merchant)
            if score > best_score and score >= self.similarity_threshold:
                best_score, best_match = score, cached_merchant
        return best_match

    def get_cached_category(self, merchant: str) -> Optional[str]:
        similar_merchant = self.find_similar_merchant(merchant)
        return self.cache[similar_merchant] if similar_merchant else None

    def store_categorization(self, merchant: str, category: str):
        self.cache[self.normalize_merchant(merchant)] = category

# Usage
cache = TransactionCache(0.8)
cache.store_categorization("STARBUCKS #1234", "Food & Beverages")
cache.get_cached_category("STARBUCKS #5678")  # -> "Food & Beverages"
```
---
## Agent Constraints (Prompt Skeleton)
- Use existing categories; may create at most 2 generic, widely applicable new ones only if necessary.
- Merchant matching must use provided merchant options with fuzzy matching.
- Validation rules: non-empty merchant/category; choose closest existing if unsure; ask clarification otherwise.
```python
def generate_agent_prompt(available_categories: List[str], merchant_options: List[str]) -> str:
    return f"""
You are an expense categorization assistant. Follow these STRICT rules:

CATEGORY CONSTRAINTS:
- Use ONLY these categories: {available_categories}
- You MAY create up to 2 new generic categories only if none fit.

FORBIDDEN:
- Overly specific categories (e.g., "Premium Coffee").

ALLOWED NEW EXAMPLES:
- "Entertainment", "Healthcare", "Education" when justified.

MERCHANT CONSTRAINTS:
- Available merchants: {merchant_options[:50]}...
- MUST match merchants from this list using fuzzy matching.

VALIDATION:
- Every result needs non-empty merchant and category.
- If unsure, pick the closest existing category; otherwise ask for clarification.
"""
```
---
## API-Level Validation (Backend)
```python
def batch_categorize_merchants(categorizations: List[Dict[str, str]]):
    results, errors = [], []
    for item in categorizations:
        if not item["category"] in valid_categories:
            errors.append(f"Invalid category: {item['category']} for {item['merchant']}")
        else:
            results.append(item)
    return {"success": results, "errors": errors}
```
---
## Error Handling & Recovery
- Manual feedback loop for edge cases; corrections update cache.
- Retries limited; prefer human-in-the-loop over blind retries.

## Telemetry & Progress
- Async job status updates; track LLM calls, cache hit-rate, error rates.

## Security & Limits
- Rate limit by user; store minimal PII; log redaction for descriptions where applicable.

## Evolution (post-v1)
- Open Banking ingestion; richer natural-language rule creation (multi-merchant, thresholds, dates). Refer to [natural-language-rules.md](ideas/natural-language-rules.md).
