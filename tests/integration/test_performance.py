from decimal import Decimal
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.enums import TransactionStatus, TransactionType
from app.infrastructure.models import Account, Transaction, User
from app.infrastructure.repositories.transaction_repository import TransactionRepository


class QueryCounter:
    def __init__(self):
        self.count = 0
        self.queries = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1
        self.queries.append(statement)


class TestN1QueryPrevention:
    def test_transaction_list_prevents_n1_query(self, db: Session):
        user = User(
            email=f"perf_test_{uuid4()}@example.com",
            full_name="Performance Test",
            hashed_password="hashed",
        )
        db.add(user)
        db.flush()

        account = Account(
            user_id=user.id,
            balance=Decimal("1000.00"),
            currency="USD",
        )
        db.add(account)
        db.flush()

        num_transactions = 20
        for _ in range(num_transactions):
            transaction = Transaction(
                account_id=account.id,
                transaction_type=TransactionType.DEPOSIT,
                amount=Decimal("10.00"),
                currency="USD",
                status=TransactionStatus.SUCCESS,
            )
            db.add(transaction)

        db.commit()

        query_counter = QueryCounter()
        event.listen(Engine, "before_cursor_execute", query_counter, named=True)

        try:
            transaction_repo = TransactionRepository(db)
            transactions = transaction_repo.get_by_account_id(
                account_id=account.id,
                skip=0,
                limit=20,
            )

            for tx in transactions:
                _ = tx.account

            assert query_counter.count <= 3, (
                f"Expected <= 3 queries with eager loading, got {query_counter.count}. "
                f"This indicates N+1 query problem! Queries: {query_counter.queries}"
            )

            assert len(transactions) == num_transactions

        finally:
            event.remove(Engine, "before_cursor_execute", query_counter)

    def test_transaction_list_with_100_items_efficient(self, db: Session):
        user = User(
            email=f"perf_large_test_{uuid4()}@example.com",
            full_name="Large Performance Test",
            hashed_password="hashed",
        )
        db.add(user)
        db.flush()

        account = Account(
            user_id=user.id,
            balance=Decimal("10000.00"),
            currency="USD",
        )
        db.add(account)
        db.flush()

        num_transactions = 100
        for _ in range(num_transactions):
            transaction = Transaction(
                account_id=account.id,
                transaction_type=TransactionType.DEPOSIT,
                amount=Decimal("10.00"),
                currency="USD",
                status=TransactionStatus.SUCCESS,
            )
            db.add(transaction)

        db.commit()

        query_counter = QueryCounter()
        event.listen(Engine, "before_cursor_execute", query_counter, named=True)

        try:
            transaction_repo = TransactionRepository(db)
            transactions = transaction_repo.get_by_account_id(
                account_id=account.id,
                skip=0,
                limit=100,
            )

            for tx in transactions:
                _ = tx.account

            assert (
                query_counter.count <= 3
            ), f"N+1 query detected! Expected <= 3 queries, got {query_counter.count}"

            assert len(transactions) == num_transactions

        finally:
            event.remove(Engine, "before_cursor_execute", query_counter)

    def test_transaction_filtering_doesnt_cause_extra_queries(self, db: Session):
        user = User(
            email=f"filter_test_{uuid4()}@example.com",
            full_name="Filter Test",
            hashed_password="hashed",
        )
        db.add(user)
        db.flush()

        account = Account(
            user_id=user.id,
            balance=Decimal("1000.00"),
            currency="USD",
        )
        db.add(account)
        db.flush()

        for _ in range(10):
            transaction = Transaction(
                account_id=account.id,
                transaction_type=TransactionType.DEPOSIT,
                amount=Decimal("10.00"),
                currency="USD",
                status=TransactionStatus.SUCCESS,
            )
            db.add(transaction)

        for _ in range(10):
            transaction = Transaction(
                account_id=account.id,
                transaction_type=TransactionType.WITHDRAWAL,
                amount=Decimal("5.00"),
                currency="USD",
                status=TransactionStatus.SUCCESS,
            )
            db.add(transaction)

        db.commit()

        query_counter = QueryCounter()
        event.listen(Engine, "before_cursor_execute", query_counter, named=True)

        try:
            transaction_repo = TransactionRepository(db)
            deposits = transaction_repo.get_by_account_id(
                account_id=account.id,
                transaction_type=TransactionType.DEPOSIT,
                limit=20,
            )

            assert query_counter.count <= 3
            assert len(deposits) == 10

        finally:
            event.remove(Engine, "before_cursor_execute", query_counter)


class TestDatabaseOptimization:
    def test_indexes_exist_on_critical_columns(self, db: Session):
        from sqlalchemy import inspect

        inspector = inspect(db.bind)
        transaction_indexes = inspector.get_indexes("transactions")
        assert any(
            "account_id" in idx["column_names"] for idx in transaction_indexes
        ), "Missing index on account_id"
        assert any(
            "status" in idx["column_names"] for idx in transaction_indexes
        ), "Missing index on status"
        assert any(
            "created_at" in idx["column_names"] for idx in transaction_indexes
        ), "Missing index on created_at"

    def test_failed_tasks_table_has_indexes(self, db: Session):
        from sqlalchemy import inspect

        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        assert "failed_tasks" in tables, "failed_tasks table not created"
        failed_task_indexes = inspector.get_indexes("failed_tasks")
        index_columns = [col for idx in failed_task_indexes for col in idx["column_names"]]
        assert "task_id" in index_columns, "Missing index on task_id"
        assert "task_name" in index_columns, "Missing index on task_name"
        assert "failed_at" in index_columns, "Missing index on failed_at"
