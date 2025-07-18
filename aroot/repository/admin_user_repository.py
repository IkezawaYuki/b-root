from sqlalchemy.orm import Session
from repository.models import AdminUsersModel
from domain.admin_users import AdminUser
from sqlalchemy import func


class AdminUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def _get(self, _id) -> AdminUsersModel | None:
        return (
            self.session.query(AdminUsersModel)
            .filter(AdminUsersModel.id == _id)
            .first()
        )

    def add(self, admin_user):
        record = AdminUsersModel(**admin_user)
        self.session.add(record)
        return AdminUser(**record.dict())

    def find_by_id(self, id):
        record = (
            self.session.query(AdminUsersModel).filter(AdminUsersModel.id == id).first()
        )
        if record is not None:
            return AdminUser(**record.dict())

    def find_by_email(self, email):
        query = self.session.query(AdminUsersModel)
        record = query.filter(AdminUsersModel.email == email).first()
        if record is not None:
            return AdminUser(**record.dict())
        return None

    def find_all(self, limit=None, offset=None):
        query = self.session.query(AdminUsersModel)
        records = query.limit(limit).offset(offset).all()
        return [AdminUser(**record.dict()) for record in records]

    def delete(self, _id):
        self.session.delete(self._get(_id))

    def count(self):
        return self.session.query(func.count(AdminUsersModel.id)).scalar()
