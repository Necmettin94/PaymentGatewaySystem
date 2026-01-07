from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.config import settings
from app.core.enums import BankResponseStatus, TransactionType
from app.core.logging import get_logger
from app.core.security import verify_webhook_signature
from app.domain.services.deposit_service import DepositService
from app.domain.services.withdrawal_service import WithdrawalService
from app.infrastructure.database.session import get_db
from app.infrastructure.models.user import User
from app.infrastructure.repositories.account_repository import AccountRepository
from app.infrastructure.repositories.transaction_repository import TransactionRepository
from app.infrastructure.repositories.webhook_repository import WebhookRepository
from app.schemas.webhook import (
    BankCallbackPayload,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
    WebhookResponse,
)

logger = get_logger(__name__)
MAX_TIMESTAMP_DIFF = 300  # 5 minutes

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/bank-callback", response_model=WebhookResponse)
async def bank_callback(
    payload: BankCallbackPayload,
    request: Request,
    x_bank_signature: str = Header(..., description="HMAC-SHA256 signature of the request body"),
    db: Session = Depends(get_db),
):

    current_timestamp = int(datetime.now(UTC).timestamp())
    time_diff = abs(
        current_timestamp - payload.timestamp
    )  # I'm not sure do we need abs() here, but just in case. check later.

    if time_diff > MAX_TIMESTAMP_DIFF:
        logger.warning(
            "webhook_timestamp_invalid",
            transaction_id=str(payload.transaction_id),
            payload_timestamp=payload.timestamp,
            current_timestamp=current_timestamp,
            diff_seconds=time_diff,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook timestamp too old or in future. Time difference: {time_diff}s (max: {MAX_TIMESTAMP_DIFF}s)",
        )

    request_body = await request.body()
    is_valid = verify_webhook_signature(
        payload=request_body.decode("utf-8"),
        signature=x_bank_signature,
        secret=settings.bank_webhook_secret,
    )

    if not is_valid:
        logger.warning(
            "webhook_signature_invalid",
            transaction_id=str(payload.transaction_id),
            provided_signature=x_bank_signature,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    logger.info(
        "webhook_received",
        transaction_id=str(payload.transaction_id),
        bank_status=payload.status,
        timestamp=payload.timestamp,
    )

    try:
        transaction_repo = TransactionRepository(db)
        transaction = transaction_repo.get_by_id(payload.transaction_id)

        if not transaction:
            logger.error(
                "webhook_transaction_not_found",
                transaction_id=str(payload.transaction_id),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction {payload.transaction_id} not found",
            )

        if transaction.transaction_type == TransactionType.DEPOSIT:
            deposit_service = DepositService(db)
            if payload.status == BankResponseStatus.SUCCESS:
                deposit_service.complete_deposit(
                    transaction_id=payload.transaction_id,
                    bank_transaction_id=payload.bank_transaction_id or "UNKNOWN",
                    bank_response=payload.message,
                )
                logger.info("webhook_deposit_completed", transaction_id=str(payload.transaction_id))
            else:
                deposit_service.fail_deposit(
                    transaction_id=payload.transaction_id,
                    error_code=payload.error_code or "BANK_ERROR",
                    error_message=payload.message or "Bank processing failed",
                    bank_response=str(payload),
                )
                logger.info("webhook_deposit_failed", transaction_id=str(payload.transaction_id))

        elif transaction.transaction_type == TransactionType.WITHDRAWAL:
            withdrawal_service = WithdrawalService(db)
            if payload.status == BankResponseStatus.SUCCESS:
                withdrawal_service.complete_withdrawal(
                    transaction_id=payload.transaction_id,
                    bank_transaction_id=payload.bank_transaction_id or "UNKNOWN",
                    bank_response=payload.message,
                )
                logger.info(
                    "webhook_withdrawal_completed", transaction_id=str(payload.transaction_id)
                )
            else:
                withdrawal_service.fail_withdrawal(
                    transaction_id=payload.transaction_id,
                    error_code=payload.error_code or "BANK_ERROR",
                    error_message=payload.message or "Bank processing failed",
                    bank_response=str(payload),
                )
                logger.info("webhook_withdrawal_failed", transaction_id=str(payload.transaction_id))

        else:
            logger.error(
                "webhook_unknown_transaction_type",
                transaction_id=str(payload.transaction_id),
                transaction_type=transaction.transaction_type,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown transaction type: {transaction.transaction_type}",
            )

        return WebhookResponse(
            received=True,
            message="Webhook received and processed successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "webhook_processing_failed",
            transaction_id=str(payload.transaction_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook: {str(e)}",
        ) from e


@router.get("/deliveries", response_model=WebhookDeliveryListResponse)
def get_webhook_deliveries(
    transaction_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    webhook_repo = WebhookRepository(db)

    if transaction_id:
        transaction_repo = TransactionRepository(db)
        transaction = transaction_repo.get_by_id(transaction_id)
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found",
            )

        account_repo = AccountRepository(db)
        account = account_repo.get_by_id(transaction.account_id)

        if not account or account.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this transaction's webhooks",
            )

        deliveries = webhook_repo.get_by_transaction_id(transaction_id)
    else:

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(current_user.id)

        if not account:
            return WebhookDeliveryListResponse(deliveries=[], total=0)

        transaction_repo = TransactionRepository(db)
        transactions = db.query(transaction_repo.model).filter_by(account_id=account.id).all()

        all_deliveries = []
        for transaction in transactions:
            deliveries_for_tx = webhook_repo.get_by_transaction_id(transaction.id)
            all_deliveries.extend(deliveries_for_tx)

        deliveries = all_deliveries

    return WebhookDeliveryListResponse(
        deliveries=[WebhookDeliveryResponse.model_validate(d) for d in deliveries],
        total=len(deliveries),
    )


@router.get("/deliveries/{delivery_id}", response_model=WebhookDeliveryResponse)
def get_webhook_delivery(
    delivery_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    webhook_repo = WebhookRepository(db)
    delivery = webhook_repo.get_by_id(delivery_id)

    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook delivery not found",
        )

    transaction_repo = TransactionRepository(db)
    transaction = transaction_repo.get_by_id(delivery.transaction_id)

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    account_repo = AccountRepository(db)
    account = account_repo.get_by_id(transaction.account_id)

    if not account or account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this webhook delivery",
        )

    return WebhookDeliveryResponse.model_validate(delivery)
