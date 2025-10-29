
from datetime import date
from decimal import Decimal

from processors.data_prechecks import RawTransactionParseResult
from processors.parser_utils import parse_date_from_raw_data


class TestRawResultFromRawData:
    """Test suite for parse_date_from_raw_data function."""
    def test_parse(self):
        data_raw = {"USCITE": "", "CAUSALE": "", "ENTRATE": "-35,88", "DATA VALUTA": "", "DATA CONTABILE": "30/09/2025", "DESCRIZIONE OPERAZIONE": "Saldo finale"}
        result = RawTransactionParseResult.from_dict(data_raw)
        assert result.amount == Decimal("-35,88")
        assert result.description == data_raw["DESCRIZIONE OPERAZIONE"]
        assert result.date == date(2025, 9, 30)
        assert result.original_amount == data_raw["USCITE"]
        assert result.is_valid() == True