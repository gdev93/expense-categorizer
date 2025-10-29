import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from babel import numbers
from babel.numbers import NumberFormatError

default_date_formats = [
    '%d/%m/%Y',  # DD/MM/YYYY
    '%d-%m-%Y',  # DD-MM-YYYY
    '%d.%m.%Y',  # DD.MM.YYYY
    '%Y-%m-%d',  # YYYY-MM-DD
    '%Y/%m/%d',  # YYYY/MM/DD
    '%Y.%m.%d',  # YYYY.MM.DD
    '%m/%d/%Y',  # MM/DD/YYYY (US format)
    '%d/%m/%y',  # DD/MM/YY (2-digit year)
    '%d-%m-%y',  # DD-MM-YY
    '%Y%m%d',  # YYYYMMDD (compact)
]
date_formats = os.getenv('PARSE_DATE_FORMATS', default_date_formats)
default_amount_pattern = re.compile(
    r'[+-]?\s*'  # Optional sign with optional space
    r'(?:'
    r'\d{1,3}(?:\.\d{3})+,\d{2,}|'  # Italian with thousands: 1.234,56
    r'\d{1,3}(?:,\d{3})+\.\d{2,}|'  # US with thousands: 1,234.56
    r'\d+,\d{2,}|'  # Simple Italian: 4,42
    r'\d+\.\d{2,}|'  # Simple US: 4.42
    r'\d+'  # Whole numbers without decimals: 3000
    r')'
)
amount_pattern = os.getenv('PARSE_AMOUNT_PATTERN', default_amount_pattern)


def _parse_date(date_str: str) -> date:
    # Try common date formats
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y']:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return datetime.now().date()


def parse_amount_from_raw_data(raw_data: dict[str, str]) -> tuple[Decimal | None, str | None]:
    """
    Parse transaction amount from raw_data dictionary using smart regex matching.

    Handles various formats:
    - Italian format with comma as decimal separator: -4,42
    - International format with dot: -4.42
    - Optional signs: +/-
    - Thousands separators (dots or commas depending on context)

    Args:
        raw_data: Dictionary with transaction raw data

    Returns:
        tuple[Decimal, str] | None: Tuple of (parsed_amount, source_key) or None if not found

    Raises:
        ValueError: If no amount is found or amounts conflict
    """
    # Regex pattern to match decimal numbers with various formats
    # Order matters: match longer patterns (with thousands) before shorter ones
    # Matches: -4,42 | +4.42 | 1.234,56 | 1,234.56 | 4.42 | 4,42

    found_amounts = {}  # key -> (normalized_decimal, original_value)

    # Scan all values in the dictionary
    for key, value in raw_data.items():
        if not value.strip():
            continue
        matches = amount_pattern.findall(value)
        if matches:
            # Take the first match (usually the complete amount)
            single_match = matches[0]
            normalized = normalize_amount(single_match)
            found_amounts[key] = (normalized, value)

    if not found_amounts:
        return None, None

    # Check if all found amounts are the same
    unique_amounts = set(amount for amount, _ in found_amounts.values())

    if len(unique_amounts) == 1:
        # All amounts are the same, return any
        first_key = list(found_amounts.keys())[0]
        return found_amounts[first_key][0], first_key

    # Different amounts found, pick the one from the shortest value
    shortest_key = min(found_amounts.keys(), key=lambda k: len(found_amounts[k][1]))
    return found_amounts[shortest_key][0], shortest_key


def normalize_amount(amount_value: str | float) -> Decimal:
    """
        Parse amount to Decimal, handling various formats.
        """
    if isinstance(amount_value, float):
        return Decimal(amount_value)

    if isinstance(amount_value, str):
        # italian
        try:
            # Remove currency symbols and spaces
            cleaned = amount_value.replace('€', '').replace(' ', '').strip()
            return numbers.parse_decimal(cleaned, locale='it_IT')
        except (ValueError, NumberFormatError):
                return Decimal('0.00')

    return Decimal('0.00')


def parse_date_from_raw_data(raw_data: dict[str, str]) -> tuple[date | None, str | None]:
    """
    Parse transaction date from raw_data dictionary by splitting values into words.

    Handles various formats:
    - Italian format: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - International format: YYYY-MM-DD, YYYY/MM/DD
    - US format: MM/DD/YYYY

    Args:
        raw_data: Dictionary with transaction raw data

    Returns:
        tuple[date, str] | None: Tuple of (parsed_date, source_key) or None if not found
    """
    # Common word separators
    separators = [' ', ';', ',', '\t', '|', '\n']

    found_dates = []  # List of (date, key) tuples

    # Scan all values in the dictionary
    for key, value in raw_data.items():
        if not value.strip():
            continue

        # Split value into words using multiple separators
        words = _split_by_separators(value, separators)

        # Try to parse each word as a date
        for word in words:
            word = word.strip()
            if not word:
                continue

            parsed_date = _try_parse_date(word)
            if parsed_date:
                found_dates.append((parsed_date, key))

    if not found_dates:
        return None, None

    # Return the earliest date (minimum) with its key
    return min(found_dates, key=lambda x: x[0])


def _split_by_separators(text: str, separators: list[str]) -> list[str]:
    """
    Split text by multiple separators.

    Args:
        text: Text to split
        separators: List of separator characters

    Returns:
        list[str]: List of words
    """
    # Replace all separators with a single separator, then split
    result = text
    for sep in separators:
        result = result.replace(sep, '|||')

    return result.split('|||')


def _try_parse_date(word: str) -> date | None:
    """
    Try to parse a word as a date using various formats.

    Args:
        word: Word to parse as date

    Returns:
        date: Parsed date object, or None if parsing fails
    """
    # Common date formats to try

    for fmt in date_formats:
        try:
            parsed = datetime.strptime(word, fmt).date()
            return parsed
        except (ValueError, AttributeError):
            continue

    return None


def parse_description_from_raw_data(raw_data: list[str]) -> str:
    return max(raw_data, key=len)
