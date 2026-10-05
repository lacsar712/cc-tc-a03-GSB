import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompensationSetting(Base):
    """补偿系数与基准洞温，全局单行，只允许测量员改。"""

    __tablename__ = "compensation_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TemperatureReading(Base):
    """洞温流水：测量员登记的洞内温度，提交测量时取最新一条。"""

    __tablename__ = "temperature_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompensationLedger(Base):
    """补偿账：提交那一刻与进队记录同一事务落账。

    原始值、当时洞温、系数、基准洞温、扣漂后值都定格在这里；
    事后有人在总表改在线展示数字，这里当时记下的旧值不变，可单独翻。
    """

    __tablename__ = "compensation_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_id: Mapped[int] = mapped_column(
        ForeignKey("convergence_logs.id"), nullable=False, unique=True
    )
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    raw_mm: Mapped[float] = mapped_column(Float, nullable=False)
    temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    drift_mm: Mapped[float] = mapped_column(Float, nullable=False)
    compensated_mm: Mapped[float] = mapped_column(Float, nullable=False)
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def settings_dict(s: CompensationSetting) -> dict:
    return {
        "id": s.id,
        "coefficient": s.coefficient,
        "baseline_temp_c": s.baseline_temp_c,
        "updated_by": s.updated_by,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def temp_dict(t: TemperatureReading) -> dict:
    return {
        "id": t.id,
        "temp_c": t.temp_c,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def ledger_dict(e: CompensationLedger) -> dict:
    return {
        "id": e.id,
        "log_id": e.log_id,
        "chainage": e.chainage,
        "raw_mm": e.raw_mm,
        "temp_c": e.temp_c,
        "coefficient": e.coefficient,
        "baseline_temp_c": e.baseline_temp_c,
        "drift_mm": e.drift_mm,
        "compensated_mm": e.compensated_mm,
        "verdict": e.verdict,
        "created_by": e.created_by,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
