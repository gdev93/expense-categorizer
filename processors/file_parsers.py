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
from django.db.models import Q

from api.models import FileStructureMetadata

logger = logging.getLogger(__name__)


FILE_STRUCTURE_METADATA_BATCH_SIZE = 50

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
        raise FileParserError(f'Errore durante l\'analisi del file Excel: {str(e)}')


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
        raise FileParserError(f'Errore durante l\'analisi del file CSV: {str(e)}')


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
        raise FileParserError(f'Tipo di file non supportato: {filename}')


def read_excel(file_path) -> List[Dict[str, str]]:
    """
    Reads a bank transaction Excel file, detecting the header dynamically,
    and cleans the data to be strictly JSON-compliant for Postgres.

    Header detection priority:
    1. FileStructureMetadata - checks if row columns match stored metadata columns
    2. Universal keywords - fallback if no metadata match found
    """
    # 1. Define Universal Keywords (for fallback only)
    keyword_string = os.getenv('BANK_KEYWORDS', 'Importo,Valuta,Descrizione,Concetto,Movimento')
    UNIVERSAL_KEYWORDS = [kw.strip() for kw in keyword_string.split(',') if kw.strip()]

    if not UNIVERSAL_KEYWORDS:
        raise ValueError("UNIVERSAL_KEYWORDS list is empty.")

    # 2. Load first 30 rows to find header
    try:
        temp_df = pd.read_excel(file_path, header=None, nrows=30, engine='openpyxl')
    except Exception as e:
        raise IOError(f"Impossibile leggere il file Excel {file_path}. Errore: {e}")

    # 3. Fetch all FileStructureMetadata records that have required columns
    valid_metadata = FileStructureMetadata.objects.filter(
        date_column_name__isnull=False,
        description_column_name__isnull=False
    ).filter(
        Q(income_amount_column_name__isnull=False) | Q(expense_amount_column_name__isnull=False)
    )

    logger.info(f"Found {valid_metadata.count()} valid FileStructureMetadata records to check")

    # 4. Try to find header using FileStructureMetadata
    header_index = -1
    matched_metadata = None

    for index, row in temp_df.iterrows():
        # Get potential column names from this row
        potential_columns = [str(val).strip() for val in row.dropna().tolist() if str(val).strip()]

        if not potential_columns:
            continue

        # Convert to set for faster lookups
        potential_columns_set = set(potential_columns)

        # Check against each metadata record
        for metadata in valid_metadata:
            # Collect required columns from metadata
            required_columns = []

            if metadata.date_column_name:
                required_columns.append(metadata.date_column_name)
            if metadata.description_column_name:
                required_columns.append(metadata.description_column_name)
            if metadata.expense_amount_column_name:
                required_columns.append(metadata.expense_amount_column_name)
            if metadata.income_amount_column_name:
                required_columns.append(metadata.income_amount_column_name)

            # Check if all required columns are present in the row
            if all(col in potential_columns_set for col in required_columns):
                header_index = index
                matched_metadata = metadata
                logger.info(f"✅ Header detected via FileStructureMetadata at row {header_index}")
                logger.info(f"   Date: {metadata.date_column_name}, "
                            f"Description: {metadata.description_column_name}, "
                            f"Income: {metadata.income_amount_column_name}, "
                            f"Expense: {metadata.expense_amount_column_name}")
                break

        if header_index != -1:
            break

    # 5. Fallback to keyword matching if no metadata match
    if header_index == -1:
        logger.info("⚠️  No FileStructureMetadata match found, falling back to keyword matching")
        for index, row in temp_df.iterrows():
            row_string = ' '.join(row.dropna().astype(str).tolist()).lower()
            if any(keyword.lower() in row_string for keyword in UNIVERSAL_KEYWORDS):
                header_index = index
                logger.info(f"✅ Header detected via keywords at row: {header_index}")
                break

    if header_index == -1:
        raise ValueError(f"Impossibile trovare l'intestazione con FileStructureMetadata o parole chiave: {UNIVERSAL_KEYWORDS}")

    # 6. Load Full Data
    df = pd.read_excel(file_path, header=header_index, engine='openpyxl')

    # 7. Drop Unnamed columns and whitespace from headers
    df = df.drop(columns=[col for col in df.columns if 'Unnamed:' in col], errors='ignore')
    df.columns = df.columns.str.strip()

    # 8. ROBUST CLEANING (Fixes the JSON/Postgres Error)
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

    # 9. Convert to Dictionary
    records: List[Dict[str, str]] = df.to_dict('records')  # type: ignore[assignment]
    return records