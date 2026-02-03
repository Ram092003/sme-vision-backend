from sqlalchemy import Column, Integer, Float, String, Date
from database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date)
    industry = Column(String(100))
    category = Column(String(100))
    amount = Column(Float)
    type = Column(String(20))