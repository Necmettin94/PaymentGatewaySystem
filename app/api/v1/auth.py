from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import TOKEN_TYPE_BEARER
from app.core.logging import get_logger
from app.domain.services.auth_service import AuthService
from app.infrastructure.database.session import get_db
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    service = AuthService(db)

    try:
        user = service.register_user(
            email=str(user_data.email),
            full_name=user_data.full_name,
            password=user_data.password,
            webhook_url=user_data.webhook_url,
        )
        token = service.create_token(user)
        return TokenResponse(
            access_token=token,
            token_type=TOKEN_TYPE_BEARER,
            user=UserResponse.model_validate(user),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: UserLogin,
    db: Session = Depends(get_db),
):
    service = AuthService(db)

    user = service.authenticate(
        email=str(credentials.email),
        password=credentials.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = service.create_token(user)

    return TokenResponse(
        access_token=token,
        token_type=TOKEN_TYPE_BEARER,
        user=UserResponse.model_validate(user),
    )
