from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.config import settings
from app.core.logging import get_logger
from app.core.security import create_access_token, verify_password
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.models import Account, Transaction, User
from app.infrastructure.models.failed_task import FailedTask

logger = get_logger(__name__)


class AdminAuthBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = form.get("username")
        password = form.get("password")

        if not isinstance(email, str) or not isinstance(password, str):
            return False

        db = SessionLocal()
        try:
            # it can be converted async if needed. right now it is sync for simplicity
            user = db.query(User).filter(User.email == email).first()

            if not user:
                logger.warning("admin_login_failed", reason="user_not_found", email=email)
                return False

            if not verify_password(password, user.hashed_password):
                logger.warning("admin_login_failed", reason="invalid_password", email=email)
                return False

            admin_emails = settings.admin_emails
            if email not in admin_emails:
                logger.warning("admin_access_denied", email=email, reason="Not in admin whitelist")
                return False

            token_data = {
                "sub": str(user.id),
                "email": user.email,
            }
            token = create_access_token(token_data)
            request.session.update({"token": token, "user_id": str(user.id)})

            logger.info("admin_login_success", email=email)
            return True

        except Exception as e:
            logger.error("admin_login_error", error=str(e))
            return False
        finally:
            db.close()

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        return token is not None


class UserAdmin(ModelView, model=User):  # type: ignore
    name = "User"
    name_plural = "Users"

    column_list = ["id", "email", "full_name", "is_active", "created_at"]
    column_searchable_list = ["email", "full_name"]
    column_sortable_list = ["email", "created_at"]
    column_default_sort = [("created_at", True)]

    column_details_exclude_list = ["hashed_password"]
    form_excluded_columns = ["hashed_password", "account"]

    can_create = False
    can_edit = True
    can_delete = False
    can_view_details = True


class AccountAdmin(ModelView, model=Account):  # type: ignore
    name = "Account"
    name_plural = "Accounts"

    column_list = ["id", "user_id", "balance", "currency", "created_at", "updated_at"]
    column_searchable_list = ["id", "user_id"]
    column_sortable_list = ["balance", "created_at"]
    column_default_sort = [("created_at", True)]

    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True


class TransactionAdmin(ModelView, model=Transaction):  # type: ignore
    name = "Transaction"
    name_plural = "Transactions"

    column_list = [
        "id",
        "account_id",
        "transaction_type",
        "amount",
        "currency",
        "status",
        "error_code",
        "created_at",
    ]

    column_searchable_list = ["id", "account_id", "bank_transaction_id"]
    column_sortable_list = ["created_at", "amount", "status"]
    column_default_sort = [("created_at", True)]

    column_details_list = [
        "id",
        "account_id",
        "transaction_type",
        "amount",
        "currency",
        "status",
        "bank_transaction_id",
        "bank_response",
        "error_code",
        "error_message",
        "idempotency_key",
        "celery_task_id",
        "created_at",
        "updated_at",
    ]

    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True


# class ReviewTransactionAdmin(ModelView, model=Transaction):
#     name = "Review"
#     name_plural = "Reviews"
#
#     column_list = [
#         "id",
#         "transaction_type",
#         "amount",
#         "error_code",
#         "error_message",
#         "created_at",
#         "status",
#     ]
#
#     column_sortable_list = ["created_at"]
#     column_default_sort = [("created_at", False)]
#
#     column_details_list = [
#         "id",
#         "account_id",
#         "transaction_type",
#         "amount",
#         "currency",
#         "status",
#         "bank_transaction_id",
#         "bank_response",
#         "error_code",
#         "error_message",
#         "celery_task_id",
#         "created_at",
#         "updated_at",
#     ]
#
#     can_create = False
#     can_edit = False
#     can_delete = False
#     can_view_details = True


class FailedTaskAdmin(ModelView, model=FailedTask):  # type: ignore
    name = "Failed Task (DLQ)"
    name_plural = "Failed Tasks (DLQ)"

    column_list = [
        "id",
        "task_name",
        "exception_type",
        "failed_at",
        "retry_count",
        "replayed_at",
        "replay_status",
    ]

    column_searchable_list = ["task_id", "task_name", "exception_type"]
    column_sortable_list = ["failed_at", "task_name"]
    column_default_sort = [("failed_at", True)]

    column_details_list = [
        "id",
        "task_id",
        "task_name",
        "args",
        "kwargs",
        "exception_type",
        "exception_message",
        "traceback",
        "retry_count",
        "failed_at",
        "replayed_at",
        "replay_status",
        "replay_notes",
        "created_at",
    ]

    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = True


def setup_admin(app, engine) -> Admin:
    authentication_backend = AdminAuthBackend(secret_key=settings.jwt_secret_key)
    admin = Admin(
        app,
        engine,
        title="Payment Gateway Admin - (admin@example.com / admin123)",
        base_url="/admin",
        authentication_backend=authentication_backend,
    )
    admin.add_view(UserAdmin)
    admin.add_view(AccountAdmin)
    admin.add_view(TransactionAdmin)
    admin.add_view(FailedTaskAdmin)

    logger.info("admin_panel_initialized", base_url="/admin")

    return admin
