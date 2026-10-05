from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, ChlorineReading, Filature, User, utcnow
from app.security import hash_password
from app.services import site_today


async def _upsert_user(session, username: str, role: str) -> None:
    existing = await session.execute(select(User).where(User.username == username))
    user = existing.scalar_one_or_none()
    if user is None:
        session.add(
            User(username=username, password_hash=hash_password("123456"), role=role)
        )
    else:
        user.password_hash = hash_password("123456")
        user.role = role


async def seed_demo() -> None:
    async with SessionLocal() as session:
        await _upsert_user(session, "admin", "admin")
        await _upsert_user(session, "admin2", "admin")
        await _upsert_user(session, "worker", "worker")

        mill = (await session.execute(select(Filature))).scalars().first()
        now = utcnow()
        if mill:
            # 旧库升级（新表已由 create_all 建好）：补一条演示用的 0.1 记录。
            basin = (
                (
                    await session.execute(
                        select(Basin).where(
                            Basin.filature_id == mill.id, Basin.code == "甲-1"
                        )
                    )
                )
                .scalars()
                .first()
            )
            if basin is not None:
                has_chlorine = (
                    await session.execute(
                        select(ChlorineReading).where(
                            ChlorineReading.basin_id == basin.id
                        )
                    )
                ).first()
                if has_chlorine is None:
                    session.add(
                        ChlorineReading(
                            basin_id=basin.id,
                            chlorine_mg_l=0.1,
                            sampler="admin",
                            sampled_at=now - timedelta(minutes=40),
                            sample_day=site_today(),
                        )
                    )
            await session.commit()
            return

        mill = Filature(name="江口缫丝坞", riverside="东津渡")
        session.add(mill)
        await session.flush()
        now = utcnow()
        specs = [
            ("甲-1", Basin.STATUS_REELING, 40.5, 0),
            ("甲-2", Basin.STATUS_SOAKING, None, 1),
            ("乙-1", Basin.STATUS_REELED, 39.2, 2),
            ("乙-2", Basin.STATUS_REELING, 36.0, 3),
            ("丙-1", Basin.STATUS_SOAKING, None, 4),
            ("丙-2", Basin.STATUS_REELED, 41.0, 5),
        ]
        reeling_basin_id = None
        for code, status, temp, idx in specs:
            basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=idx)
            session.add(basin)
            await session.flush()
            if code == "甲-1":
                reeling_basin_id = basin.id
            if temp is not None:
                session.add(
                    BathReading(
                        basin_id=basin.id,
                        water_temp_c=temp,
                        operator="worker",
                        taken_at=now - timedelta(hours=2),
                    )
                )

        # 甲-1 正在缫丝中：当天有一条余氯 0.1 毫克/升的清汤记录，
        # 低于 0.3 放行线，故不能改回浸茧，须管理员重新采样合格记录。
        session.add(
            ChlorineReading(
                basin_id=reeling_basin_id,
                chlorine_mg_l=0.1,
                sampler="admin",
                sampled_at=now - timedelta(minutes=40),
                sample_day=site_today(),
            )
        )
        await session.commit()
