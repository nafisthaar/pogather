import re
from datetime import datetime, timedelta

from . import rules
from .errors import ValidationError
from .formatting import format_rupiah

# "15000", "15.000" or "1,500,000": dots/commas only count as thousand separators.
_AMOUNT_PATTERN = re.compile(r"^([0-9]{1,3}([.,][0-9]{3})+|[0-9]+)$")
_WHOLE_NUMBER = re.compile(r"^[0-9]+$")
_PERSON_NAME = re.compile(r"^[^\W_][\w .'\-]*$")
_TITLE = re.compile(r"^[^\W_][\w .,'&()#/\-]*$")
_PHONE = re.compile(r"^\+?[0-9]{8,15}$")
_USERNAME = re.compile(r"^[a-z0-9_]{3,30}$")


def _clean_line(raw, label, max_length, pattern=None, required=True):
    text = " ".join((raw or "").split())
    if not text:
        if required:
            raise ValidationError(f"{label} is required.")
        return None
    if len(text) > max_length:
        raise ValidationError(f"{label} can be at most {max_length} characters.")
    if pattern and not pattern.match(text):
        raise ValidationError(f"{label} contains characters that are not allowed.")
    return text


def clean_full_name(raw):
    return _clean_line(raw, "Name", rules.MAX_FULL_NAME_LENGTH, _PERSON_NAME)


def clean_po_name(raw):
    return _clean_line(raw, "PO name", rules.MAX_PO_NAME_LENGTH, _TITLE)


def clean_item_name(raw):
    return _clean_line(raw, "Item name", rules.MAX_ITEM_NAME_LENGTH, _TITLE)


def clean_description(raw):
    return _clean_line(raw, "Description", rules.MAX_DESCRIPTION_LENGTH, required=False)


def clean_note(raw):
    return _clean_line(raw, "Note", rules.MAX_NOTE_LENGTH, required=False)


def clean_payment_info(raw):
    return _clean_line(raw, "Payment info", rules.MAX_PAYMENT_INFO_LENGTH, required=False)


def clean_phone(raw):
    text = re.sub(r"[ \-]", "", (raw or "").strip())
    if not text:
        return None
    if not _PHONE.match(text):
        raise ValidationError("Phone must be 8 to 15 digits, optionally starting with +.")
    return text


def clean_username(raw):
    username = (raw or "").strip().lower()
    if not _USERNAME.match(username):
        raise ValidationError("Username must be 3-30 characters: a-z, 0-9 or underscore.")
    return username


def check_password(raw):
    if raw is None or not rules.MIN_PASSWORD_LENGTH <= len(raw) <= rules.MAX_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be {rules.MIN_PASSWORD_LENGTH}-{rules.MAX_PASSWORD_LENGTH} characters."
        )
    return raw


def parse_price(raw):
    text = re.sub(r"^rp\.?\s*", "", (raw or "").strip(), flags=re.IGNORECASE)
    if not _AMOUNT_PATTERN.match(text):
        raise ValidationError("Price must be a whole number of rupiah, like 15000 or 15.000.")
    value = int(re.sub(r"[.,]", "", text))
    if not 1 <= value <= rules.MAX_PRICE:
        raise ValidationError(f"Price must be between Rp 1 and {format_rupiah(rules.MAX_PRICE)}.")
    return value


def parse_quota(raw):
    text = (raw or "").strip()
    if not _WHOLE_NUMBER.match(text) or not 1 <= int(text) <= rules.MAX_QUOTA:
        raise ValidationError(f"Quota must be a whole number from 1 to {rules.MAX_QUOTA}.")
    return int(text)


def parse_quantity(raw):
    """Blank means 'none of this item'. Returns 0 to MAX_QTY_PER_ITEM."""
    text = (raw or "").strip()
    if not text:
        return 0
    if not _WHOLE_NUMBER.match(text) or int(text) > rules.MAX_QTY_PER_ITEM:
        raise ValidationError(
            f"Quantity must be a whole number from 0 to {rules.MAX_QTY_PER_ITEM} for each item."
        )
    return int(text)


def parse_quantities(raw_by_item_id):
    """{item_id: 'raw text'} -> {item_id: quantity}, keeping only items with quantity above 0."""
    quantities = {}
    for item_id, raw in raw_by_item_id.items():
        quantity = parse_quantity(raw)
        if quantity > 0:
            quantities[item_id] = quantity
    if not quantities:
        raise ValidationError("Choose at least one item.")
    return quantities


def parse_deadline(raw, now, unchanged_from=None):
    """Local date and time like 2026-12-31T17:00. It must be in the future, unless the owner
    is saving an edit without touching the deadline (`unchanged_from`)."""
    try:
        value = datetime.fromisoformat((raw or "").strip())
    except ValueError:
        raise ValidationError("Deadline must look like 2026-12-31T17:00.") from None
    if value.tzinfo is not None:
        raise ValidationError("Deadline must not include a time zone.")
    value = value.replace(second=0, microsecond=0)
    if value > now + timedelta(days=rules.MAX_DEADLINE_DAYS):
        raise ValidationError(f"Deadline can be at most {rules.MAX_DEADLINE_DAYS} days away.")
    if value <= now and value != unchanged_from:
        raise ValidationError("Deadline must be in the future.")
    return value


def parse_payment_method(raw):
    method = (raw or "").strip()
    if method not in rules.PAYMENT_METHODS:
        raise ValidationError("Choose a payment method: bank transfer, e-wallet or QRIS.")
    return method
