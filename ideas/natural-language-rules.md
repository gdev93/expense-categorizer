# Future Ideas & Enhancements 💡

## Natural Language Rule Creation (v2.0)

### **Concept**
Allow users to create categorization rules using natural language instead of rigid function schemas.

### **User Experience Vision**
> "All Starbucks and Coffee Bean transactions should go to Food & Beverages, but only if they're over 5. Anything under 5 goes to Miscellaneous."

## Agent Processing & Rule Formulation

### 1. Vendor Scope
This rule set applies **only** to transactions from:
* **Starbucks**
* **Coffee Bean**

### 2. Compound Rule Structure

The categorization depends entirely on the transaction amount:

| Condition | Amount Range | Category Assignment |
| :--- | :--- | :--- |
| **Primary Rule** (Based on "over 5") | **$>\$5.00$** (e.g., $5.01) | **Food & Beverages** ☕ |
| **Secondary Rule** (Based on "under 5") | **$<\$5.00$** (e.g., $4.99) | **Miscellaneous** 🛍️ |

### 3. Edge Case Handling

* **Conflict:** The transaction amount of **exactly $\$5.00$** is an edge case that is *not* explicitly defined, as it is neither "over 5" nor "under 5."
* **Recommendation:** For unambiguous implementation, the business should decide whether $\le \$5.00$ or $\ge \$5.00$ should be the threshold.
    * **Common Interpretation (Assumed for implementation):** Transactions **$\le \$5.00$** are often grouped with the lower category (Miscellaneous) to simplify the logic:

| Amount | Assumed Category |
| :--- | :--- |
| $\le \$5.00$ | **Miscellaneous** |
| $>\$5.00$ | **Food & Beverages** |
### **Advanced Rule Scenarios**
- **Multi-merchant rules**: "All coffee shops (Starbucks, Dunkin, local cafes) → Food"
- **Conditional logic**: "Gas stations over $50 → Transportation, under $50 → Daily Expenses"  
- **Date-based rules**: "All restaurants in December → Holiday Dining"
- **Exclusion patterns**: "All fast food except McDonald's → Quick Meals"
- **Amount ranges**: "Grocery stores $100-300 → Weekly Shopping, over $300 → Bulk Shopping"
- **Frequency-based**: "Recurring monthly payments → Bills & Subscriptions"

### **Technical Architecture (Future)**
```python
# Complex rule structure
class SmartRule:
    merchants: List[str]          # ["STARBUCKS", "COFFEE BEAN"]  
    conditions: List[Condition]   # [AmountCondition(">", 5)]
    category: str                 # "Food & Beverages"
    priority: int                 # Rule precedence
    exceptions: List[str]         # Exclusion patterns
```

#### **Rule Hierarchy & Priorities**
- How do we handle conflicting rules created by different instructions?
- Should the agent be able to modify or delete existing rules?
- How do we represent rule precedence in natural language?