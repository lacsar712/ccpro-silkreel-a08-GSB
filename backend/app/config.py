import os
from zoneinfo import ZoneInfo

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://silkreel:silkreel@127.0.0.1:6160/silkreel",
)
JWT_SECRET = os.environ.get("JWT_SECRET", "silkreel-dev-secret")
JWT_ALG = "HS256"
# “当天/自然日”按坞上挂钟所在时区切日，默认 Asia/Shanghai。
SITE_TIMEZONE = ZoneInfo(os.environ.get("SITE_TIMEZONE", "Asia/Shanghai"))
# 缫丝中改回浸茧所需的最低清汤余氯（毫克/升）。
MIN_CHLORINE_MG_L = 0.3
