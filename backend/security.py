from fastapi import Header, HTTPException

from auth import get_token_user_id


def get_current_user_id(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = get_token_user_id(authorization[7:])
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    return user_id
