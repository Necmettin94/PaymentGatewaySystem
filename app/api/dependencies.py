from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.infrastructure.database.session import get_db
from app.infrastructure.models.account import Account
from app.infrastructure.models.user import User
from app.infrastructure.repositories.account_repository import AccountRepository
from app.infrastructure.repositories.user_repository import UserRepository

logger = get_logger(__name__)

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    payload = decode_access_token(token)
    if payload is None:
        logger.warning("invalid_token", token_prefix=token[:20])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(user_id_str)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
        ) from e

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)

    if user is None:
        logger.warning("user_not_found_in_token", user_id=user_id_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        logger.warning("inactive_user_login_attempt", user_id=user_id_str)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


def get_current_user_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Account:
    account_repo = AccountRepository(db)
    account = account_repo.get_by_user_id(current_user.id)

    if not account:
        logger.error(
            "account_not_found_for_user",
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    return account
