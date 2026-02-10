"""
File parsers for transaction uploads.
Handles CSV and Excel file parsing with automatic format detection,
header hunting, and smart footer cropping.
"""
import os
import logging
import io
import pandas as pd
from typing import List, Dict, Optional, Tuple
from django.db.models import Q
from api.models import FileStructureMetadata

logger = logging.getLogger(__name__)

class FileParserError(Exception):
    """Exception raised for file parsing errors"""
    pass

def parse_uploaded_file(file) -> List[Dict[str, str]]:
    """
    Main entry point. Automatically detects file type and runs the Smart Pipeline.
    """
    filename = file.name.lower()

    try:
        if filename.endswith(('.xlsx', '.xls')):
            return _process_file_smartly(file, is_excel=True)
        elif filename.endswith('.csv'):
            return _process_file_smartly(file, is_excel=False)
        else:
            raise FileParserError(f'Unsupported file type: {filename}')
    except Exception as e:
        logger.error(f"Parsing failed for {filename}: {str(e)}", exc_info=True)
        raise FileParserError(f"Error parsing file: {str(e)}")

def _process_file_smartly(file, is_excel: bool) -> List[Dict[str, str]]:
    """
    Unified pipeline for both CSV and Excel:
    1. Load 'Raw' Preview (first N rows)
    2. Header Hunting (Metadata Match -> Heuristic Fallback)
    3. Reload Full Data with correct Header
    4. Smart Cropping (Remove footers based on Date validity)
    5. Data Cleaning (JSON compliance)
    """
    # 1. LOAD PREVIEW (First 30 rows)
    # We need a seekable stream for pandas
    if hasattr(file, 'seek'):
        file.seek(0)

    try:
        if is_excel:
            # Load raw rows without header assumption
            df_preview = pd.read_excel(file, header=None, nrows=30)
            # Reset file pointer for full read later
            file.seek(0)
        else:
            # For CSV, try to detect separator
            content = file.read()
            if isinstance(content, bytes):
                # Attempt to decode common encodings
                try:
                    text_content = content.decode('utf-8-sig')
                except UnicodeDecodeError:
                    text_content = content.decode('latin-1')
            else:
                text_content = content

            # Use io.StringIO to create a file-like object for pandas
            preview_io = io.StringIO(text_content)

            # Try sniffing separator or default to auto
            try:
                sep = None # Pandas 'python' engine detects it automatically
                df_preview = pd.read_csv(preview_io, sep=sep, header=None, nrows=30, engine='python')
            except Exception:
                # Fallback for strict separators
                preview_io.seek(0)
                df_preview = pd.read_csv(preview_io, sep=';', header=None, nrows=30)

            # Prepare full file wrapper for later
            file_io = io.StringIO(text_content)

    except Exception as e:
        raise FileParserError(f"Failed to read file preview: {e}")

    # 2. HEADER HUNTING
    header_index, matched_metadata = _find_header_row(df_preview)

    # 3. RELOAD FULL DATA
    try:
        if is_excel:
            df = pd.read_excel(file, header=header_index)
        else:
            file_io.seek(0) # Reset buffer
            df = pd.read_csv(file_io, header=header_index, sep=None, engine='python')
    except Exception as e:
        raise FileParserError(f"Failed to load full data with header at row {header_index}: {e}")

    # Basic cleanup of column names
    df.columns = df.columns.astype(str).str.strip()
    df = df.drop(columns=[c for c in df.columns if 'Unnamed:' in c], errors='ignore')

    # 4. SMART CROPPING (The Magic Step)
    # Eliminate footers/disclaimers by checking Date column validity
    df = _crop_footer_smartly(df, matched_metadata)

    # 5. FINAL CELL CLEANING
    return _clean_dataframe_to_dict(df)


def _find_header_row(df_preview: pd.DataFrame) -> Tuple[int, Optional[FileStructureMetadata]]:
    """
    Identifies the header row index.
    Priority 1: Strict match with FileStructureMetadata in DB.
    Priority 2: Heuristic match using 'Universal Keywords'.
    """
    # Fetch relevant metadata to check against
    valid_metadata = FileStructureMetadata.objects.filter(
        date_column_name__isnull=False,
        description_column_name__isnull=False
    )

    # A. METADATA MATCHING STRATEGY
    for index, row in df_preview.iterrows():
        # Get clean list of values in this row
        row_values = [str(val).strip() for val in row.dropna().tolist() if str(val).strip()]
        if not row_values: continue

        row_values_set = set(row_values)

        for metadata in valid_metadata:
            required_cols = [
                metadata.date_column_name,
                metadata.description_column_name
            ]
            # Add amount columns if they exist in metadata
            if metadata.expense_amount_column_name: required_cols.append(metadata.expense_amount_column_name)
            if metadata.income_amount_column_name: required_cols.append(metadata.income_amount_column_name)

            # Check if ALL required columns are present in this row
            if all(col in row_values_set for col in required_cols):
                logger.info(f"✅ Header found at row {index} via Metadata: {metadata}")
                return index, metadata

    # B. HEURISTIC FALLBACK STRATEGY
    # Only if no DB metadata matched
    logger.info("⚠️ No Metadata match. Switching to Keyword Heuristic.")

    keywords = os.getenv('BANK_KEYWORDS', 'data,valuta,descrizione,importo,entrate,uscite,contabile').split(',')
    keywords = [k.strip().lower() for k in keywords if k.strip()]

    best_score = 0
    best_index = -1

    for index, row in df_preview.iterrows():
        row_values = [str(val).strip().lower() for val in row.dropna().tolist()]
        row_values = set([word for val in row_values for word in val.split()])
        # Count how many keywords appear in this row
        score = sum(1 for val in row_values if val in keywords)

        # We need at least 2 keywords to be confident (e.g. "Data" and "Importo")
        if score >= 2 and score > best_score:
            best_score = score
            best_index = index

    if best_index != -1:
        logger.info(f"✅ Header found at row {best_index} via Heuristic (Score: {best_score})")
        return best_index, None

    raise FileParserError("Could not detect a valid header row. Please check file format.")


def _crop_footer_smartly(df: pd.DataFrame, metadata: Optional[FileStructureMetadata]) -> pd.DataFrame:
    """
    Removes footer rows (totals, disclaimers, empty lines) by strictly validating the Date column.
    If a row does not have a valid date, it is NOT a transaction.
    """
    if df.empty:
        return df

    # 1. Identify the Date Column
    date_col = None

    if metadata and metadata.date_column_name in df.columns:
        date_col = metadata.date_column_name
    else:
        # Heuristic search for date column
        for col in df.columns:
            if 'data' in col.lower() or 'date' in col.lower():
                date_col = col
                break

    if not date_col:
        logger.warning("Could not identify Date column for smart cropping. Falling back to simple dropna.")
        return df.dropna(how='all')

    # 2. Coerce Invalid Dates to NaT (Not a Time)
    # errors='coerce' turns "Total", "Page 1", "Disclaimer" into NaT
    # dayfirst=True is crucial for EU formats
    try:
        # Create a boolean mask of valid rows
        valid_date_mask = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce').notna()

        original_count = len(df)
        df_clean = df[valid_date_mask].copy()
        cropped_count = original_count - len(df_clean)

        if cropped_count > 0:
            logger.info(f"✂️ Smart Crop: Removed {cropped_count} footer/noise rows based on invalid dates in '{date_col}'")

        return df_clean

    except Exception as e:
        logger.warning(f"Smart cropping failed: {e}. Returning original.")
        return df


def _clean_dataframe_to_dict(df: pd.DataFrame) -> List[Dict[str, str]]:
    """
    Final cleaning to ensure JSON compliance for Postgres.
    Converts NaNs to None, dates to strings, strips whitespace.
    """
    def clean_cell(x):
        if x is None: return None
        if pd.isna(x): return None # Handle NaN/NaT

        s = str(x).strip()
        if not s or s.lower() in ('nan', 'nat', 'none', 'null'):
            return None
        return s

    # Process columns
    for col in df.columns:
        # Format Timestamps explicitly if pandas recognized them
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%d/%m/%Y')

        # Apply strict cleaning
        df[col] = df[col].apply(clean_cell)

    # Remove rows that became completely empty after cleaning
    df = df.dropna(how='all')

    # Convert to list of dicts and ENSURE no NaNs are left (Postgres JSONField compatibility)
    records = df.to_dict('records')
    for record in records:
        for key, value in record.items():
            if pd.isna(value):
                record[key] = None

    return records