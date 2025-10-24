from dataclasses import dataclass
from decimal import Decimal

from processors.parser_utils import parse_amount_from_raw_data, parse_date_from_raw_data, \
    parse_description_from_raw_data


@dataclass
class RawTransactionParseResult:
    raw_data: dict[str, str]
    amount: Decimal | None
    original_amount: str | None
    date: str | None
    date_original: str | None
    description: str | None

    def is_valid(self) -> bool:
        return self.amount is not None and self.date is not None

    @staticmethod
    def from_dict(raw_data: dict[str, str]) -> 'RawTransactionParseResult':
        amount, amount_key = parse_amount_from_raw_data(raw_data)
        date, date_key = parse_date_from_raw_data(raw_data)
        input_description = raw_data.copy()
        del input_description[amount_key]
        del input_description[date_key]
        return RawTransactionParseResult(
            raw_data=raw_data,
            amount=amount,
            original_amount=raw_data.get(amount_key, ''),
            date=date,
            date_original=raw_data.get(date_key,''),
            description=parse_description_from_raw_data([value for _, value in input_description.items()])
        )

def parse_raw_transaction(raw_data: list[dict[str, str]]) -> list[RawTransactionParseResult]:
    return [RawTransactionParseResult.from_dict(raw_data) for raw_data in raw_data]
