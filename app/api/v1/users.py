from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.logging import get_logger
from app.domain.services.balance_service import BalanceService
from app.infrastructure.database.session import get_db
from app.infrastructure.models.user import User
from app.infrastructure.repositories.account_repository import AccountRepository
from app.infrastructure.repositories.transaction_repository import TransactionRepository
from app.schemas.account import BalanceResponse
from app.schemas.transaction import TransactionResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=dict)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat(),
    }


@router.get("/me/balance", response_model=BalanceResponse)
def get_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = BalanceService(db)
    try:
        balance_info = service.get_balance_by_user_id(current_user.id)

        return BalanceResponse(
            balance=balance_info["balance"],
            currency=balance_info["currency"],
            account_id=balance_info["account_id"],
        )
    except Exception as e:
        logger.error("balance_query_failed", user_id=str(current_user.id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get("/me/transactions", response_model=list[TransactionResponse])
def get_transactions(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account_repo = AccountRepository(db)
    account = account_repo.get_by_user_id(current_user.id)
    if not account:
        return []
    transaction_repo = TransactionRepository(db)
    transactions = transaction_repo.get_by_account_id(
        account_id=account.id,
        skip=skip,
        limit=min(limit, 100),
    )
    return [TransactionResponse.model_validate(transactio) for transactio in transactions]
