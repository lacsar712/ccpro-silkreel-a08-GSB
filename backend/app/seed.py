from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, ChlorineReading, Filature, User, utcnow
from app.security import hash_password


async def seed_demo() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(User).where(User.username == "admin"))
        admin = existing.scalar_one_or_none()
        if admin is None:
            admin = User(username="admin", password_hash=hash_password("123456"), role="admin")
            session.add(admin)
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"

        existing_w = await session.execute(select(User).where(User.username == "worker"))
        worker = existing_w.scalar_one_or_none()
        if worker is None:
            session.add(User(username="worker", password_hash=hash_password("123456"), role="worker"))
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"

        mill = (await session.execute(select(Filature))).scalars().first()
        if mill:
            # 升级旧库：清汤余氯表为空时，给一盆缫丝中补一条今日 0.1 记录
            has_chlorine = (
                await session.execute(select(ChlorineReading.id).limit(1))
            ).first()
            if has_chlorine is None:
                reeling = (
                    await session.execute(
                        select(Basin).where(Basin.status == Basin.STATUS_REELING).limit(1)
                    )
                ).scalars().first()
                if reeling is not None:
                    session.add(
                        ChlorineReading(
                            basin_id=reeling.id,
                            chlorine_mg_l=0.1,
                            sample_date=utcnow().date(),
                            taken_at=utcnow() - timedelta(minutes=30),
                            sampler="admin",
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
        # 缫丝中盆位预置一条今日清汤余氯记录，0.1 毫克/升不足以放行改浸茧
        chlorine_seed = {"甲-1": 0.1}
        for code, status, temp, idx in specs:
            basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=idx)
            session.add(basin)
            await session.flush()
            if temp is not None:
                session.add(
                    BathReading(
                        basin_id=basin.id,
                        water_temp_c=temp,
                        operator="worker",
                        taken_at=now - timedelta(hours=2),
                    )
                )
            if code in chlorine_seed:
                session.add(
                    ChlorineReading(
                        basin_id=basin.id,
                        chlorine_mg_l=chlorine_seed[code],
                        sample_date=now.date(),
                        taken_at=now - timedelta(minutes=30),
                        sampler="admin",
                    )
                )
        await session.commit()
