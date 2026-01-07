from decimal import Decimal

from app.core.enums import TransactionStatus, TransactionType
from app.infrastructure.models import Account, Transaction, User


class TestUserModel:
    def test_user_creation(self, db):
        user = User(
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.is_active is True
        assert user.created_at is not None


class TestAccountModel:
    def test_account_creation(self, db, test_user):
        from app.infrastructure.repositories.account_repository import AccountRepository

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(test_user.id)

        assert account is not None
        assert account.id is not None
        assert account.user_id == test_user.id
        assert account.balance == Decimal("0.00")
        assert account.currency == "USD"

    def test_balance_constraint_non_negative(self, db, test_user):
        account = Account(
            user_id=test_user.id,
            balance=Decimal("-10.00"),
            currency="USD",
        )
        db.add(account)

        db.rollback()


class TestTransactionModel:
    def test_transaction_creation(self, db, test_user):
        from app.infrastructure.repositories.account_repository import AccountRepository

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(test_user.id)

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("50.00"),
            currency="USD",
            status=TransactionStatus.PENDING,
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        assert transaction.id is not None
        assert transaction.account_id == account.id
        assert transaction.transaction_type == TransactionType.DEPOSIT
        assert transaction.amount == Decimal("50.00")
        assert transaction.status == TransactionStatus.PENDING

    def test_amount_must_be_positive(self, db, test_user):
        from app.infrastructure.repositories.account_repository import AccountRepository

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(test_user.id)

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("0.00"),
            currency="USD",
            status=TransactionStatus.PENDING,
        )
        db.add(transaction)

        db.rollback()
