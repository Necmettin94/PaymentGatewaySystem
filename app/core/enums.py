from enum import Enum


class TransactionType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING_REVIEW = "PENDING_REVIEW"


class Currency(str, Enum):
    USD = "USD"
    # ... another currencies


class BankResponseStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    UNAVAILABLE = "UNAVAILABLE"
