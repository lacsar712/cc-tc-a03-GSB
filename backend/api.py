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
    CompensationSetting,
    ConvergenceLog,
    SessionLocal,
    TemperatureReading,
    engine,
    ledger_dict,
    row_dict,
    settings_dict,
    temp_dict,
)
from rules import (
    COEF_MAX,
    COEF_MIN,
    TEMP_MAX,
    TEMP_MIN,
    coefficient_ok,
    compensate,
    judge,
    temp_ok,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def get_settings(db) -> CompensationSetting | None:
    return db.query(CompensationSetting).order_by(CompensationSetting.id).first()


def latest_temp(db) -> TemperatureReading | None:
    return db.query(TemperatureReading).order_by(TemperatureReading.id.desc()).first()


def record_measurement(db, chainage: str, delta_mm: float, username: str):
    """进队记录和补偿账在同一事务里落库，要么一起成要么一起退。

    返回 (log_row, None)；缺洞温或系数越界时返回 (None, (人话提示, 状态码))。
    """
    settings = get_settings(db)
    if settings is None:
        return None, ("还没有设置补偿系数和基准洞温，请先在补偿专页的系数设置里填写", 400)
    if not coefficient_ok(settings.coefficient):
        return None, (
            f"补偿系数 {settings.coefficient} mm/℃ 超出 {COEF_MIN}~{COEF_MAX} 的允许范围，"
            "请先到系数设置里改正再提交",
            400,
        )
    temp = latest_temp(db)
    if temp is None:
        return None, ("还没有洞温记录，请先在补偿专页的洞温流水里登记当前洞温再提交", 400)
    drift, compensated = compensate(
        delta_mm, temp.temp_c, settings.baseline_temp_c, settings.coefficient
    )
    now = datetime.now(timezone.utc)
    row = ConvergenceLog(
        chainage=chainage,
        delta_mm=delta_mm,
        status="pending",
        created_by=username,
        created_at=now,
    )
    db.add(row)
    db.flush()  # 先取 log.id，补偿账挂在同一事务里
    db.add(
        CompensationLedger(
            log_id=row.id,
            chainage=chainage,
            raw_mm=delta_mm,
            temp_c=temp.temp_c,
            coefficient=settings.coefficient,
            baseline_temp_c=settings.baseline_temp_c,
            drift_mm=drift,
            compensated_mm=compensated,
            created_by=username,
            created_at=now,
        )
    )
    return row, None


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        db.add(
            CompensationSetting(
                coefficient=0.05,
                baseline_temp_c=20.0,
                updated_by="surveyor",
                updated_at=now,
            )
        )
        db.add(TemperatureReading(temp_c=20.0, created_by="surveyor", created_at=now))
        db.flush()
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            row, err = record_measurement(db, chainage, delta, "surveyor")
            assert err is None, err
            ledger = (
                db.query(CompensationLedger)
                .filter(CompensationLedger.log_id == row.id)
                .one()
            )
            verdict, reason = judge(ledger.compensated_mm)
            assert verdict == expect
            row.status = "done"
            row.verdict = verdict
            row.reason = reason
            row.processed_at = now
            ledger.verdict = verdict
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


def require_writer(message="仅测量员可提交收敛读数"):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"detail": "未登录"}), 401
            if user["role"] != "writer":
                return jsonify({"detail": message}), 403
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return deco


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


@app.post("/api/logs")
@require_writer("仅测量员可提交收敛读数")
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    db = SessionLocal()
    try:
        row, err = record_measurement(db, chainage, delta_mm, g.user["username"])
        if err is not None:
            db.rollback()
            return jsonify({"detail": err[0]}), err[1]
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.patch("/api/logs/<int:log_id>")
@require_writer("仅测量员可改在线展示数字")
def update_log(log_id: int):
    """只改总表在线展示的数字；补偿台账里当时记下的旧值不动。"""
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(ConvergenceLog, log_id)
        if row is None:
            return jsonify({"detail": "这条记录不存在"}), 404
        if "chainage" in body:
            chainage = (body.get("chainage") or "").strip()
            if not chainage:
                return jsonify({"detail": "桩号不能为空"}), 400
            row.chainage = chainage
        if "delta_mm" in body:
            try:
                row.delta_mm = float(body.get("delta_mm"))
            except (TypeError, ValueError):
                return jsonify({"detail": "收敛值必须是数字"}), 400
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row))
    finally:
        db.close()


@app.get("/api/compensation/settings")
@require_login
def get_comp_settings():
    db = SessionLocal()
    try:
        s = get_settings(db)
        return jsonify(settings_dict(s) if s else None)
    finally:
        db.close()


@app.put("/api/compensation/settings")
@require_writer("仅测量员可修改补偿系数")
def put_comp_settings():
    body = request.get_json(silent=True) or {}
    try:
        coefficient = float(body.get("coefficient"))
    except (TypeError, ValueError):
        return jsonify({"detail": "补偿系数必须是数字"}), 400
    if not coefficient_ok(coefficient):
        return jsonify(
            {
                "detail": f"补偿系数要在 {COEF_MIN}~{COEF_MAX} mm/℃ 之间，{coefficient} 超出范围"
            }
        ), 400
    try:
        baseline = float(body.get("baseline_temp_c"))
    except (TypeError, ValueError):
        return jsonify({"detail": "基准洞温必须是数字"}), 400
    if not temp_ok(baseline):
        return jsonify(
            {"detail": f"基准洞温要在 {TEMP_MIN}~{TEMP_MAX} ℃ 之间，{baseline} 不合理"}
        ), 400
    db = SessionLocal()
    try:
        s = get_settings(db)
        now = datetime.now(timezone.utc)
        if s is None:
            s = CompensationSetting(
                coefficient=coefficient,
                baseline_temp_c=baseline,
                updated_by=g.user["username"],
                updated_at=now,
            )
            db.add(s)
        else:
            s.coefficient = coefficient
            s.baseline_temp_c = baseline
            s.updated_by = g.user["username"]
            s.updated_at = now
        db.commit()
        db.refresh(s)
        return jsonify(settings_dict(s))
    finally:
        db.close()


@app.get("/api/compensation/temps")
@require_login
def list_temps():
    db = SessionLocal()
    try:
        rows = (
            db.query(TemperatureReading)
            .order_by(TemperatureReading.id.desc())
            .limit(200)
            .all()
        )
        return jsonify([temp_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/compensation/temps")
@require_writer("仅测量员可登记洞温")
def create_temp():
    body = request.get_json(silent=True) or {}
    try:
        temp_c = float(body.get("temp_c"))
    except (TypeError, ValueError):
        return jsonify({"detail": "洞温必须是数字"}), 400
    if not temp_ok(temp_c):
        return jsonify(
            {"detail": f"洞温要在 {TEMP_MIN}~{TEMP_MAX} ℃ 之间，{temp_c} 不合理"}
        ), 400
    db = SessionLocal()
    try:
        row = TemperatureReading(
            temp_c=temp_c,
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(temp_dict(row)), 201
    finally:
        db.close()


@app.get("/api/compensation/ledger")
@require_login
def list_ledger():
    db = SessionLocal()
    try:
        rows = (
            db.query(CompensationLedger).order_by(CompensationLedger.id.desc()).all()
        )
        return jsonify([ledger_dict(r) for r in rows])
    finally:
        db.close()
