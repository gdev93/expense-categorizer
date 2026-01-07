import csv
import io
from typing import Iterator

from api.models import Transaction


def generate_transaction_csv(transactions_iterator: Iterator[Transaction]):
    """
    A generator that yields CSV rows for the given transactions iterator.
    
    Args:
        transactions_iterator: An iterable of Transaction model instances.
                              Should be called with .iterator() for efficiency.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Italian Headers Mapping
    # Date -> Data
    # Amount -> Importo
    # Transaction Type -> Tipo di Transazione
    # Bank Description -> Descrizione Bancaria
    # Original CSV Source -> File Sorgente
    headers = ['Data', 'Importo', 'Categoria', 'Descrizione Bancaria', 'Tipo di Transazione', 'File Sorgente']
    writer.writerow(headers)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)

    for tx in transactions_iterator:
        row = [
            tx.transaction_date.isoformat() if tx.transaction_date else '',
            tx.amount,
            tx.category.name if tx.category else '',
            tx.description,
            tx.transaction_type,
            tx.csv_upload.file_name if tx.csv_upload else ''
        ]
        writer.writerow(row)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)
