from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import create_access_token, get_password_hash, verify_password
from app.infrastructure.models.account import Account
from app.infrastructure.models.user import User
from app.infrastructure.repositories.account_repository import AccountRepository
from app.infrastructure.repositories.user_repository import UserRepository

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.account_repo = AccountRepository(db)

    def register_user(
        self,
        email: str,
        full_name: str,
        password: str,
        webhook_url: str | None = None,
    ) -> User:
        existing_user = self.user_repo.get_by_email(email)
        if existing_user:
            raise ValueError(f"User with email {email} already exists")

        hashed_password = get_password_hash(password)

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            is_active=True,
            webhook_url=webhook_url,
        )
        created_user = self.user_repo.create(user)
        self.db.flush()

        account = Account(
            user_id=created_user.id,
            balance=0,
            currency="USD",
        )
        self.account_repo.create(account)

        self.db.commit()
        self.db.refresh(created_user)

        logger.info(
            "user_registered",
            user_id=str(created_user.id),
            email=email,
            account_id=str(account.id),
        )

        return created_user

    def authenticate(
        self,
        email: str,
        password: str,
    ) -> User | None:
        user = self.user_repo.get_by_email(email)
        if not user:
            logger.warning("authentication_failed", email=email, reason="user_not_found")
            return None

        if not user.is_active:
            logger.warning("authentication_failed", email=email, reason="user_inactive")
            return None

        if not verify_password(password, str(user.hashed_password)):
            logger.warning("authentication_failed", email=email, reason="invalid_password")
            return None

        logger.info("authentication_success", user_id=str(user.id), email=email)
        return user

    @staticmethod
    def create_token(user: User) -> str:
        token_data = {
            "sub": str(user.id),
            "email": user.email,
        }
        return create_access_token(token_data)
