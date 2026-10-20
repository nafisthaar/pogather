class AppError(Exception):
    """Base class for expected errors."""


class ValidationError(AppError):
    """The input is wrong: bad format, out of range, or asks for more than the quota."""


class BusinessRuleError(AppError):
    """The input is fine, but the current state of the data does not allow it."""


class DeadlineError(BusinessRuleError):
    """The PO deadline has passed."""


class InvalidTransitionError(BusinessRuleError):
    """The order status can not change that way."""


class NotFoundError(AppError):
    """The record does not exist (or the user is not allowed to know it exists)."""
