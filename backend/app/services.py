"""缫丝盆门槛：
- 标成已缫完须最近一次汤温落在 38～42℃。
- 缫丝中改回浸茧须当天有一条未作废且余氯 ≥ 0.3 毫克/升的清汤记录。
"""

import math
from datetime import date

from app.models import Basin, ChlorineReading

MIN_TEMP = 38.0
MAX_TEMP = 42.0

MIN_CHLORINE = 0.3


class RuleError(ValueError):
    pass


def local_today() -> date:
    return date.today()


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def active_chlorine_on(basin: Basin, day: date) -> ChlorineReading | None:
    """该坞某自然日未作废的清汤余氯记录（理论上至多一条）。"""
    active = [
        r
        for r in (basin.chlorine_readings or [])
        if r.voided_at is None and r.sample_date == day
    ]
    if not active:
        return None
    return max(active, key=lambda r: r.taken_at)


def valid_chlorine(value: float) -> bool:
    return math.isfinite(value) and value > 0


def assert_can_set_status(basin: Basin, new_status: str, today: date | None = None) -> None:
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

    if basin.status == Basin.STATUS_REELING and new_status == Basin.STATUS_SOAKING:
        day = today or local_today()
        reading = active_chlorine_on(basin, day)
        if reading is None:
            raise RuleError("该坞今天没有合格的清汤余氯记录，不能改回浸茧")
        if reading.chlorine_mg_l < MIN_CHLORINE:
            raise RuleError(
                f"今日清汤余氯 {reading.chlorine_mg_l} 毫克/升，"
                f"低于 {MIN_CHLORINE} 不能放行改浸茧"
            )
