from dataclasses import dataclass
from decimal import Decimal

from api.models import CsvUpload
from processors.parser_utils import parse_amount_from_raw_data, parse_date_from_raw_data, \
    parse_unstructured_text


@dataclass
class RawTransactionCsvHeaderNames:
    amount: str
    date: str
    description: str
    merchant: str | None = None
@dataclass
class RawTransactionParseResult:
    raw_data: dict[str, str]
    amount: Decimal | None = None
    original_amount: str | None = None
    date: str | None = None
    date_original: str | None = None
    description: str | None = None
    merchant: str | None = None
    header_names: RawTransactionCsvHeaderNames | None = None
    def is_valid(self) -> bool:
        return self.amount is not None and self.date is not None and self.description is not None

    @staticmethod
    def from_dict(raw_data: dict[str, str], csv_uploads: list[CsvUpload] = None) -> 'RawTransactionParseResult':
        if not csv_uploads:
            return RawTransactionParseResult(raw_data=raw_data)
        amount, amount_column_name = parse_amount_from_raw_data(raw_data,
                                                                [csv_upload.amount_column_name for csv_upload in
                                                                 csv_uploads])
        date, date_column_name = parse_date_from_raw_data(raw_data,
                                                          [csv_upload.date_column_name for csv_upload in csv_uploads])
        description, description_column_name = parse_unstructured_text(raw_data,
                                                                       [csv_upload.description_column_name for
                                                                        csv_upload in csv_uploads])
        merchant, merchant_column_name = parse_unstructured_text(raw_data,
                                                                 [csv_upload.merchant_column_name for csv_upload in
                                                                  csv_uploads])

        raw_transaction_result = RawTransactionParseResult(
            raw_data=raw_data,
            amount=amount,
            original_amount=raw_data.get(amount_column_name, ''),
            date=date,
            date_original=raw_data.get(date_column_name, ''),
            description=description,
            merchant=merchant
        )
        if raw_transaction_result.is_valid():
            raw_transaction_result.header_names = RawTransactionCsvHeaderNames(
                amount=amount_column_name,
                date=date_column_name,
                description=description_column_name,
                merchant=merchant_column_name
            )
        return raw_transaction_result


def parse_raw_transaction(raw_data: dict[str, str], csv_uploads: list[CsvUpload] = None) -> RawTransactionParseResult:
    return RawTransactionParseResult.from_dict(raw_data, csv_uploads)
