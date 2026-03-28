"""Auth routes — Clerk-based profile management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.clerk_auth import get_clerk_user_id
from app.services.redis_service import redis_client

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class ProfileUpdateRequest(BaseModel):
    interests: Optional[List[str]] = None
    level: Optional[str] = None
    role: Optional[str] = None


class ProfileSetupRequest(BaseModel):
    role: str = "student"
    interests: List[str] = []
    level: str = "beginner"


def cache_user_profile(user: User):
    """Save user profile in Redis for fast access during personalization."""
    import json
    profile = {
        "id": user.id,
        "clerk_id": user.clerk_id,
        "role": user.role,
        "interests": user.interests or [],
        "level": user.level,
        "engagement": user.engagement or {},
    }
    redis_client.setex(f"user:{user.id}", 86400, json.dumps(profile))
    if user.clerk_id:
        redis_client.setex(f"clerk_user:{user.clerk_id}", 86400, str(user.id))


async def get_or_create_user(clerk_id: str, db: AsyncSession) -> User:
    """Get existing user by Clerk ID or create a new one."""
    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(clerk_id=clerk_id, role="student", interests=[], level="beginner", engagement={})
        db.add(user)
        await db.flush()
        await db.commit()
        cache_user_profile(user)

    return user


@router.get("/profile")
async def get_profile(
    clerk_id: str = Depends(get_clerk_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's profile."""
    user = await get_or_create_user(clerk_id, db)
    return {
        "id": user.id,
        "clerk_id": user.clerk_id,
        "email": user.email,
        "role": user.role,
        "interests": user.interests,
        "level": user.level,
        "engagement": user.engagement,
        "needs_setup": not user.interests,
    }


@router.post("/profile/setup")
async def setup_profile(
    body: ProfileSetupRequest,
    clerk_id: str = Depends(get_clerk_user_id),
    db: AsyncSession = Depends(get_db),
):
    """First-time profile setup after Clerk login."""
    user = await get_or_create_user(clerk_id, db)
    user.role = body.role
    user.interests = body.interests
    user.level = body.level
    await db.commit()
    cache_user_profile(user)
    return {"message": "Profile configured", "user_id": user.id}


@router.put("/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    clerk_id: str = Depends(get_clerk_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update user preferences."""
    user = await get_or_create_user(clerk_id, db)

    if body.interests is not None:
        user.interests = body.interests
    if body.level is not None:
        user.level = body.level
    if body.role is not None:
        user.role = body.role

    await db.commit()
    cache_user_profile(user)
    redis_client.delete(f"feed:{user.id}")

    return {"message": "Profile updated", "user_id": user.id}
