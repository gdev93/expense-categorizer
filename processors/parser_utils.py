import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

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

# Common word separators
separators = [' ', ';', ',', '\t', '|', '\n']
def parse_amount_from_raw_data(raw_data: dict[str, str], csv_amount_columns:list[str]) -> tuple[Decimal | None, str | None]:

    # Regex pattern to match decimal numbers with various formats
    # Order matters: match longer patterns (with thousands) before shorter ones
    # Matches: -4,42 | +4.42 | 1.234,56 | 1,234.56 | 4.42 | 4,42

    # Scan all values in the dictionary
    for column_name in csv_amount_columns:
        if column_name not in raw_data:
            continue
        return normalize_amount(raw_data[column_name]), column_name

    return None, None

    # Check if all found amounts are the same


def normalize_amount(amount_value: str | float | int) -> Decimal | None:
    """
    Parse amount to Decimal, handling various formats including Italian locale.
    Supports both Italian (comma as decimal) and international (dot as decimal) formats.
    """
    # 1. Handle numeric types directly
    if isinstance(amount_value, (float, int)):
        # Convert float to string first to maintain precision before Decimal conversion
        if isinstance(amount_value, float):
            return Decimal(str(amount_value))
        return Decimal(amount_value)

    if isinstance(amount_value, str):
        # 2. Cleanup
        # Remove currency symbols and spaces first.
        cleaned = amount_value.replace('€', '').replace('$', '').replace(' ', '').strip()

        if not cleaned or cleaned.lower() in ('nan', 'none'):
            return None

        # 3. Standardize Format
        if ',' in cleaned and '.' in cleaned:
            # Case 1: Both comma and dot present (e.g., 1.234,56 or 1,234.56)

            # **ITALIAN/EUROPEAN HEURISTIC:** Assume the last separator is the decimal point.
            if cleaned.rfind(',') > cleaned.rfind('.'):
                # Input is Italian: dot is thousands separator, comma is decimal
                # Example: "1.234,56" -> remove dots, replace comma with dot -> "1234.56"
                standardized = cleaned.replace('.', '').replace(',', '.')
            else:
                # Input is International: comma is thousands separator, dot is decimal
                # Example: "1,234.56" -> remove commas -> "1234.56"
                standardized = cleaned.replace(',', '')

        elif ',' in cleaned:
            # Case 2: Only comma present (e.g., 1234,56)
            # Assume Italian/European decimal separator
            standardized = cleaned.replace(',', '.')

        else:
            # Case 3: Only dot, or no separators (e.g., 1234.56 or 1234)
            # Assume International decimal separator
            standardized = cleaned

        # 4. Attempt final conversion to Decimal
        try:
            return Decimal(standardized)
        except InvalidOperation:
            # Catches malformed strings like "1.2.3,45" after standardization
            raise ValueError(f"Invalid amount format: {amount_value}")

    raise ValueError(f"Invalid amount type: {type(amount_value)}")

def parse_date_from_raw_data(raw_data: dict[str, str], csv_date_columns:list[str]) -> tuple[date | None, str | None]:

    # Scan all values in the dictionary
    for csv_date_column in csv_date_columns:
        if csv_date_column not in raw_data:
            continue
        value = raw_data.get(csv_date_column)
        # Split value into words using multiple separators
        words = _split_by_separators(value, separators)

        # Try to parse each word as a date
        for word in words:
            word = word.strip()
            if not word:
                continue

            parsed_date = _try_parse_date(word)
            if parsed_date:
                return parsed_date, csv_date_column
    return None, None


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


def parse_unstructured_text(raw_data: dict[str,str], column_names:list[str]) -> tuple[str | None, str | None]:
    for column_name in column_names:
        if column_name in raw_data:
            return raw_data[column_name], column_name
    return None, None


def parse_date_from_raw_data_with_no_suggestions(raw_data: dict[str, str]) -> tuple[date | None, str | None]:
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


    found_dates = []  # List of (date, key) tuples

    # Scan all values in the dictionary
    for key, value in raw_data.items():
        if not value.strip():
            continue
        parsed_date = parse_raw_date(value)
        found_dates.append((parsed_date, key))


    if not found_dates:
        return None, None

    return max(found_dates, key=lambda x: x[0])

def parse_raw_date(raw_date:str) -> date | None:
    # Split value into words using multiple separators
    words = _split_by_separators(raw_date, separators)

    # Try to parse each word as a date
    for word in words:
        word = word.strip()
        if not word:
            continue

        parsed_date = _try_parse_date(word)
        if parsed_date:
            return parsed_date
    return None


from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class ParsedField:
    """Represents a parsed field with its numeric and original string values"""
    amount: Decimal
    original_value: str

    def __str__(self) -> str:
        return self.original_value


@dataclass
class ParsedAmountRawData:
    """Structured representation of raw transaction data with parsed fields"""
    fields: dict[str, ParsedField]

    def is_valid(self) -> bool:
        return len(self.fields) > 0

    @classmethod
    def from_raw_dict(cls, raw_data: dict[str, tuple[Decimal, str]]) -> 'ParsedAmountRawData':
        """
        Create ParsedRawData from a dictionary of tuples.

        Args:
            raw_data: Dictionary where values are tuples of (Decimal, str)

        Returns:
            ParsedRawData instance
        """
        fields = {}
        for key, (amount, original) in raw_data.items():
            fields[key] = ParsedField(amount=amount, original_value=original)
        return cls(fields=fields)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Convert to a plain dictionary representation"""
        return {
            key: {
                'amount': field.amount,
                'original_value': field.original_value
            }
            for key, field in self.fields.items()
        }


def parse_amount_from_raw_data_without_suggestion(raw_data: dict[str, str]) -> ParsedAmountRawData:
    """
    Parse transaction data from raw_data dictionary using smart regex matching.

    Handles various formats:
    - Italian format with comma as decimal separator: -4,42
    - International format with dot: -4.42
    - Optional signs: +/-
    - Thousands separators (dots or commas depending on context)

    Args:
        raw_data: Dictionary with transaction raw data (string values)

    Returns:
        ParsedAmountRawData: Structured object containing parsed fields with amounts and original values
    """
    parsed_fields = {}

    # Scan all values in the dictionary
    for key, value in raw_data.items():
        if not value or not value.strip():
            continue

        matches = amount_pattern.findall(value)
        if matches:
            # Take the first match (usually the complete amount)
            single_match = matches[0]
            normalized = normalize_amount(single_match)
            parsed_fields[key] = ParsedField(
                amount=normalized,
                original_value=value
            )

    return ParsedAmountRawData(fields=parsed_fields)