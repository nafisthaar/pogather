from datetime import datetime


def format_rupiah(amount):
    """15000 -> 'Rp 15.000' (Indonesian thousand separator)."""
    return "Rp " + f"{amount:,}".replace(",", ".")


def format_datetime(value):
    """Accepts an ISO string or a datetime and returns '05 Mar 2026, 17:00'."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%d %b %Y, %H:%M")
