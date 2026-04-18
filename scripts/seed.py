import asyncio
from uuid import uuid4
from app.backend.database import async_session_maker
from app.backend.security import hash_password
from app.models.user_model import User, UserRole


async def run_seed():
    async with async_session_maker() as session:

        admin = User(
            id=uuid4(),
            username="admin_otg",
            password_hash=hash_password("admin123"),
            role=UserRole.ADMIN
        )


        inspector_1 = User(
            id=uuid4(),
            username="inspector_ivan",
            password_hash=hash_password("ins123"),
            role=UserRole.INSPECTOR
        )


        inspector_2 = User(
            id=uuid4(),
            username="inspector_olena",
            password_hash=hash_password("ins456"),
            role=UserRole.INSPECTOR
        )


        session.add_all([admin, inspector_1, inspector_2])
        await session.commit()

        print("Базу успішно наповнено: 1 Адмін та 2 Інспектори створені.")


if __name__ == "__main__":
    asyncio.run(run_seed())