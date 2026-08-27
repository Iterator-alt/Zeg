"""Initial schema with parcels, wetlands, floodplains, and manual_overrides tables.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure PostGIS extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Create parcels table
    op.create_table(
        "parcels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("owner_name", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("recorded_acres", sa.Float(), nullable=True),
        sa.Column("calculated_acres", sa.Float(), nullable=True),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_parcels_source_id", "parcels", ["source_id"], unique=False)
    op.create_index("idx_parcels_county", "parcels", ["county"], unique=False)
    op.create_index(
        "idx_parcels_geom",
        "parcels",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )

    # Create wetlands table
    op.create_table(
        "wetlands",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attribute", sa.String(length=50), nullable=True),
        sa.Column("wetland_type", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_wetlands_geom",
        "wetlands",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )

    # Create floodplains table
    op.create_table(
        "floodplains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fld_zone", sa.String(length=20), nullable=True),
        sa.Column("zone_subty", sa.String(length=100), nullable=True),
        sa.Column("static_bfe", sa.String(length=20), nullable=True),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("sfha_tf", sa.String(length=5), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_floodplains_fld_zone", "floodplains", ["fld_zone"], unique=False)
    op.create_index(
        "idx_floodplains_geom",
        "floodplains",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )

    # Create manual_overrides table
    op.create_table(
        "manual_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parcel_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parcel_id"],
            ["parcels.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_manual_overrides_parcel_id", "manual_overrides", ["parcel_id"], unique=False)
    op.create_index("idx_manual_overrides_session_id", "manual_overrides", ["session_id"], unique=False)
    op.create_index(
        "idx_manual_overrides_parcel_session",
        "manual_overrides",
        ["parcel_id", "session_id"],
        unique=False,
    )
    op.create_index(
        "idx_manual_overrides_geom",
        "manual_overrides",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_table("manual_overrides")
    op.drop_table("floodplains")
    op.drop_table("wetlands")
    op.drop_table("parcels")
