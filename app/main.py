# app/main.py

from fastapi import FastAPI
from app.api.routes import items
from app.db.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Personal Knowledge Repository")

app.include_router(items.router, prefix="/items", tags=["Items"])


@app.get("/")
def root():
    return {"message": "Personal Knowledge Repository API is running"}