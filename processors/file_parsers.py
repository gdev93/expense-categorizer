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
        reader = csv.DictReader(io_string)
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
    Reads a bank transaction Excel file by dynamically detecting the header row
    using universal keywords, and cleans the resulting DataFrame.

    Keywords are read from the 'BANK_KEYWORDS' environment variable (comma-separated).

    Returns:
        List of dictionaries representing rows (same format as parse_csv_file)
    """
    # 1. Define Universal Keywords (Case-Insensitive)
    keyword_string = os.getenv('BANK_KEYWORDS', 'Importo,Valuta,Descrizione,Concetto,Movimento')

    # Clean the string and create the list of keywords
    UNIVERSAL_KEYWORDS = [
        kw.strip() for kw in keyword_string.split(',') if kw.strip()
    ]

    # Validate that we have keywords to search for
    if not UNIVERSAL_KEYWORDS:
        raise ValueError(
            "UNIVERSAL_KEYWORDS list is empty. Check the BANK_KEYWORDS environment variable or the default list.")

    # 2. Attempt to Load the first 30 rows without a header to start the search
    try:
        temp_df = pd.read_excel(file_path, header=None, nrows=30, engine='openpyxl')
    except Exception as e:
        raise IOError(f"Failed to read Excel file {file_path}. Error: {e}")

    # 3. Dynamically Find the Header Row Index
    header_index = -1
    for index, row in temp_df.iterrows():
        # Clean the row: drop NaNs, convert to string, and lowercase for robust search
        row_string = ' '.join(row.dropna().astype(str).tolist()).lower()

        # Check if any keyword is present in this row
        if any(keyword.lower() in row_string for keyword in UNIVERSAL_KEYWORDS):
            header_index = index
            logger.info(
                f"✅ Success: Header dynamically detected at row index: {header_index} using keywords: {UNIVERSAL_KEYWORDS}")
            break

    if header_index == -1:
        # If no header is found, raise an error to stop processing
        raise ValueError(f"Could not find the transaction header based on universal keywords: {UNIVERSAL_KEYWORDS}.")

    # 4. Load the Full Data using the Detected Header Index (without dtype=str)
    df = pd.read_excel(file_path, header=header_index, engine='openpyxl')

    # 5. Clean up the DataFrame

    # Drop any unwanted 'Unnamed' columns
    df = df.drop(columns=[col for col in df.columns if 'Unnamed:' in col], errors='ignore')

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # 6. Convert datetime columns to dd/mm/yyyy format and strip all values in one loop
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%d/%m/%Y')
        else:
            # Convert to string
            df[col] = df[col].astype(str)

        # Strip whitespace from all string values
        df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

    df = df.where(pd.notna(df))

    # 7. Convert DataFrame to list of dictionaries (same format as CSV parser)
    records: List[Dict[str, str]] = df.to_dict('records')  # type: ignore[assignment]
    return records