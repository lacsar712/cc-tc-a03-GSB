"""进程内认领：同一 Flask 进程后台线程抢 pending，按补偿账里的扣漂后毫米出结论。"""
import threading
import time
from datetime import datetime, timezone

from models import CompensationLedger, ConvergenceLog, SessionLocal
from rules import judge

_stop = threading.Event()


def claim_once() -> bool:
    db = SessionLocal()
    try:
        row = (
            db.query(ConvergenceLog)
            .filter(ConvergenceLog.status == "pending")
            .order_by(ConvergenceLog.id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            db.commit()
            return False
        ledger = (
            db.query(CompensationLedger)
            .filter(CompensationLedger.log_id == row.id)
            .first()
        )
        now = datetime.now(timezone.utc)
        if ledger is None:
            # 进队记录和补偿账本应一起落库；缺账说明两边不齐，不能硬判
            row.status = "done"
            row.verdict = "异常"
            row.reason = "补偿账里找不到对应记录，无法判定"
        else:
            verdict, reason = judge(float(ledger.compensated_mm))
            row.status = "done"
            row.verdict = verdict
            row.reason = reason
            ledger.verdict = verdict
        row.processed_at = now
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def loop():
    while not _stop.is_set():
        try:
            if claim_once():
                time.sleep(0.4)
            else:
                time.sleep(1.0)
        except Exception as exc:
            print(f"claimer error: {exc}", flush=True)
            time.sleep(1.0)


def start():
    t = threading.Thread(target=loop, name="convergence-claimer", daemon=True)
    t.start()
