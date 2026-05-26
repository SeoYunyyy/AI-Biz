"""
초기 아이템 데이터 삽입 스크립트

사용법:
    cd backend
    python scripts/seed_items.py
"""

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from database import AsyncSessionLocal, Base, engine
from models.gamification import Item
from utils.category_mapper import CATEGORY_ITEMS


async def seed_items():
    # 테이블 생성 (없으면)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        inserted = 0
        skipped = 0

        for category, item_data in CATEGORY_ITEMS.items():
            # 이미 존재하면 스킵
            existing = await session.execute(
                select(Item).where(Item.category == category)
            )
            if existing.scalar_one_or_none():
                print(f"  ⏭️  스킵: {category} ({item_data['name']})")
                skipped += 1
                continue

            item = Item(
                name=item_data["name"],
                category=category,
                emoji=item_data["emoji"],
                description=item_data["description"],
            )
            session.add(item)
            print(f"  ✅ 삽입: {category} → {item_data['emoji']} {item_data['name']}")
            inserted += 1

        await session.commit()
        print(f"\n완료! 삽입: {inserted}개 / 스킵: {skipped}개")


if __name__ == "__main__":
    print("🌱 아이템 데이터 시딩 시작...\n")
    asyncio.run(seed_items())
