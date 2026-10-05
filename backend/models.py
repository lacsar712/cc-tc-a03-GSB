import os
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    """进队记录：测量员一次报送一行，与补偿账同生共死。"""

    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)  # 原始读数，永不改写
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    temp_now_c: Mapped[float | None] = mapped_column(Float, nullable=True)  # 当时洞温
    drift_mm: Mapped[float | None] = mapped_column(Float, nullable=True)  # 温漂，后台回填
    corrected_mm: Mapped[float | None] = mapped_column(Float, nullable=True)  # 扣漂后毫米
    online_mm: Mapped[float | None] = mapped_column(Float, nullable=True)  # 在线展示数字，可事后改
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ledger: Mapped["CompensationLedger"] = relationship(back_populates="log", uselist=False)
    revisions: Mapped[list["DisplayRevision"]] = relationship(
        back_populates="log", order_by="DisplayRevision.id"
    )


class CompensationLedger(Base):
    """补偿账：报送当时落下的不可变快照，只有后台能回填扣漂结果，谁都不能改。"""

    __tablename__ = "compensation_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_id: Mapped[int] = mapped_column(
        ForeignKey("convergence_logs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    coeff_k: Mapped[float] = mapped_column(Float, nullable=False)  # 温度系数 mm/℃
    baseline_temp_c: Mapped[float] = mapped_column(Float, nullable=False)  # 基准洞温
    measured_temp_c: Mapped[float] = mapped_column(Float, nullable=False)  # 当时洞温
    drift_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_mm: Mapped[float] = mapped_column(Float, nullable=False)
    corrected_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    log: Mapped[ConvergenceLog] = relationship(back_populates="ledger")


class DisplayRevision(Base):
    """在线展示改数留痕：账里的旧值不靠回忆，每一改都单独可翻。"""

    __tablename__ = "display_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_id: Mapped[int] = mapped_column(
        ForeignKey("convergence_logs.id", ondelete="CASCADE"), nullable=False
    )
    old_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_mm: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_by: Mapped[str] = mapped_column(String, nullable=False)
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    log: Mapped[ConvergenceLog] = relationship(back_populates="revisions")


def _iso(value):
    return value.isoformat() if value else None


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "temp_now_c": row.temp_now_c,
        "drift_mm": row.drift_mm,
        "corrected_mm": row.corrected_mm,
        "online_mm": row.online_mm if row.online_mm is not None else row.corrected_mm,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
        "processed_at": _iso(row.processed_at),
        "revisions": [
            {
                "id": r.id,
                "old_mm": r.old_mm,
                "new_mm": r.new_mm,
                "note": r.note,
                "edited_by": r.edited_by,
                "edited_at": _iso(r.edited_at),
            }
            for r in row.revisions
        ],
    }


def ledger_dict(row: CompensationLedger) -> dict:
    return {
        "id": row.id,
        "log_id": row.log_id,
        "chainage": row.log.chainage,
        "coeff_k": row.coeff_k,
        "baseline_temp_c": row.baseline_temp_c,
        "measured_temp_c": row.measured_temp_c,
        "drift_mm": row.drift_mm,
        "raw_mm": row.raw_mm,
        "corrected_mm": row.corrected_mm,
        "verdict": row.log.verdict,
        "status": row.log.status,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
    }
