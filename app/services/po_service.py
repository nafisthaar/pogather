from datetime import datetime

from .. import rules, validation
from ..db import write_transaction
from ..errors import BusinessRuleError, NotFoundError, ValidationError
from ..repositories import po_sessions as po_repo


def _iso(moment):
    return moment.isoformat(timespec="seconds")


def _view(row, now):
    deadline = datetime.fromisoformat(row["deadline"])
    po = dict(row)
    po["deadline_dt"] = deadline
    po["remaining"] = max(0, row["quota"] - row["used"])
    po["fill_percent"] = min(100, round(100 * row["used"] / row["quota"]))
    po["is_expired"] = now >= deadline
    po["accepting_orders"] = row["status"] == rules.PO_OPEN and now < deadline
    return po


def _get_row(conn, po_id):
    row = po_repo.get(conn, po_id)
    if row is None:
        raise NotFoundError("PO not found.")
    return row


def sync_expired(conn, now):
    with write_transaction(conn):
        return po_repo.close_expired(conn, _iso(now))


def create_session(conn, owner_id, name_raw, quota_raw, deadline_raw, payment_info_raw, now=None):
    now = now or datetime.now()
    name = validation.clean_po_name(name_raw)
    quota = validation.parse_quota(quota_raw)
    deadline = validation.parse_deadline(deadline_raw, now)
    payment_info = validation.clean_payment_info(payment_info_raw)
    with write_transaction(conn):
        return po_repo.create(conn, name, quota, _iso(deadline), payment_info, owner_id, _iso(now))


def update_session(conn, po_id, name_raw, quota_raw, deadline_raw, payment_info_raw, now=None):
    now = now or datetime.now()
    name = validation.clean_po_name(name_raw)
    quota = validation.parse_quota(quota_raw)
    payment_info = validation.clean_payment_info(payment_info_raw)
    with write_transaction(conn):
        po = _get_row(conn, po_id)
        deadline = validation.parse_deadline(
            deadline_raw, now, unchanged_from=datetime.fromisoformat(po["deadline"])
        )
        if quota < po["used"]:
            raise ValidationError(
                f"Quota can not be lower than the {po['used']} portions that are already ordered."
            )
        po_repo.update(conn, po_id, name, quota, _iso(deadline), payment_info)


def set_status(conn, po_id, status, now=None):
    now = now or datetime.now()
    if status not in rules.PO_STATUSES:
        raise ValidationError("Status must be OPEN or CLOSED.")
    with write_transaction(conn):
        po = _get_row(conn, po_id)
        if status == rules.PO_OPEN and now >= datetime.fromisoformat(po["deadline"]):
            raise BusinessRuleError("The deadline has passed. Edit the PO and set a new deadline first.")
        po_repo.set_status(conn, po_id, status)


def get_session(conn, po_id, now=None):
    now = now or datetime.now()
    sync_expired(conn, now)
    return _view(_get_row(conn, po_id), now)


def list_open_sessions(conn, now=None):
    now = now or datetime.now()
    sync_expired(conn, now)
    return [_view(row, now) for row in po_repo.list_open(conn)]


def list_all_sessions(conn, now=None):
    now = now or datetime.now()
    sync_expired(conn, now)
    return [_view(row, now) for row in po_repo.list_all(conn)]
