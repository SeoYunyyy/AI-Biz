# app/db/crud.py

from sqlalchemy.orm import Session
from app.models.item import Item


def create_item(db: Session, item_data: dict):
    db_item = Item(**item_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_items(db: Session):
    return db.query(Item).order_by(Item.created_at.desc()).all()