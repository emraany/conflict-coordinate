from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Admin1Alias(Base):
    """Maps spelling variants of admin1 names to ACLED's canonical form.

    Seeded from ACLED's vocabulary (canonical → itself) and Natural Earth
    `name`/`name_alt`. Iterated as UCDP/GDELT misses surface.
    """

    __tablename__ = "admin1_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    alias_norm: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_admin1_norm: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_admin1: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_admin1_aliases_country_alias",
            "country_iso3",
            "alias_norm",
            unique=True,
        ),
        Index(
            "ix_admin1_aliases_country_canonical",
            "country_iso3",
            "canonical_admin1_norm",
        ),
    )


class Admin1Polygon(Base):
    """Natural Earth admin1 polygons for GDELT point-in-polygon attach."""

    __tablename__ = "admin1_polygons"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    admin1: Mapped[str] = mapped_column(String(120), nullable=False)
    admin1_norm: Mapped[str] = mapped_column(String(120), nullable=False)
    centroid_lat: Mapped[float | None] = mapped_column(Float)
    centroid_lng: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_admin1_polygons_country_admin1",
            "country_iso3",
            "admin1_norm",
            unique=True,
        ),
    )
