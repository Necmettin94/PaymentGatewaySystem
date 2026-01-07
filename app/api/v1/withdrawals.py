from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_current_user_account
from app.api.v1.utils.transaction_utils import (
    create_transaction,
    get_user_transaction,
    list_account_transactions,
)
from app.core.enums import TransactionType
from app.core.logging import get_logger
from app.domain.exceptions import InsufficientBalanceError
from app.domain.services.withdrawal_service import WithdrawalService
from app.infrastructure.database.session import get_db
from app.infrastructure.models.account import Account
from app.infrastructure.models.user import User
from app.schemas.transaction import TransactionResponse, WithdrawalCreate, WithdrawalResponse
from app.workers.tasks.withdrawal_tasks import process_withdrawal

logger = get_logger(__name__)

router = APIRouter(prefix="/withdrawals", tags=["Withdrawals"])


@router.post("", response_model=WithdrawalResponse, status_code=status.HTTP_202_ACCEPTED)
def create_withdrawal(
    withdrawal_data: WithdrawalCreate,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user_account),
    current_user: User = Depends(get_current_user),
):
    service = WithdrawalService(db)

    try:
        return create_transaction(
            db=db,
            account=account,
            current_user=current_user,
            transaction_data=withdrawal_data,
            create_transaction_func=lambda: service.create_pending_withdrawal(
                account_id=account.id,
                amount=withdrawal_data.amount,
                currency=withdrawal_data.currency,
            ),
            task_function=process_withdrawal.delay,
            transaction_type_name="withdrawal",
            response_class=WithdrawalResponse,
        )
    except InsufficientBalanceError as e:
        logger.warning(
            "withdrawal_insufficient_balance",
            user_id=str(current_user.id),
            requested_amount=str(withdrawal_data.amount),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("/{withdrawal_id}", response_model=TransactionResponse)
def get_withdrawal(
    withdrawal_id: UUID,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user_account),
):
    transaction = get_user_transaction(
        transaction_id=withdrawal_id,
        account=account,
        db=db,
        transaction_type_name="withdrawal",
    )

    return TransactionResponse.model_validate(transaction)


@router.get("", response_model=list[TransactionResponse])
def list_withdrawals(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user_account),
):
    return list_account_transactions(
        account=account,
        db=db,
        transaction_type=TransactionType.WITHDRAWAL,
        skip=skip,
        limit=limit,
    )
