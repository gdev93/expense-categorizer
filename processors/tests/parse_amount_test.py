from decimal import Decimal

from processors.parser_utils import parse_amount_from_raw_data


class TestParseAmountFromRawData:
    """Test suite for parse_amount_from_raw_data function."""

    def test_italian_format_simple_comma(self):
        """Test simple Italian format with comma as decimal separator."""
        raw_data = {"USCITE": "-4,42"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("4.42")
        assert key == "USCITE"

    def test_italian_format_with_thousands(self):
        """Test Italian format with dot as thousands separator."""
        raw_data = {"AMOUNT": "1.234,56"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("1234.56")
        assert key == "AMOUNT"

    def test_positive_with_plus_sign(self):
        """Test amount with explicit plus sign."""
        raw_data = {"ENTRATE": "+100,50"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("100.50")
        assert key == "ENTRATE"

    def test_negative_with_minus_sign(self):
        """Test amount with minus sign."""
        raw_data = {"USCITE": "-250,75"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("250.75")
        assert key == "USCITE"

    def test_large_italian_amount(self):
        """Test large amount in Italian format."""
        raw_data = {"AMOUNT": "12.345.678,90"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("12345678.90")
        assert key == "AMOUNT"

    def test_amount_with_spaces(self):
        """Test amount with spaces (should be handled)."""
        raw_data = {"AMOUNT": "- 1.234,56"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("-1234.56")
        assert key == "AMOUNT"

    def test_multiple_same_amounts(self):
        """Test when same amount appears in multiple values."""
        raw_data = {"USCITE": "-30,00", "CAUSALE": "Bonifico In Uscita", "ENTRATE": "", "DATA VALUTA": "27/09/2025",
                    "DATA CONTABILE": "27/09/2025",
                    "DESCRIZIONE OPERAZIONE": "Bonifico istantaneo da voi disposto N. CPUB6M0NCLQSNWEL008SAAX9A3FH A favore di Iovis Societa' A Responsabilita' Limitata IBAN beneficiario IT37G0760113200001060974860 Note: Saldo pernottamento Zanotti musicco"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("-30")
        assert key in ["USCITE", "IMPORTO", "TOTALE"]

    def test_multiple_different_amounts_picks_shortest_value(self):
        """Test when different amounts are found, picks from shortest value."""
        raw_data = {
            "FIELD1": "Amount is 100,50 EUR",  # Longer value
            "FIELD2": "50,25",  # Shortest value
            "FIELD3": "Total: 75,00"  # Medium value
        }
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("50.25")
        assert key == "FIELD2"

    def test_amount_embedded_in_text(self):
        """Test extracting amount from text."""
        raw_data = {
            "DESCRIZIONE": "Op. Mastercard presso ITALMARK importo 4,42"
        }
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("4.42")
        assert key == "DESCRIZIONE"

    def test_no_amount_returns_none(self):
        """Test that None is returned when no amount is found."""
        raw_data = {"DESCRIZIONE": "Payment at store", "DATE": "14/10/2025"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is None

    def test_empty_dictionary_returns_none(self):
        """Test that None is returned for empty dictionary."""
        raw_data = {}
        result = parse_amount_from_raw_data(raw_data)
        assert result is None

    def test_empty_values_returns_none(self):
        """Test that None is returned when all values are empty."""
        raw_data = {"FIELD1": "", "FIELD2": "   ", "FIELD3": ""}
        result = parse_amount_from_raw_data(raw_data)
        assert result is None

    def test_amount_with_two_decimals(self):
        """Test amount with exactly two decimal places."""
        raw_data = {"AMOUNT": "99,99"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("99.99")
        assert key == "AMOUNT"

    def test_amount_with_three_decimals(self):
        """Test amount with three decimal places."""
        raw_data = {"AMOUNT": "100,123"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("100.123")
        assert key == "AMOUNT"

    def test_zero_amount(self):
        """Test zero amount."""
        raw_data = {"AMOUNT": "0,00"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("0.00")
        assert key == "AMOUNT"

    def test_real_world_italian_bank_data(self):
        """Test with real-world Italian bank transaction format."""
        raw_data = {
            "DATA CONTABILE": "14/10/2025",
            "DATA VALUTA": "16/10/2025",
            "DESCRIZIONE OPERAZIONE": "Op. Mastercard del 14/10/2025 presso ITALMARK",
            "USCITE": "-4,42"
        }
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("-4.42")
        assert key == "USCITE"

    def test_amount_in_shortest_field(self):
        """Test that when amounts differ, shortest field value is chosen."""
        raw_data = {
            "LONG_DESCRIPTION": "The transaction amount was 1.000,00 euros",
            "AMOUNT": "500,50",
            "NOTE": "Paid 250,25 to vendor"
        }
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("500.50")
        assert key == "AMOUNT"

    def test_small_decimal_amount(self):
        """Test very small decimal amount."""
        raw_data = {"AMOUNT": "0,01"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("0.01")
        assert key == "AMOUNT"

    def test_amount_without_decimals_not_matched(self):
        """Test that amounts without decimals are not matched (requires 2+ decimals)."""
        raw_data = {"AMOUNT": "100"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is None

    def test_amount_with_one_decimal_not_matched(self):
        """Test that amounts with only one decimal place are not matched."""
        raw_data = {"AMOUNT": "100,5"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is None

    def test_multiple_amounts_in_one_value_takes_first(self):
        """Test that when multiple amounts are in one value, first is taken."""
        raw_data = {"DESCRIPTION": "Paid 100,50 and received 50,25 back"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("100.50")
        assert key == "DESCRIPTION"

    def test_amount_with_currency_symbol_nearby(self):
        """Test amount with currency symbol nearby in text."""
        raw_data = {"AMOUNT": "€ 1.234,56"}
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        assert amount == Decimal("1234.56")
        assert key == "AMOUNT"

    def test_mixed_format_keys(self):
        """Test with amounts in different fields with different formats."""
        raw_data = {
            "ITALIAN_AMOUNT": "1.234,56",
            "US_AMOUNT": "5.678,90",  # Will be parsed as US format
            "SIMPLE": "42,00"
        }
        result = parse_amount_from_raw_data(raw_data)
        assert result is not None
        amount, key = result
        # Should pick the shortest value
        assert key == "SIMPLE"
        assert amount == Decimal("42.00")