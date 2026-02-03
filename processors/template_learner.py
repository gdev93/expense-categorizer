import logging
import os
import re
from collections import Counter
from typing import Iterable

from api.models import Transaction


def _normalize_description(text: str) -> str:
    """
    Initial normalization: removes dates, times, and numeric noise.
    """
    if not text:
        return ""

    # 1. Remove dates (various formats)
    text = re.sub(r'\d{2,4}[/-]\d{2}[/-]\d{2,4}', ' ', text)

    # 2. Remove times
    text = re.sub(r'\d{1,2}:\d{2}(:\d{2})?', ' ', text)

    # 3. Remove amounts (e.g., 10.99 or 10,99)
    text = re.sub(r'\d+[.,]\d+', ' ', text)

    # 4. Remove PANs, masked cards or long IDs (10+ characters)
    text = re.sub(r'[a-zA-Z0-9\*xX]{10,}', ' ', text).strip()

    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)

    return text


class TemplateLearner:
    """
    Identifies 'noise' tokens specific to a file structure based on statistical frequency.
    Settings are controlled via environment variables.
    """

    min_sample_size = int(os.getenv('TEMPLATE_MIN_SAMPLE_SIZE', 150))
    frequency_threshold = float(os.getenv('TEMPLATE_FREQUENCY_THRESHOLD', 0.35))

    def find_template_words(self, transactions: Iterable[Transaction]) -> list[str]:
        """
        Analyzes categorized transactions to find recurring tokens
        that do not belong to the Merchant name.
        """
        word_counter = Counter()
        valid_transactions_count = 0

        for tx in transactions:
            if not tx.merchant or not tx.description:
                continue

            # A. Normalize and Tokenize Description
            clean_desc = _normalize_description(tx.description).lower()
            desc_tokens = set(clean_desc.split())

            # B. Tokenize Merchant Name
            merchant_tokens = set(tx.merchant.name.lower().split())

            # C. Subtraction (Residue = Description - Merchant)
            residue_tokens = desc_tokens - merchant_tokens

            # Filter out very short tokens
            filtered_residue = [word for word in residue_tokens if len(word) > 2]

            if filtered_residue:
                word_counter.update(filtered_residue)
                valid_transactions_count += 1

        # D. Sample size check
        if valid_transactions_count < self.min_sample_size:
            logging.info(f"TemplateLearner: Not enough data ({valid_transactions_count}/{self.min_sample_size})")
            return []

        # E. Frequency-based selection
        cutoff_limit = valid_transactions_count * self.frequency_threshold

        candidate_words = [
            word for word, count in word_counter.items()
            if count >= cutoff_limit
        ]

        return sorted(candidate_words)
