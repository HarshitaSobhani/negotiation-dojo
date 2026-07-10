import os
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2:///negotiation_dojo")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    negotiations = relationship("Negotiation", back_populates="user")


class Negotiation(Base):
    __tablename__ = "negotiations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String, nullable=False)
    scenario_text = Column(Text, nullable=False)
    persona_target = Column(Numeric, nullable=False)
    persona_walk_away = Column(Numeric, nullable=False)
    persona_personality = Column(String, nullable=False)
    final_number = Column(Numeric)
    outcome = Column(String)
    debrief = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime)

    user = relationship("User", back_populates="negotiations")
    messages = relationship(
        "Message", back_populates="negotiation", order_by="Message.id",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    negotiation_id = Column(Integer, ForeignKey("negotiations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    negotiation = relationship("Negotiation", back_populates="messages")


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
