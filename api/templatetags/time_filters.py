from django import template

register = template.Library()


@register.filter
def format_processing_time(milliseconds):
    """Format milliseconds into human-readable time"""
    if milliseconds is None:
        return "N/A"

    try:
        ms = float(milliseconds)

        if ms >= 60000:
            minutes = ms / 60000
            return f"{minutes:.1f}min"
        elif ms >= 1000:
            seconds = ms / 1000
            return f"{seconds:.2f}s"
        else:
            return f"{ms:.0f}ms"
    except (ValueError, TypeError):
        return str(milliseconds)