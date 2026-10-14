"""Host-specific, per-file-version video inspection receipts."""
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import SQLModel, Field, Column, JSON


class VideoHealth(SQLModel, table=True):
    __tablename__ = "video_health"
    __table_args__ = (
        UniqueConstraint("asset_id", "version_key", name="uq_video_health_version"),
        CheckConstraint("status IN ('unchecked','queued','checking','passed','abnormal','incomplete','unsupported')",
                        name="ck_video_health_status"),
    )
    id: str = Field(primary_key=True)
    asset_id: str = Field(foreign_key="media_asset.id", ondelete="CASCADE", index=True)
    version_key: str
    version: dict = Field(sa_column=Column(JSON, nullable=False))
    asset_snapshot: str
    status: str = Field(default="unchecked", index=True)
    container_status: str = "unchecked"
    error_code: str | None = None
    error_summary: str | None = None
    observed_at: float
    checked_at: float | None = None
    passed_at: float | None = None
    next_attempt_at: float = 0
    attempts: int = 0
    priority: int = 0
    decoded_seconds: float = 0
    duration_seconds: float | None = None
    cancel_requested: bool = False
    notified: bool = False
    acknowledged: bool = False
