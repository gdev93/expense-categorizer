"""
File parsers for transaction uploads.
Handles CSV and Excel file parsing with automatic format detection.
"""
import csv
import io
import os
import logging
from typing import List, Dict
import pandas as pd

logger = logging.getLogger(__name__)


class FileParserError(Exception):
    """Exception raised for file parsing errors"""
    pass


def parse_excel_file(file) -> List[Dict[str, str]]:
    """
    Parse Excel file and return list of row dictionaries.
    Uses the transaction_view.py logic to dynamically detect header.

    Args:
        file: Uploaded Excel file

    Returns:
        List of dictionaries representing rows

    Raises:
        FileParserError: If parsing fails
    """
    try:
        # Save uploaded file temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            for chunk in file.chunks():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        try:
            # Use the universal reader function
            csv_data = read_excel(tmp_path)

            # Convert DataFrame to list of dictionaries
            return csv_data
        finally:
            # Clean up temp file
            os.unlink(tmp_path)

    except Exception as e:
        raise FileParserError(f'Error parsing Excel file: {str(e)}')


def parse_csv_file(file) -> List[Dict[str, str]]:
    """
    Parse CSV file and return list of row dictionaries.

    Args:
        file: Uploaded CSV file

    Returns:
        List of dictionaries representing rows

    Raises:
        FileParserError: If parsing fails
    """
    try:
        file.seek(0)
        decoded_file = file.read().decode('utf-8-sig')
        io_string = io.StringIO(decoded_file)
        dialect = csv.Sniffer().sniff(decoded_file)
        reader = csv.DictReader(io_string, dialect=dialect)
        return list(reader)
    except Exception as e:
        raise FileParserError(f'Error parsing CSV file: {str(e)}')


def parse_uploaded_file(file) -> List[Dict[str, str]]:
    """
    Parse uploaded file (CSV or Excel) and return list of row dictionaries.
    Automatically detects file type based on extension.

    Args:
        file: Uploaded file (CSV or Excel)

    Returns:
        List of dictionaries representing rows

    Raises:
        FileParserError: If parsing fails or unsupported file type
    """
    filename = file.name.lower()

    if filename.endswith('.csv'):
        return parse_csv_file(file)
    elif filename.endswith(('.xlsx', '.xls')):
        return parse_excel_file(file)
    else:
        raise FileParserError(f'Unsupported file type: {filename}')


def read_excel(file_path) -> List[Dict[str, str]]:
    """
    Reads a bank transaction Excel file, detecting the header dynamically,
    and cleans the data to be strictly JSON-compliant for Postgres.
    """
    # 1. Define Universal Keywords
    keyword_string = os.getenv('BANK_KEYWORDS', 'Importo,Valuta,Descrizione,Concetto,Movimento')
    UNIVERSAL_KEYWORDS = [kw.strip() for kw in keyword_string.split(',') if kw.strip()]

    if not UNIVERSAL_KEYWORDS:
        raise ValueError("UNIVERSAL_KEYWORDS list is empty.")

    # 2. Load first 30 rows to find header
    try:
        temp_df = pd.read_excel(file_path, header=None, nrows=30, engine='openpyxl')
    except Exception as e:
        raise IOError(f"Failed to read Excel file {file_path}. Error: {e}")

    # 3. Dynamically Find Header Row
    header_index = -1
    for index, row in temp_df.iterrows():
        row_string = ' '.join(row.dropna().astype(str).tolist()).lower()
        if any(keyword.lower() in row_string for keyword in UNIVERSAL_KEYWORDS):
            header_index = index
            logger.info(f"✅ Header detected at row: {header_index}")
            break

    if header_index == -1:
        raise ValueError(f"Could not find header with keywords: {UNIVERSAL_KEYWORDS}")

    # 4. Load Full Data
    df = pd.read_excel(file_path, header=header_index, engine='openpyxl')

    # 5. Drop Unnamed columns and whitespace from headers
    df = df.drop(columns=[col for col in df.columns if 'Unnamed:' in col], errors='ignore')
    df.columns = df.columns.str.strip()

    # ---------------------------------------------------------
    # 6. ROBUST CLEANING (Fixes the JSON/Postgres Error)
    # ---------------------------------------------------------

    # Helper function to clean individual cells
    def clean_cell(x):
        # If it is strictly None, return None
        if x is None:
            return None

        # If it is a float/numpy NaN, return None
        if pd.isna(x):
            return None

        # Convert to string and strip whitespace
        s = str(x).strip()

        # Check for empty strings or artifacts like "nan", "NaT"
        if not s or s.lower() in ('nan', 'nat', 'none'):
            return None

        return s

    for col in df.columns:
        # Handle Date Columns specifically before string conversion
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            # Format valid dates; NaT (Not a Time) will remain NaT or become NaN
            df[col] = df[col].dt.strftime('%d/%m/%Y')

        # Apply the cleaner to every cell in the column
        df[col] = df[col].apply(clean_cell)

    # 7. Convert to Dictionary
    records: List[Dict[str, str]] = df.to_dict('records')  # type: ignore[assignment]
    return records