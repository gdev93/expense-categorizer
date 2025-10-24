
from datetime import date

from processors.parser_utils import parse_date_from_raw_data


class TestParseDateFromRawData:
    """Test suite for parse_date_from_raw_data function."""

    def test_italian_format_with_slash(self):
        """Test Italian date format with slash (DD/MM/YYYY)."""
        raw_data = {"DATA CONTABILE": "14/10/2025"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DATA CONTABILE"

    def test_italian_format_with_dash(self):
        """Test Italian date format with dash (DD-MM-YYYY)."""
        raw_data = {"DATE": "14-10-2025"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DATE"

    def test_italian_format_with_dot(self):
        """Test Italian date format with dot (DD.MM.YYYY)."""
        raw_data = {"DATE": "14.10.2025"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DATE"

    def test_iso_format_with_dash(self):
        """Test ISO date format (YYYY-MM-DD)."""
        raw_data = {"DATE": "2025-10-14"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DATE"

    def test_iso_format_with_slash(self):
        """Test ISO date format with slash (YYYY/MM/DD)."""
        raw_data = {"DATE": "2025/10/14"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DATE"

    def test_compact_format(self):
        """Test compact date format (YYYYMMDD)."""
        raw_data = {"DATE": "20251014"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DATE"

    def test_two_digit_year(self):
        """Test date with 2-digit year."""
        raw_data = {"DATE": "14/10/25"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DATE"

    def test_date_with_space_separator(self):
        """Test extracting date from space-separated text."""
        raw_data = {
            "DESCRIZIONE": "Op. Mastercard del 14/10/2025 presso ITALMARK"
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "DESCRIZIONE"

    def test_date_with_semicolon_separator(self):
        """Test extracting date with semicolon separator."""
        raw_data = {"FIELD": "Transaction;14/10/2025;completed"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "FIELD"

    def test_date_with_comma_separator(self):
        """Test extracting date with comma separator."""
        raw_data = {"FIELD": "Payment,14/10/2025,confirmed"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "FIELD"

    def test_date_with_pipe_separator(self):
        """Test extracting date with pipe separator."""
        raw_data = {"FIELD": "ID123|14/10/2025|Status"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "FIELD"

    def test_multiple_same_dates(self):
        """Test when same date appears in multiple values."""
        raw_data = {
            "DATA CONTABILE": "14/10/2025",
            "DATA VALUTA": "14/10/2025",
            "DESCRIZIONE": "Transaction 14/10/2025"
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key in ["DATA CONTABILE", "DATA VALUTA", "DESCRIZIONE"]

    def test_multiple_different_dates_returns_min(self):
        """Test when different dates are found, returns the earliest."""
        raw_data = {
            "FIELD1": "20/10/2025",
            "FIELD2": "15/10/2025",
            "FIELD3": "10/10/2025"  # Earliest
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 10)
        assert key == "FIELD3"

    def test_mixed_date_formats(self):
        """Test with mixed date formats in different fields."""
        raw_data = {
            "DATE1": "2025-10-20",  # ISO format
            "DATE2": "15/10/2025",  # Italian format
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 15)  # Earlier date
        assert key == "DATE2"

    def test_no_date_returns_none(self):
        """Test that None is returned when no date is found."""
        raw_data = {"DESCRIZIONE": "Payment at store", "AMOUNT": "100.50"}
        result = parse_date_from_raw_data(raw_data)
        assert result is None

    def test_empty_dictionary_returns_none(self):
        """Test that None is returned for empty dictionary."""
        raw_data = {}
        result = parse_date_from_raw_data(raw_data)
        assert result is None

    def test_empty_values_returns_none(self):
        """Test that None is returned when all values are empty."""
        raw_data = {"FIELD1": "", "FIELD2": "   ", "FIELD3": ""}
        result = parse_date_from_raw_data(raw_data)
        assert result is None

    def test_invalid_date_skipped(self):
        """Test that invalid dates are skipped."""
        raw_data = {
            "BAD_DATE": "32/13/2025",  # Invalid day and month
            "GOOD_DATE": "14/10/2025"
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "GOOD_DATE"

    def test_real_world_italian_bank_data(self):
        """Test with real-world Italian bank transaction format."""
        raw_data = {
            "DATA CONTABILE": "14/10/2025",
            "DATA VALUTA": "16/10/2025",
            "DESCRIZIONE OPERAZIONE": "Op. Mastercard del 14/10/2025 presso ITALMARK",
            "USCITE": "-4,42"
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)  # Earliest date
        assert key in ["DATA CONTABILE", "DESCRIZIONE OPERAZIONE"]

    def test_leap_year_date(self):
        """Test leap year date."""
        raw_data = {"DATE": "29/02/2024"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2024, 2, 29)
        assert key == "DATE"

    def test_invalid_leap_year_skipped(self):
        """Test that invalid leap year date is skipped."""
        raw_data = {
            "BAD_DATE": "29/02/2025",  # Not a leap year
            "GOOD_DATE": "28/02/2025"
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 2, 28)
        assert key == "GOOD_DATE"

    def test_year_at_boundary(self):
        """Test dates at year boundaries."""
        raw_data = {"DATE": "31/12/2025"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 12, 31)
        assert key == "DATE"

    def test_first_day_of_year(self):
        """Test first day of year."""
        raw_data = {"DATE": "01/01/2025"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 1, 1)
        assert key == "DATE"

    def test_multiple_dates_in_single_value(self):
        """Test multiple dates in a single value separated by spaces."""
        raw_data = {
            "DESCRIPTION": "Transaction from 10/10/2025 to 15/10/2025"
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 10)  # Earliest
        assert key == "DESCRIPTION"

    def test_dates_with_mixed_separators(self):
        """Test value with multiple separator types."""
        raw_data = {
            "FIELD": "Start: 20/10/2025; End: 15/10/2025, Process: 10/10/2025"
        }
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 10)  # Earliest
        assert key == "FIELD"

    def test_date_with_tab_separator(self):
        """Test date separated by tab."""
        raw_data = {"FIELD": "Payment\t14/10/2025\tConfirmed"}
        result = parse_date_from_raw_data(raw_data)
        assert result is not None
        parsed_date, key = result
        assert parsed_date == date(2025, 10, 14)
        assert key == "FIELD"