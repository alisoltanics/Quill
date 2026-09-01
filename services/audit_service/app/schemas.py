from pydantic import BaseModel


class ActivityItem(BaseModel):
    user: str
    action: str
    version: int
    created_at: str
