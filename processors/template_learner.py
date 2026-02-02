import re
from typing import Iterable

from api.models import Transaction, FileStructureMetadata


def _normalize_description(text) -> str:
    """
    Uses regex to remove dates, times, and long numeric IDs from the description.
    """
    if not text:
        return ""

    # Remove dates (DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD, etc.)
    text = re.sub(r'\d{2,4}[/-]\d{2}[/-]\d{2,4}', ' ', text)

    # Remove times (HH:MM:SS, HH:MM)
    text = re.sub(r'\d{2}:\d{2}(:\d{2})?', ' ', text)

    # Remove long numeric IDs (typically 8+ digits)
    text = re.sub(r'\d{8,}', ' ', text)

    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text).strip()

    return text


class TemplateLearner:
    """
    Identifies 'noise' words in transaction descriptions that appear frequently
    for a specific file structure.
    """

    def find_template_words(self, transactions: Iterable[Transaction]) -> list[str]:
        """
        Fetches categorized transactions for the file structure, counts word frequencies,
        and identifies candidate blacklist words.
        """
        # 1. Fetch transactions that match this structure and have been categorized (as they are more reliable)
        # We find transactions associated with UploadFiles that match this structure's row_hash
        if not any(transactions):
            return []

        # PLACEHOLDER FOR CORE LOGIC
        # In a real implementation, we would:
        # 1. Tokenize and normalize descriptions
        # 2. Count word frequencies
        # 3. Filter words that appear in more than `threshold` * `count` transactions

        # Scaffolding returns an empty list or some dummy candidates as placeholder
        candidate_words = []

        return candidate_words
