from fastapi import APIRouter

from app.api.v1 import auth, deposits, users, withdrawals

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(deposits.router)
api_router.include_router(withdrawals.router)
api_router.include_router(users.router)
