from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.get("/health/ready")
async def readiness_check():
    # You can add checks for Supabase, Redis, etc.
    return {"status": "ready"}

@router.get("/health/live")
async def liveness_check():
    return {"status": "alive"}