from sqlalchemy.orm import Session
from aroot.repository.models import CustomersModel
from aroot.service.customers import Customer


class CustomersRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, customer):
        record = CustomersModel(**customer)
        self.session.add(record)
        return Customer(**record.dict())

    def _get(self, _id) -> CustomersModel:
        return self.session.query(CustomersModel).filter(CustomersModel.id == _id).first()

    def find_by_id(self, _id):
        customer = self._get(_id)
        if customer is not None:
            return Customer(**customer.dict())

    def find_by_email(self, email):
        query = self.session.query(CustomersModel)
        record = query.filter(CustomersModel.email == email).first()
        if record is not None:
            return Customer(**record.dict())

    def find_all(self, limit=None, offset=None):
        query = self.session.query(CustomersModel)
        records = query.limit(limit).offset(offset).all()
        return [Customer(**record.dict()) for record in records]

    def update(self, id_, **payload):
        record = self._get(id_)
        for key, val in payload.items():
            setattr(record, key, val)
        return Customer(**record.dict())

    def delete(self, _id):
        self.session.delete(self._get(_id))