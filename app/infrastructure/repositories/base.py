from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.database.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get_by_id(self, id: UUID) -> ModelType | None:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_by_id_with_lock(self, id: UUID) -> ModelType | None:
        return self.db.query(self.model).filter(self.model.id == id).with_for_update().first()

    def create(self, obj: ModelType) -> ModelType:
        self.db.add(obj)
        self.db.flush()  # Get ID without committing
        self.db.refresh(obj)
        return obj

    def update(self, obj: ModelType) -> ModelType:
        self.db.add(obj)
        self.db.flush()
        self.db.refresh(obj)
        return obj
