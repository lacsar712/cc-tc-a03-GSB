import math
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from claimer import start as start_claimer
from models import (
    Base,
    CompensationLedger,
    ConvergenceLog,
    DisplayRevision,
    SessionLocal,
    engine,
    ledger_dict,
    row_dict,
)
from rules import (
    CompensationError,
    compensate,
    judge,
    validate_coeff,
    validate_temp,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        # (桩号, 原始读数, 系数, 基准洞温, 当时洞温, 期望结论)
        seeds = (
            ("K12+180", 1.2, 0.05, 15.0, 15.0, "合格"),
            ("K18+040", 5.6, 0.05, 15.0, 25.0, "超限"),
        )
        for chainage, raw, k, t0, t1, expect in seeds:
            drift, corrected = compensate(raw, k, t0, t1)
            verdict, reason = judge(corrected)
            assert verdict == expect
            row = ConvergenceLog(
                chainage=chainage,
                delta_mm=raw,
                status="done",
                verdict=verdict,
                reason=f"{reason}（种子：洞温 {t1:g}℃、基准 {t0:g}℃、系数 {k:g}）",
                temp_now_c=t1,
                drift_mm=drift,
                corrected_mm=corrected,
                created_by="surveyor",
                created_at=now,
                processed_at=now,
            )
            db.add(row)
            db.flush()
            db.add(
                CompensationLedger(
                    log_id=row.id,
                    coeff_k=k,
                    baseline_temp_c=t0,
                    measured_temp_c=t1,
                    drift_mm=drift,
                    raw_mm=raw,
                    corrected_mm=corrected,
                    created_by="surveyor",
                    created_at=now,
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "巡检员只读：能翻表翻账，不能报送或改数"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def parse_number(body, key, label, required=True):
    """返回 float；缺料/不是数字时抛 CompensationError，文案直接给测量员看。"""
    value = body.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise CompensationError(f"{label}没填，退回补填后再提交")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CompensationError(f"{label}必须是数字，收到的是 {value!r}")
    if not math.isfinite(number):
        raise CompensationError(f"{label}必须是正常数字，不能是无穷或空值")
    return number


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.get("/api/ledger")
@require_login
def list_ledger():
    """补偿账流水：测量员、巡检员都能翻，谁都不能从这条路上改。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(CompensationLedger)
            .order_by(CompensationLedger.id.desc())
            .all()
        )
        return jsonify([ledger_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/logs")
@require_writer
def create_log():
    """进队记录与补偿账同一事务提交；任一边不齐整单退回，不留半截账。"""
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空，退回补填"}), 400

    try:
        raw_mm = parse_number(body, "delta_mm", "测缝原始读数（毫米）")
        coeff_k = parse_number(body, "coeff_k", "温度系数")
        baseline_temp_c = parse_number(body, "baseline_temp_c", "基准洞温")
        measured_temp_c = parse_number(body, "measured_temp_c", "当时洞温")
        validate_coeff(coeff_k)
        validate_temp("基准洞温", baseline_temp_c)
        validate_temp("当时洞温", measured_temp_c)
    except CompensationError as exc:
        return jsonify({"detail": str(exc)}), 400

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=raw_mm,
            temp_now_c=measured_temp_c,
            status="pending",
            created_by=g.user["username"],
            created_at=now,
        )
        db.add(row)
        db.flush()  # 拿到 row.id 再落账，两笔同一事务
        db.add(
            CompensationLedger(
                log_id=row.id,
                coeff_k=coeff_k,
                baseline_temp_c=baseline_temp_c,
                measured_temp_c=measured_temp_c,
                raw_mm=raw_mm,
                created_by=g.user["username"],
                created_at=now,
            )
        )
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.put("/api/logs/<int:log_id>/display")
@require_writer
def update_display(log_id):
    """只改在线展示数字并留痕；原始读数与补偿账一个字节都不动。"""
    body = request.get_json(silent=True) or {}
    try:
        new_mm = parse_number(body, "online_mm", "在线展示毫米值")
    except CompensationError as exc:
        return jsonify({"detail": str(exc)}), 400
    note = (body.get("note") or "").strip() or None

    db = SessionLocal()
    try:
        row = db.get(ConvergenceLog, log_id)
        if row is None:
            return jsonify({"detail": "找不到这条记录"}), 404
        old_mm = row.online_mm if row.online_mm is not None else row.corrected_mm
        row.online_mm = new_mm
        db.add(
            DisplayRevision(
                log_id=row.id,
                old_mm=old_mm,
                new_mm=new_mm,
                note=note,
                edited_by=g.user["username"],
                edited_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
