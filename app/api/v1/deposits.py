from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_current_user_account
from app.api.v1.utils.transaction_utils import (
    create_transaction,
    get_user_transaction,
    list_account_transactions,
)
from app.core.enums import TransactionType
from app.core.logging import get_logger
from app.domain.services.deposit_service import DepositService
from app.infrastructure.database.session import get_db
from app.infrastructure.models.account import Account
from app.infrastructure.models.user import User
from app.schemas.transaction import DepositCreate, DepositResponse, TransactionResponse
from app.workers.tasks.deposit_tasks import process_deposit

logger = get_logger(__name__)

router = APIRouter(prefix="/deposits", tags=["Deposits"])


@router.post("", response_model=DepositResponse, status_code=status.HTTP_202_ACCEPTED)
def create_deposit(
    deposit_data: DepositCreate,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user_account),
    current_user: User = Depends(get_current_user),
):
    service = DepositService(db)

    return create_transaction(
        db=db,
        account=account,
        current_user=current_user,
        transaction_data=deposit_data,
        create_transaction_func=lambda: service.create_pending_deposit(
            account_id=account.id,
            amount=deposit_data.amount,
            currency=deposit_data.currency,
        ),
        task_function=process_deposit.delay,
        transaction_type_name="deposit",
        response_class=DepositResponse,
    )


@router.get("/{deposit_id}", response_model=TransactionResponse)
def get_deposit(
    deposit_id: UUID,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user_account),
):
    transaction = get_user_transaction(
        transaction_id=deposit_id,
        account=account,
        db=db,
        transaction_type_name="deposit",
    )

    return TransactionResponse.model_validate(transaction)


@router.get("", response_model=list[TransactionResponse])
def list_deposits(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user_account),
):
    return list_account_transactions(
        account=account,
        db=db,
        transaction_type=TransactionType.DEPOSIT,
        skip=skip,
        limit=limit,
    )
