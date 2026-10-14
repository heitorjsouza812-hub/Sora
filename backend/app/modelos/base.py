"""Base declarativa SQLAlchemy 2; especificação §§1 e 8.4."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base comum de todas as tabelas persistidas pela Sora."""
