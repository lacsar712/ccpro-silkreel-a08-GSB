from quart import Quart, g, jsonify, request
from quart.helpers import make_response
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, utcnow
from app.repositories import BasinRepo, ChlorineRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    MIN_CHLORINE,
    RuleError,
    active_chlorine_on,
    assert_can_set_status,
    latest_temp,
    local_today,
    valid_chlorine,
)

app = Quart(__name__)


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


@app.before_request
async def load_user():
    g.user = None
    token = _bearer()
    if not token:
        return
    username = parse_token(token)
    if not username:
        return
    async with SessionLocal() as session:
        g.user = await UserRepo(session).by_username(username)


def require_user():
    if g.user is None:
        return jsonify({"detail": "未登录"}), 401
    return None


def require_admin():
    denied = require_user()
    if denied:
        return denied
    if g.user.role != "admin":
        return jsonify({"detail": "仅管理员可采样与作废清汤余氯记录"}), 403
    return None


@app.route("/api/health")
async def health():
    return {"status": "ok", "service": "SilkReel"}


@app.route("/api/auth/login", methods=["POST"])
async def login():
    body = await request.get_json(force=True)
    username = (body or {}).get("username", "")
    password = (body or {}).get("password", "")
    async with SessionLocal() as session:
        user = await UserRepo(session).by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return jsonify({"detail": "用户名或密码错误"}), 401
        return {
            "access_token": make_token(user.username),
            "user": {"username": user.username, "role": user.role},
        }


@app.route("/api/auth/me")
async def me():
    denied = require_user()
    if denied:
        return denied
    return {"username": g.user.username, "role": g.user.role}


def _basin_json(basin: Basin) -> dict:
    today_reading = active_chlorine_on(basin, local_today())
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "todayChlorineMgL": today_reading.chlorine_mg_l if today_reading else None,
        "chlorineOk": (
            today_reading is not None and today_reading.chlorine_mg_l >= MIN_CHLORINE
        ),
    }


@app.route("/api/board")
async def board():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        mill = await BasinRepo(session).board()
        if mill is None:
            return jsonify({"detail": "尚无缫丝坞"}), 404
        basins = sorted(mill.basins, key=lambda b: b.ring_index)
        return {
            "filature": mill.name,
            "riverside": mill.riverside,
            "basins": [_basin_json(b) for b in basins],
        }


@app.route("/api/basins/<int:basin_id>/readings", methods=["POST"])
async def add_reading(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    try:
        temp = float((body or {}).get("waterTempC"))
    except (TypeError, ValueError):
        return jsonify({"detail": "汤温必须是数字"}), 400
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        await repo.add_reading(basin, temp, g.user.username)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/basins/<int:basin_id>/status", methods=["POST"])
async def set_status(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    status = (body or {}).get("status", "")
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            assert_can_set_status(basin, status)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.save_status(basin, status)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


def _chlorine_json(row, basin_code: str) -> dict:
    return {
        "id": row.id,
        "basinId": row.basin_id,
        "basinCode": basin_code,
        "chlorineMgL": row.chlorine_mg_l,
        "sampleDate": row.sample_date.isoformat(),
        "takenAt": row.taken_at.isoformat() if row.taken_at else None,
        "sampler": row.sampler,
        "voidedAt": row.voided_at.isoformat() if row.voided_at else None,
        "voided": row.voided_at is not None,
        "qualified": row.chlorine_mg_l >= MIN_CHLORINE,
    }


@app.route("/api/chlorine")
async def chlorine_list():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = ChlorineRepo(session)
        rows = await repo.list()
        basins = (await session.execute(select(Basin.id, Basin.code))).all()
        codes = {bid: code for bid, code in basins}
        return {
            "records": [_chlorine_json(r, codes.get(r.basin_id, str(r.basin_id))) for r in rows]
        }


@app.route("/api/chlorine", methods=["POST"])
async def chlorine_create():
    denied = require_admin()
    if denied:
        return denied
    body = await request.get_json(force=True)
    try:
        basin_id = int((body or {}).get("basinId"))
    except (TypeError, ValueError):
        return jsonify({"detail": "必须指定坞"}), 400
    try:
        value = float((body or {}).get("chlorineMgL"))
    except (TypeError, ValueError):
        return jsonify({"detail": "余氯值必须是数字"}), 400
    if not valid_chlorine(value):
        return jsonify({"detail": "余氯值必须是正数"}), 400
    async with SessionLocal() as session:
        basin = await BasinRepo(session).get(basin_id)
        if basin is None:
            return jsonify({"detail": "坞不存在"}), 404
        now = utcnow()
        repo = ChlorineRepo(session)
        try:
            row = await repo.add(basin, value, now.date(), g.user.username, now)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        return _chlorine_json(row, basin.code)


@app.route("/api/chlorine/<int:reading_id>/void", methods=["POST"])
async def chlorine_void(reading_id: int):
    denied = require_admin()
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = ChlorineRepo(session)
        row = await repo.get(reading_id)
        if row is None:
            return jsonify({"detail": "记录不存在"}), 404
        if row.voided_at is not None:
            return jsonify({"detail": "该记录已作废"}), 400
        basin_code = (
            await session.execute(select(Basin.code).where(Basin.id == row.basin_id))
        ).scalar_one_or_none()
        await repo.void(row, utcnow())
        return _chlorine_json(row, basin_code or str(row.basin_id))
