class DomainException(Exception):
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class InsufficientBalanceError(DomainException):
    def __init__(self, message: str = "Insufficient balance"):
        super().__init__(message, code="INSUFFICIENT_BALANCE")


class AccountNotFoundError(DomainException):
    def __init__(self, message: str = "Account not found"):
        super().__init__(message, code="ACCOUNT_NOT_FOUND")


class UserNotFoundError(DomainException):
    def __init__(self, message: str = "User not found"):
        super().__init__(message, code="USER_NOT_FOUND")


class TransactionNotFoundError(DomainException):
    def __init__(self, message: str = "Transaction not found"):
        super().__init__(message, code="TRANSACTION_NOT_FOUND")


class BankError(DomainException):
    def __init__(self, message: str = "Bank operation failed"):
        super().__init__(message, code="BANK_ERROR")


class ConcurrentUpdateError(DomainException):
    def __init__(self, message: str = "Resource is locked by another process"):
        super().__init__(message, code="CONCURRENT_UPDATE")
