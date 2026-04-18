import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

# Ensure project root is importable when running `python /code/scripts/seed.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.backend.database import async_session_maker
from app.backend.security import hash_password
from app.models.user_model import User, UserRole


SEED_USERS = [
    ("admin_otg", "admin123", UserRole.ADMIN),
    ("inspector_ivan", "ins123", UserRole.INSPECTOR),
    ("inspector_olena", "ins456", UserRole.INSPECTOR),
    ("volunteer_marta", "vol123", UserRole.VOLUNTEER),
    ("volunteer_oleg", "vol456", UserRole.VOLUNTEER),
]


async def run_seed() -> None:
    async with async_session_maker() as session:
        usernames = [username for username, _, _ in SEED_USERS]
        existing_stmt = select(User.username).where(User.username.in_(usernames))
        existing = set((await session.execute(existing_stmt)).scalars().all())

        new_users = [
            User(
                id=uuid4(),
                username=username,
                password_hash=hash_password(password),
                role=role,
            )
            for username, password, role in SEED_USERS
            if username not in existing
        ]

        if not new_users:
            print("Seed skipped: all demo users already exist.")
            return

        session.add_all(new_users)
        await session.commit()
        print(f"Seed complete: created {len(new_users)} user(s).")


if __name__ == "__main__":
    asyncio.run(run_seed())