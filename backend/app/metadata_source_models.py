from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import CheckConstraint, Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

class FilmMetadataSourceSnapshot(SQLModel,table=True):
    __tablename__='film_metadata_source_snapshot'
    __table_args__=(
        UniqueConstraint('film_id','field_kind','origin_kind','origin_ref',name='uq_film_metadata_source_snapshot'),
        CheckConstraint("field_kind IN ('original_language','spoken_languages','cast')",name='ck_metadata_snapshot_field'),
        CheckConstraint("origin_kind IN ('curated','nfo','tmdb')",name='ck_metadata_snapshot_origin'),
    )
    id: str=Field(default_factory=lambda:'msnap_'+uuid4().hex,primary_key=True)
    film_id: str=Field(foreign_key='film.id',ondelete='CASCADE',index=True)
    field_kind: str
    origin_kind: str
    origin_ref: str
    values: list[str]=Field(default_factory=list,sa_column=Column(JSON,nullable=False))
    observed_at: str=Field(default_factory=lambda:datetime.now(timezone.utc).isoformat())
