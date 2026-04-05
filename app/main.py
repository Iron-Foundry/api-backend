import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from pymongo import AsyncMongoClient
from valkey.asyncio import Valkey

from app.routers import events

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "foundry")
VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to MongoDB at {}...", MONGO_URI)
    app.state.mongo = AsyncMongoClient(MONGO_URI)
    app.state.db = app.state.mongo[MONGO_DB]
    logger.info("Connecting to Valkey at {}...", VALKEY_URI)
    app.state.valkey = Valkey.from_url(VALKEY_URI)
    yield
    logger.info("Closing MongoDB connection...")
    await app.state.mongo.aclose()
    logger.info("Closing Valkey connection...")
    await app.state.valkey.aclose()


app = FastAPI(title="The Foundry API", lifespan=lifespan)

app.include_router(events.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
