from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, ChlorineReading, Filature, User
from app.services import RuleError


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
                selectinload(Filature.basins).selectinload(Basin.readings),
                selectinload(Filature.basins).selectinload(Basin.chlorine_readings),
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
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self) -> list[ChlorineReading]:
        result = await self.session.execute(
            select(ChlorineReading).order_by(
                ChlorineReading.sample_date.desc(),
                ChlorineReading.basin_id,
                ChlorineReading.taken_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def get(self, reading_id: int) -> ChlorineReading | None:
        result = await self.session.execute(
            select(ChlorineReading).where(ChlorineReading.id == reading_id)
        )
        return result.scalar_one_or_none()

    async def add(
        self, basin: Basin, value: float, day: date, sampler: str, taken_at
    ) -> ChlorineReading:
        row = ChlorineReading(
            basin=basin,
            chlorine_mg_l=value,
            sample_date=day,
            taken_at=taken_at,
            sampler=sampler,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise RuleError("该坞今天已有一条未作废的清汤余氯记录，请先作废旧记录")
        await self.session.refresh(row)
        return row

    async def void(self, reading: ChlorineReading, voided_at) -> None:
        reading.voided_at = voided_at
        await self.session.commit()
