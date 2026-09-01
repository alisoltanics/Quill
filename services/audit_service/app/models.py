from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from .database import Base


class AuditActivity(Base):
    __tablename__ = "audit_activity"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    user_name = Column(String(255), nullable=False)
    action = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False)
    client_id = Column(String(128), nullable=True)
    event_timestamp = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
