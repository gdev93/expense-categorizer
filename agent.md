# Expense Categorization Agent

An intelligent expense categorization system that uses AI to automatically organize your financial transactions based on natural language instructions.

## What It Does

The agent automates the tedious task of categorizing expenses by understanding natural language commands like:
- "Categorize all Starbucks transactions as Food & Beverages"
- "Create a new category called Transportation"
- "Apply the Groceries category to all Walmart purchases"

## Key Features

### Smart Processing
- Uploads CSV files containing transaction data
- Automatically detects which columns contain relevant information (merchant names, amounts, dates)
- Groups similar transactions together for efficient processing

### Intelligent Caching
- Remembers previous categorizations to avoid redundant AI calls
- Uses fuzzy matching to recognize merchant name variations (e.g., "STARBUCKS #1234" and "STARBUCKS #5678" are treated as the same merchant)
- Reduces costs and improves speed with a cache-first approach

### Accuracy-First Design
- Strict validation rules prevent the agent from creating overly specific or inappropriate categories
- Prefers using existing categories over creating new ones
- Falls back to human review when uncertain

### Cost-Effective
- Only calls the AI for truly new patterns
- Semantic batching groups similar transactions to minimize API calls
- High similarity threshold (≥80%) ensures cached results are reused whenever appropriate

## How It Works

1. **Upload**: You upload a CSV file with your transactions
2. **Detection**: The system identifies the relevant columns (merchant, amount, date, etc.)
3. **Instruction**: You provide natural language instructions for categorization
4. **Processing**: The agent processes transactions in smart batches, learning patterns as it goes
5. **Review**: You review the results and can make manual corrections
6. **Learning**: Corrections are cached for future similar transactions

## Current Capabilities (v1)

- CSV file upload and processing
- Natural language instruction interpretation
- Category creation and management
- Keyword-based rule creation
- Batch transaction categorization
- Fuzzy merchant name matching
- Intelligent caching and pattern recognition

## Technical Approach

The system uses a two-layer architecture:
- **Base Backend**: Handles CRUD operations for categories, rules, and transactions
- **LLM Agent**: Interprets natural language instructions and converts them into structured function calls

The agent has access to specific tools:
- `createCategory`: Creates new expense categories
- `addKeywordRule`: Defines keyword-to-category mappings
- `applyRuleToTransactions`: Applies categorization rules in bulk

Built with Python and FastAPI, designed for accuracy and low operational cost.

## Future Evolution

Post-v1 features will include:
- Open Banking integration for automatic transaction ingestion
- Richer natural-language rule creation (multi-merchant conditions, amount thresholds, date-based logic)
- Advanced rule patterns with exclusions and complex conditionals