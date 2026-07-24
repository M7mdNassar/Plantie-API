from fastapi import Depends
from src.api.middleware.auth import verify_token

async def get_current_user(user_info: dict = Depends(verify_token)):
    return user_info