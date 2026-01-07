from collections.abc import Callable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.enums import TransactionType
from app.core.logging import get_logger
from app.domain.exceptions import InsufficientBalanceError
from app.infrastructure.models.account import Account
from app.infrastructure.models.transaction import Transaction
from app.infrastructure.models.user import User
from app.infrastructure.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import (
    DepositCreate,
    DepositResponse,
    TransactionResponse,
    WithdrawalCreate,
    WithdrawalResponse,
)

logger = get_logger(__name__)


def get_user_transaction(
    transaction_id: UUID,
    account: Account,
    db: Session,
    transaction_type_name: str = "transaction",
) -> Transaction:
    transaction_repo = TransactionRepository(db)
    transaction = transaction_repo.get_by_id(transaction_id)

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{transaction_type_name.capitalize()} not found",
        )

    if transaction.account_id != account.id:
        logger.warning(
            "unauthorized_transaction_access_attempt",
            transaction_id=str(transaction_id),
            account_id=str(account.id),
            transaction_account_id=str(transaction.account_id),
            type=transaction_type_name,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to access this {transaction_type_name}",
        )

    return transaction


def list_account_transactions(
    account: Account,
    db: Session,
    transaction_type: TransactionType,
    skip: int = 0,
    limit: int = 20,
    max_limit: int = 100,
) -> list[TransactionResponse]:
    transaction_repo = TransactionRepository(db)
    transactions = transaction_repo.get_by_account_id(
        account_id=account.id,
        skip=skip,
        limit=min(limit, max_limit),
        transaction_type=transaction_type,
    )

    return [TransactionResponse.model_validate(t) for t in transactions]


def create_transaction(
    db: Session,
    account: Account,
    current_user: User,
    transaction_data: DepositCreate | WithdrawalCreate,
    create_transaction_func: Callable,
    task_function: Callable,
    transaction_type_name: str,
    response_class: type[DepositResponse] | type[WithdrawalResponse],
) -> DepositResponse | WithdrawalResponse:
    try:
        transaction = create_transaction_func()
        db.commit()
        db.refresh(transaction)

        task = task_function(
            transaction_id=str(transaction.id),
            account_id=str(account.id),
            amount=str(transaction_data.amount),
            user_id=str(current_user.id),
        )

        transaction.celery_task_id = task.id
        db.commit()

        logger.info(
            f"{transaction_type_name}_request_accepted",
            transaction_id=str(transaction.id),
            task_id=task.id,
            amount=str(transaction_data.amount),
        )

        response = response_class.model_validate(transaction)
        response.message = (
            f"{transaction_type_name.capitalize()} request accepted and is being processed"
        )

        return response

    except InsufficientBalanceError:
        raise
    except Exception as e:
        logger.error(f"{transaction_type_name}_creation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create {transaction_type_name}: {str(e)}",
        ) from e
