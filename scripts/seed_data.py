import argparse
import json
import random
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# sys.path ayarı importlardan önce gelmek zorunda olduğu için
# alttaki importlarda E402 kuralını (Module level import not at top of file) susturuyoruz.
sys.path.insert(0, str(Path(__file__).parent.parent))  # nosec


from app.core.enums import TransactionStatus, TransactionType  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.domain.services.auth_service import AuthService  # noqa: E402
from app.infrastructure.database.session import SessionLocal  # noqa: E402
from app.infrastructure.models import Account, FailedTask, Transaction, User  # noqa: E402

configure_logging("INFO")
logger = get_logger(__name__)


def seed_users():
    db = SessionLocal()

    try:
        existing_count = db.query(User).count()
        if existing_count > 0:
            logger.info("users_already_exist", count=existing_count)
            return

        service = AuthService(db)

        test_users = [
            {
                "email": "admin@example.com",
                "full_name": "Admin User",
                "password": "admin123",
                "webhook_url": None,  # Admin doesn't need webhooks
            },
            {
                "email": "alice@example.com",
                "full_name": "Alice Johnson",
                "password": "password123",
                "webhook_url": None,
            },
            {
                "email": "bob@example.com",
                "full_name": "Bob Smith",
                "password": "password123",
                "webhook_url": None,
            },
            {
                "email": "charlie@example.com",
                "full_name": "Charlie Brown",
                "password": "password123",
                "webhook_url": None,
            },
        ]

        created_users = []
        for user_data in test_users:
            user = service.register_user(
                email=str(user_data["email"]),
                full_name=str(user_data["full_name"]),
                password=str(user_data["password"]),
            )
            created_users.append(user)
            logger.info("user_created", email=user.email, id=str(user.id))

        logger.info("seed_completed", user_count=len(created_users))

    except Exception as e:
        logger.error("seed_failed", error=str(e))
        db.rollback()
        raise

    finally:
        db.close()


def seed_failed_tasks(count: int = 5):
    db = SessionLocal()

    try:
        existing_count = db.query(FailedTask).count()
        if existing_count >= count:
            logger.info("failed_tasks_already_exist", count=existing_count)
            return

        created = 0
        for i in range(count):
            task_id = str(uuid4())
            failed_task = FailedTask(
                task_id=task_id,
                task_name="seed.test_task",
                args=json.dumps([f"arg{i}"]),
                kwargs=json.dumps({}),
                exception_type="RuntimeError",
                exception_message=f"Seeded failure {i}",
                traceback="Traceback (most recent call last): ...",
                retry_count="0",
                failed_at=datetime.now(UTC),
            )

            db.add(failed_task)
            created += 1

        db.commit()
        logger.info("seed_failed_tasks_completed", created=created)

    except Exception as e:
        logger.error("seed_failed_tasks_failed", error=str(e))
        db.rollback()
        raise

    finally:
        db.close()


def seed_transactions(count: int = 15):
    db = SessionLocal()

    try:
        account_count = db.query(Account).count()
        if account_count == 0:
            logger.info(
                "no_accounts_found_creating_users",
            )
            seed_users()

        accounts = db.query(Account).all()

        existing_count = db.query(Transaction).count()
        if existing_count >= count:
            logger.info("transactions_already_exist", count=existing_count)
            return

        created = 0
        for _ in range(count):
            acct = random.choice(accounts)  # nosec
            ttype = random.choice(
                [TransactionType.DEPOSIT.value, TransactionType.WITHDRAWAL.value]
            )  # nosec
            status = random.choice(  # nosec
                [
                    TransactionStatus.PENDING.value,
                    TransactionStatus.PROCESSING.value,
                    TransactionStatus.SUCCESS.value,
                    TransactionStatus.FAILED.value,
                ]
            )
            amount = Decimal(str(round(random.uniform(1, 1000), 2)))  # nosec

            txn = Transaction(
                account_id=acct.id,
                transaction_type=ttype,
                amount=amount,
                currency=acct.currency or "USD",
                status=status,
            )

            db.add(txn)
            created += 1

        db.commit()
        logger.info("seed_transactions_completed", created=created)

    except Exception as e:
        logger.error("seed_transactions_failed", error=str(e))
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed initial data into the database.")
    parser.add_argument(
        "--what",
        choices=["users", "failed_tasks", "transactions"],
        default="users",
        help="Which dataset to seed (default: users)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of items to create for datasets that accept a count (default: 5)",
    )

    args = parser.parse_args()

    logger.info("starting_database_seed", what=args.what)

    if args.what == "users":
        seed_users()
    elif args.what == "failed_tasks":
        seed_failed_tasks(count=args.count)
    elif args.what == "transactions":
        seed_transactions(count=args.count)
    else:
        seed_users()

    logger.info("database_seed_completed")
