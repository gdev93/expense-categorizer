import hmac
import hashlib
import base64
from django.conf import settings
from cryptography.fernet import Fernet

def generate_blind_index(value):
    """
    Generate a deterministic HMAC-SHA256 hash (salted with settings.SECRET_KEY)
    for a given value to allow exact matching on encrypted fields.
    """
    if not value:
        return ""
    # Use HMAC with SECRET_KEY for security
    return hmac.new(
        settings.SECRET_KEY.encode(),
        value.lower().strip().encode(),
        hashlib.sha256
    ).hexdigest()

def _get_fernet():
    """Derives a Fernet key from settings.SECRET_KEY."""
    # Ensure it's 32 bytes for Fernet
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_value(value):
    """Encrypt a value using application-level encryption."""
    if value is None:
        return None
    f = _get_fernet()
    return f.encrypt(str(value).encode()).decode()

def decrypt_value(encrypted_value):
    """Decrypt an encrypted value."""
    if not encrypted_value:
        return None
    f = _get_fernet()
    try:
        return f.decrypt(encrypted_value.encode()).decode()
    except Exception:
        return None
