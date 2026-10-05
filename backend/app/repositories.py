from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Basin, BathReading, ChlorineReading, Filature, User


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


class BasinRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def board(self) -> Filature | None:
        result = await self.session.execute(
            select(Filature).options(
                selectinload(Filature.basins)
                .selectinload(Basin.readings),
                selectinload(Filature.basins)
                .selectinload(Basin.chlorine_readings),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(
                selectinload(Basin.readings),
                selectinload(Basin.chlorine_readings),
            )
            .where(Basin.id == basin_id)
        )
        return result.scalar_one_or_none()

    async def add_reading(self, basin: Basin, temp_c: float, operator: str) -> BathReading:
        row = BathReading(basin=basin, water_temp_c=temp_c, operator=operator)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def save_status(self, basin: Basin, status: str) -> None:
        basin.status = status
        await self.session.commit()


class ChlorineRepo:
    """清汤余氯记录仓储。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_basin(self, basin_id: int) -> Basin | None:
        """行锁该坞，串行化同坞同日的交叉采样。"""
        result = await self.session.execute(
            select(Basin).where(Basin.id == basin_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def active_for_day(self, basin_id: int, day: date) -> ChlorineReading | None:
        result = await self.session.execute(
            select(ChlorineReading).where(
                ChlorineReading.basin_id == basin_id,
                ChlorineReading.sample_day == day,
                ChlorineReading.voided_at.is_(None),
            )
        )
        return result.scalars().first()

    async def add(
        self,
        basin_id: int,
        value: float,
        sampler: str,
        sampled_at,
        day: date,
    ) -> ChlorineReading:
        row = ChlorineReading(
            basin_id=basin_id,
            chlorine_mg_l=value,
            sampler=sampler,
            sampled_at=sampled_at,
            sample_day=day,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise exc
        await self.session.refresh(row)
        return row

    async def get(self, reading_id: int) -> ChlorineReading | None:
        result = await self.session.execute(
            select(ChlorineReading)
            .options(joinedload(ChlorineReading.basin))
            .where(ChlorineReading.id == reading_id)
        )
        return result.scalar_one_or_none()

    async def list_day(self, day: date) -> list[ChlorineReading]:
        result = await self.session.execute(
            select(ChlorineReading)
            .options(joinedload(ChlorineReading.basin))
            .where(ChlorineReading.sample_day == day)
            .order_by(ChlorineReading.basin_id, ChlorineReading.sampled_at)
        )
        return list(result.scalars().unique().all())

    async def save_void(self, reading: ChlorineReading, voided_at) -> None:
        reading.voided_at = voided_at
        await self.session.commit()
