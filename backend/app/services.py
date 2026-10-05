"""缫丝盆业务门槛。

- 标成已缫完：最近一次汤温须落在 38～42℃。
- 缫丝中改回浸茧：当天须有一条未作废且余氯不低于 0.3 毫克/升的清汤记录。
"""

from datetime import date, datetime

from app.config import MIN_CHLORINE_MG_L, SITE_TIMEZONE
from app.models import Basin, ChlorineReading

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


def site_today(moment: datetime | None = None) -> date:
    """按坞上挂钟时区取自然日。"""
    moment = moment or datetime.now(SITE_TIMEZONE)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SITE_TIMEZONE)
    return moment.astimezone(SITE_TIMEZONE).date()


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def active_chlorine_for_day(
    basin: Basin, day: date
) -> ChlorineReading | None:
    active = [
        r
        for r in (basin.chlorine_readings or [])
        if r.voided_at is None and r.sample_day == day
    ]
    if not active:
        return None
    # 同日理论上至多一条；若有历史脏数据，以最新采样为准。
    return max(active, key=lambda r: r.sampled_at)


def assert_valid_chlorine_value(value: float) -> None:
    if value != value or value in (float("inf"), float("-inf")):
        raise RuleError("余氯值无效")
    if value <= 0:
        raise RuleError("余氯值须为正数")


def assert_no_active_chlorine(basin: Basin, day: date) -> None:
    if active_chlorine_for_day(basin, day) is not None:
        raise RuleError("该坞当天已有未作废的清汤余氯记录，请先作废再重采")


def assert_can_set_status(
    basin: Basin, new_status: str, *, today: date | None = None
) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status == Basin.STATUS_REELED:
        temp = latest_temp(basin)
        if temp is None:
            raise RuleError("该盆尚无汤温记录，不能标已缫完")
        if temp < MIN_TEMP or temp > MAX_TEMP:
            raise RuleError(
                f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃，不能标已缫完"
            )
        return
    # 仅“缫丝中 → 浸茧”这一道回退读余氯；
    # 登记汤温、标已缫完、已缫完拨浸茧均不看余氯。
    if basin.status == Basin.STATUS_REELING and new_status == Basin.STATUS_SOAKING:
        day = today or site_today()
        record = active_chlorine_for_day(basin, day)
        if record is None:
            raise RuleError("当天没有合格的清汤余氯记录，不能改回浸茧")
        if record.chlorine_mg_l < MIN_CHLORINE_MG_L:
            raise RuleError(
                f"当天清汤余氯 {record.chlorine_mg_l:g} 毫克/升，"
                f"低于 {MIN_CHLORINE_MG_L:g}，不能改回浸茧"
            )
