from datetime import date, datetime

from quart import Quart, g, jsonify, request
from quart.helpers import make_response
from sqlalchemy.exc import IntegrityError

from app.config import SITE_TIMEZONE
from app.db import SessionLocal
from app.models import Basin, ChlorineReading, utcnow
from app.repositories import BasinRepo, ChlorineRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    RuleError,
    active_chlorine_for_day,
    assert_can_set_status,
    assert_valid_chlorine_value,
    latest_temp,
    site_today,
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
        return jsonify({"detail": "仅管理员可采样或作废清汤余氯"}), 403
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
    today = site_today()
    today_record = active_chlorine_for_day(basin, today)
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "todayChlorine": _chlorine_json(today_record) if today_record else None,
    }


def _chlorine_json(reading: ChlorineReading) -> dict:
    return {
        "id": reading.id,
        "basinId": reading.basin_id,
        "basinCode": reading.basin.code if reading.basin else None,
        "chlorineMgL": reading.chlorine_mg_l,
        "sampledAt": reading.sampled_at.isoformat() if reading.sampled_at else None,
        "sampleDay": reading.sample_day.isoformat(),
        "sampler": reading.sampler,
        "voidedAt": reading.voided_at.isoformat() if reading.voided_at else None,
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
            "today": site_today().isoformat(),
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


@app.route("/api/chlorine", methods=["GET"])
async def chlorine_list():
    denied = require_user()
    if denied:
        return denied
    raw_day = request.args.get("day", "")
    if raw_day:
        try:
            day = date.fromisoformat(raw_day)
        except ValueError:
            return jsonify({"detail": "日期格式应为 YYYY-MM-DD"}), 400
    else:
        day = site_today()
    async with SessionLocal() as session:
        rows = await ChlorineRepo(session).list_day(day)
        return {
            "day": day.isoformat(),
            "today": site_today().isoformat(),
            "records": [_chlorine_json(r) for r in rows],
        }


@app.route("/api/chlorine", methods=["POST"])
async def chlorine_create():
    denied = require_admin()
    if denied:
        return denied
    body = await request.get_json(force=True) or {}
    try:
        basin_id = int(body.get("basinId"))
    except (TypeError, ValueError):
        return jsonify({"detail": "须指定坞"}), 400
    try:
        value = float(body.get("chlorineMgL"))
    except (TypeError, ValueError):
        return jsonify({"detail": "余氯值必须是数字"}), 400
    try:
        assert_valid_chlorine_value(value)
    except RuleError as exc:
        return jsonify({"detail": str(exc)}), 400

    sampled_at_raw = (body.get("sampledAt") or "").strip()
    if sampled_at_raw:
        try:
            sampled_at = datetime.fromisoformat(sampled_at_raw)
        except ValueError:
            return jsonify({"detail": "采样时刻格式无效"}), 400
        if sampled_at.tzinfo is None:
            sampled_at = sampled_at.replace(tzinfo=SITE_TIMEZONE)
        sampled_at = sampled_at.astimezone(utcnow().tzinfo)
    else:
        sampled_at = utcnow()
    day = sampled_at.astimezone(SITE_TIMEZONE).date()

    async with SessionLocal() as session:
        repo = ChlorineRepo(session)
        basin = await repo.lock_basin(basin_id)
        if basin is None:
            return jsonify({"detail": "坞不存在"}), 404
        # 两名值班交叉给同坞同日交两条时，这里只许留下一条；
        # 行锁 + 数据库唯一索引双保险。
        existing = await repo.active_for_day(basin_id, day)
        if existing is not None:
            return jsonify({"detail": "该坞当天已有未作废的清汤余氯记录，请先作废再重采"}), 409
        try:
            reading = await repo.add(basin_id, value, g.user.username, sampled_at, day)
        except IntegrityError:
            return jsonify({"detail": "该坞当天已有未作废的清汤余氯记录，请先作废再重采"}), 409
        reading = await repo.get(reading.id)
        return _chlorine_json(reading)


@app.route("/api/chlorine/<int:reading_id>/void", methods=["POST"])
async def chlorine_void(reading_id: int):
    denied = require_admin()
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = ChlorineRepo(session)
        reading = await repo.get(reading_id)
        if reading is None:
            return jsonify({"detail": "余氯记录不存在"}), 404
        if reading.voided_at is not None:
            return jsonify({"detail": "该记录已作废"}), 400
        await repo.save_void(reading, utcnow())
        reading = await repo.get(reading_id)
        return _chlorine_json(reading)
