"""migrate repositories.owner to organisation_id FK

Revision ID: h8d5f2b0c419
Revises: g7c4e1a9d305
Create Date: 2026-03-24 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "h8d5f2b0c419"
down_revision = "g7c4e1a9d305"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add nullable FK column
    op.add_column(
        "repositories",
        sa.Column("organisation_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_repositories_organisation_id",
        "repositories",
        "organizations",
        ["organisation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_repositories_organisation_id",
        "repositories",
        ["organisation_id"],
    )

    # 2. Backfill: match existing repos to orgs by owner login derived from full_name
    op.execute("""
        UPDATE repositories r
        SET    organisation_id = o.id
        FROM   organizations o
        WHERE  split_part(r.full_name, '/', 1) = o.login
    """)

    # 3. Drop the now-redundant owner column (derivable from full_name)
    op.drop_column("repositories", "owner")


def downgrade() -> None:
    # Re-derive owner from full_name
    op.add_column(
        "repositories",
        sa.Column("owner", sa.String(255), nullable=True),   # nullable while backfilling
    )
    op.execute("UPDATE repositories SET owner = split_part(full_name, '/', 1)")
    op.alter_column("repositories", "owner", nullable=False)

    # Remove FK and index
    op.drop_constraint(
        "fk_repositories_organisation_id", "repositories", type_="foreignkey"
    )
    op.drop_index("ix_repositories_organisation_id", table_name="repositories")
    op.drop_column("repositories", "organisation_id")
