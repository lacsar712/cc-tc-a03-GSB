"""进程内认领：同一 Flask 进程后台线程抢 pending，不另起容器。

抢到后用补偿账里报送当时记下的系数与洞温快照算扣漂，再按 ±3.0 mm 下结论。
"""
import threading
import time
from datetime import datetime, timezone

from models import ConvergenceLog, SessionLocal
from rules import compensate, judge

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

        ledger = row.ledger
        # 进队记录与补偿账原子同生；缺账说明数据被人动过，行保持 pending 等人查。
        if ledger is None:
            db.commit()
            print(f"claimer: log {row.id} 缺补偿账，跳过", flush=True)
            return False

        drift, corrected = compensate(
            float(row.delta_mm),
            float(ledger.coeff_k),
            float(ledger.baseline_temp_c),
            float(ledger.measured_temp_c),
        )
        verdict, reason = judge(corrected)

        row.drift_mm = drift
        row.corrected_mm = corrected
        row.status = "done"
        row.verdict = verdict
        row.reason = (
            f"{reason}（洞温 {ledger.measured_temp_c:g}℃ 相对基准 "
            f"{ledger.baseline_temp_c:g}℃，系数 {ledger.coeff_k:g}，扣漂移 {drift} mm）"
        )
        row.processed_at = datetime.now(timezone.utc)

        ledger.drift_mm = drift
        ledger.corrected_mm = corrected

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
