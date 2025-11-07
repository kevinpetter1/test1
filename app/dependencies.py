from __future__ import annotations

import os
from typing import AsyncGenerator, Generator

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_telnyx_api_key() -> str:
    api_key = os.getenv("TELNYX_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="TELNYX_API_KEY not configured")
    return api_key
