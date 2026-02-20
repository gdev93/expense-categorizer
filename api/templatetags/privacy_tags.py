from django import template
from api.privacy_utils import decrypt_value

register = template.Library()

@register.filter
def decrypt(value):
    if not value:
        return ""
    try:
        return decrypt_value(value)
    except Exception:
        return value
