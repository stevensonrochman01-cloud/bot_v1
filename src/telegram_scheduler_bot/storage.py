from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, create_engine, select, text, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    pass


class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_time_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class MessageStorage:
    def initialize(self) -> None:
        Base.metadata.create_all(engine)
        self._upgrade_integer_columns()

    def _upgrade_integer_columns(self) -> None:
        if not settings.database_url.startswith("postgresql"):
            return

        statements = [
            "ALTER TABLE scheduled_messages ALTER COLUMN chat_id TYPE BIGINT",
            "ALTER TABLE scheduled_messages ALTER COLUMN user_id TYPE BIGINT",
        ]

        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def create_message(
        self,
        *,
        chat_id: int,
        user_id: int,
        message: str,
        scheduled_time_utc: datetime,
    ) -> int:
        with SessionLocal() as session:
            record = ScheduledMessage(
                chat_id=chat_id,
                user_id=user_id,
                message=message,
                scheduled_time_utc=scheduled_time_utc,
                status="pending",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record.id

    def list_pending_for_user(self, *, user_id: int) -> list[ScheduledMessage]:
        with SessionLocal() as session:
            return list(
                session.scalars(
                    select(ScheduledMessage)
                    .where(
                        ScheduledMessage.user_id == user_id,
                        ScheduledMessage.status == "pending",
                    )
                    .order_by(ScheduledMessage.scheduled_time_utc.asc())
                )
            )

    def delete_pending_message(self, *, message_id: int, user_id: int) -> bool:
        with SessionLocal() as session:
            record = session.scalar(
                select(ScheduledMessage).where(
                    ScheduledMessage.id == message_id,
                    ScheduledMessage.user_id == user_id,
                    ScheduledMessage.status == "pending",
                )
            )
            if record is None:
                return False

            session.delete(record)
            session.commit()
            return True

    def list_all_pending(self) -> list[ScheduledMessage]:
        with SessionLocal() as session:
            return list(
                session.scalars(
                    select(ScheduledMessage)
                    .where(ScheduledMessage.status == "pending")
                    .order_by(ScheduledMessage.scheduled_time_utc.asc())
                )
            )

    def update_status(self, *, message_id: int, status: str) -> None:
        values: dict[str, object] = {"status": status}
        if status == "sent":
            values["sent_at"] = datetime.utcnow()

        with SessionLocal() as session:
            session.execute(
                update(ScheduledMessage)
                .where(ScheduledMessage.id == message_id)
                .values(**values)
            )
            session.commit()
