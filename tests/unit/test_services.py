from decimal import Decimal

import pytest

from app.core.enums import TransactionStatus
from app.domain.exceptions import InsufficientBalanceError
from app.domain.services.balance_service import BalanceService
from app.domain.services.deposit_service import DepositService
from app.domain.services.withdrawal_service import WithdrawalService


class TestDepositService:
    def test_create_pending_deposit(self, db, test_user):
        from app.infrastructure.repositories.account_repository import AccountRepository

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(test_user.id)

        service = DepositService(db)
        transaction = service.create_pending_deposit(
            account_id=account.id,
            amount=Decimal("100.00"),
            currency="USD",
        )

        assert transaction.id is not None
        assert transaction.status == TransactionStatus.PENDING
        assert transaction.amount == Decimal("100.00")

    def test_complete_deposit_adds_balance(self, db, test_user):
        from app.infrastructure.repositories.account_repository import AccountRepository

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(test_user.id)
        initial_balance = account.balance

        service = DepositService(db)
        transaction = service.create_pending_deposit(
            account_id=account.id,
            amount=Decimal("100.00"),
            currency="USD",
        )

        service.complete_deposit(
            transaction_id=transaction.id,
            bank_transaction_id="BANK-123",
        )

        db.refresh(account)
        assert account.balance == initial_balance + Decimal("100.00")

        db.refresh(transaction)
        assert transaction.status == TransactionStatus.SUCCESS


class TestWithdrawalService:
    def test_withdrawal_reserves_balance(self, db, test_user_with_balance):
        user, account = test_user_with_balance
        initial_balance = account.balance

        service = WithdrawalService(db)
        transaction = service.create_pending_withdrawal(
            account_id=account.id,
            amount=Decimal("100.00"),
            currency="USD",
        )

        db.refresh(account)
        assert account.balance == initial_balance
        assert transaction.status == TransactionStatus.PENDING

    def test_withdrawal_insufficient_balance_fails(self, db, test_user):
        from app.infrastructure.repositories.account_repository import AccountRepository

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(test_user.id)

        service = WithdrawalService(db)

        with pytest.raises(InsufficientBalanceError):
            service.create_pending_withdrawal(
                account_id=account.id,
                amount=Decimal("9999.00"),
                currency="USD",
            )

    def test_failed_withdrawal_no_refund_needed(self, db, test_user_with_balance):
        user, account = test_user_with_balance
        initial_balance = account.balance

        service = WithdrawalService(db)
        transaction = service.create_pending_withdrawal(
            account_id=account.id,
            amount=Decimal("100.00"),
            currency="USD",
        )

        db.refresh(account)
        assert account.balance == initial_balance

        service.fail_withdrawal(
            transaction_id=transaction.id,
            error_code="BANK_ERROR",
            error_message="Bank failed",
        )

        db.refresh(account)
        assert account.balance == initial_balance

        db.refresh(transaction)
        assert transaction.status == TransactionStatus.FAILED


class TestBalanceService:
    def test_get_balance(self, db, test_user_with_balance):
        user, account = test_user_with_balance

        service = BalanceService(db)
        balance = service.get_balance(account.id)

        assert balance == Decimal("1000.00")

    def test_get_balance_by_user_id(self, db, test_user_with_balance):
        user, account = test_user_with_balance

        service = BalanceService(db)
        result = service.get_balance_by_user_id(user.id)

        assert result["balance"] == Decimal("1000.00")
        assert result["currency"] == "USD"
        assert result["account_id"] == account.id
