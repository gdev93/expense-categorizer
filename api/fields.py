from django.db import models
from decimal import Decimal
from api.privacy_utils import encrypt_value, decrypt_value

class EncryptedDecimalField(models.TextField):
    description = "A field that encrypts and decrypts Decimal values"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return Decimal('0.00')
        decrypted = decrypt_value(value)
        try:
            return Decimal(decrypted) if decrypted else Decimal('0.00')
        except Exception:
            return Decimal('0.00')

    def to_python(self, value):
        if value is None or isinstance(value, Decimal):
            return value
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception:
                return Decimal('0.00')
        return Decimal(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        return encrypt_value(str(value))

class EncryptedCharField(models.TextField):
    description = "A field that encrypts and decrypts string values"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return ""
        decrypted = decrypt_value(value)
        return decrypted or ""

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        return str(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        return encrypt_value(str(value))
