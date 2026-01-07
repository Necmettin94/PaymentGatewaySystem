from app.workers.base_task import DLQTask
from app.workers.celery_app import celery_app
from app.workers.strategies import DepositStrategy
from app.workers.transaction_processor import GenericTransactionProcessor

_processor = GenericTransactionProcessor(DepositStrategy())


@celery_app.task(
    bind=True,
    base=DLQTask,  # DLQ-aware task base class
    name="process_deposit",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_deposit(
    self,  # this is the task instance passed by Celery
    transaction_id: str,
    account_id: str,
    amount: str,
    user_id: str,
) -> dict:
    return _processor.process(
        task_instance=self,
        transaction_id=transaction_id,
        account_id=account_id,
        amount=amount,
        user_id=user_id,
    )
