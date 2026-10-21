from .. import rules
from ..repositories import orders as orders_repo
from . import po_service


def po_recap(conn, po_id, now=None):
    session = po_service.get_session(conn, po_id, now)
    by_status = {status: {"orders": 0, "portions": 0, "amount": 0} for status in rules.ORDER_STATUSES}
    for row in orders_repo.totals_by_status(conn, po_id):
        by_status[row["status"]] = {
            "orders": row["orders"], "portions": row["portions"], "amount": row["amount"],
        }
    return {
        "session": session,
        "per_menu": [dict(row) for row in orders_repo.portions_per_menu(conn, po_id)],
        "by_status": by_status,
        "total_portions": session["used"],                          
        "revenue_paid": by_status[rules.ORDER_PAID]["amount"],      
        "revenue_pending": by_status[rules.ORDER_PENDING]["amount"],  
    }
