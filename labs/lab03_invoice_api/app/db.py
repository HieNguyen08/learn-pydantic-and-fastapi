"""Tầng persistence: SQLAlchemy 2.x async + SQLite (aiosqlite). Module 10."""
import os
from typing import AsyncIterator

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./invoices.db")


class Base(DeclarativeBase):
    pass


class Series(Base):
    __tablename__ = "series"
    tenant_id: Mapped[int] = mapped_column(primary_key=True)
    series: Mapped[str] = mapped_column(String(10), primary_key=True)
    last_number: Mapped[int] = mapped_column(default=0)


class InvoiceRow(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("tenant_id", "series", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    series: Mapped[str] = mapped_column(String(10))
    number: Mapped[int | None]                     # NULL trong lúc tạo, cấp số cuối transaction (UNIQUE bỏ qua NULL)
    seller_tax_code: Mapped[str] = mapped_column(String(13))
    buyer_name: Mapped[str] = mapped_column(String(400))
    total_before_tax: Mapped[int] = mapped_column(BigInteger)
    total_tax: Mapped[int] = mapped_column(BigInteger)
    total: Mapped[int] = mapped_column(BigInteger)
    lines: Mapped[list["LineRow"]] = relationship(back_populates="invoice", lazy="raise", cascade="all")


class LineRow(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    name: Mapped[str] = mapped_column(String(500))
    quantity = mapped_column(Numeric(19, 4))
    unit_price: Mapped[int] = mapped_column(BigInteger)
    vat_rate: Mapped[str] = mapped_column(String(5))
    amount: Mapped[int] = mapped_column(BigInteger)
    invoice: Mapped[InvoiceRow] = relationship(back_populates="lines")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    tenant_id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(String)


def make_engine(url: str = DATABASE_URL) -> AsyncEngine:
    # timeout: chờ khóa ghi của SQLite thay vì lỗi "database is locked" khi nhiều request ghi cùng lúc
    return create_async_engine(url, connect_args={"timeout": 30})


async def create_schema(engine: AsyncEngine, tenants=(1, 2, 3)):
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as s, s.begin():
        for t in tenants:
            if await s.get(Series, (t, "1C26TMK")) is None:
                s.add(Series(tenant_id=t, series="1C26TMK"))


class Database:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as s, s.begin():          # commit khi thoát, rollback khi lỗi
            yield s
