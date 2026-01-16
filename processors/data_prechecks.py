from dataclasses import dataclass
from decimal import Decimal

from api.models import UploadFile
from processors.parser_utils import parse_amount_from_raw_data, parse_date_from_raw_data, \
    parse_unstructured_text


@dataclass
class RawTransactionParseResult:
    raw_data: dict[str, str]
    amount: Decimal | None = None
    original_amount: str | None = None
    date: str | None = None
    date_original: str | None = None
    description: str | None = None
    merchant: str | None = None
    operation_type: str | None = None
    is_income: bool = False

    def is_valid(self) -> bool:
        return self.amount is not None and self.date is not None and self.description is not None

    @staticmethod
    def from_dict(raw_data: dict[str, str], upload_files: list[UploadFile] = None) -> 'RawTransactionParseResult':
        if not upload_files:
            return RawTransactionParseResult(raw_data=raw_data)
        amount, amount_column_name = parse_amount_from_raw_data(raw_data,
                                                                [upload_file.expense_amount_column_name for upload_file in
                                                                 upload_files]+[upload_file.income_amount_column_name for upload_file in upload_files])
        date, date_column_name = parse_date_from_raw_data(raw_data,
                                                          [upload_file.date_column_name for upload_file in upload_files])
        target_upload_file = next((upload_file for upload_file in upload_files if
                                  (upload_file.income_amount_column_name == amount_column_name or upload_file.expense_amount_column_name == amount_column_name) and upload_file.date_column_name == date_column_name),
                                 None)
        is_income = False
        if target_upload_file:
            if target_upload_file.income_amount_column_name != target_upload_file.expense_amount_column_name:
                is_income = target_upload_file.income_amount_column_name == amount_column_name
            else:
                is_income = amount > Decimal(0)


        description, _ = parse_unstructured_text(raw_data,
                                                                       [upload_file.description_column_name for
                                                                        upload_file in upload_files])
        merchant, _ = parse_unstructured_text(raw_data,
                                                                 [upload_file.merchant_column_name for upload_file in
                                                                  upload_files])
        operation_type, _ = parse_unstructured_text(raw_data,
                                                                             [upload_file.operation_type_column_name for
                                                                              upload_file in
                                                                              upload_files])

        raw_transaction_result = RawTransactionParseResult(
            raw_data=raw_data,
            amount=amount,
            original_amount=raw_data.get(amount_column_name, ''),
            date=date,
            date_original=raw_data.get(date_column_name, ''),
            description=description,
            merchant=merchant,
            operation_type=operation_type,
            is_income=is_income
        )
        return raw_transaction_result


def parse_raw_transaction(raw_data: dict[str, str], upload_files: list[UploadFile] = None) -> RawTransactionParseResult:
    return RawTransactionParseResult.from_dict(raw_data, upload_files)
