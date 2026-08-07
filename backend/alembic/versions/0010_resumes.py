"""resumes: JSONB-authoritative resumes, the write-derived index, and revisions

Adds the Output layer. Ordering matters because ``resumes`` holds the FK to
``job_applications`` (a one-directional link, so no circular dependency):

1. the ``job_application_status`` enum and ``job_applications`` (a lightweight
   relational entity; this revision creates the table and the FK target only);
2. the ``resume_kind`` / ``resume_status`` enums and ``resumes`` (the ``document``
   JSONB, the write-derived ``title`` / ``schema_version`` / ``revision`` scalars,
   ``forked_from_resume_id`` self-FK for fork provenance, and ``job_application_id``
   with ``UNIQUE`` for the 1:1 link and the application-only ``CHECK``);
3. ``resume_bullet_ref`` (write-derived: which canonical bullets a resume
   references, reindexed on every save, indexed by ``bullet_id`` for "used in N");
4. ``resume_revisions`` (append-only keep-all: a fully resolved snapshot per save,
   with the ``pdf_object_key`` the render path fills).

``resume_bullet_ref`` references ``bulletpoints(id)`` (from 0008), so this revision
chains after the library and profile domains. Constraint, index, and enum names
follow the deterministic convention so the ORM models in ``floresu.resumes.models``
autogenerate no diff and the downgrade is reversible.

Revision ID: 0010_resumes
Revises: 0009_skills_identity_variants
Create Date: 2026-07-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_resumes"
down_revision: str | None = "0009_skills_identity_variants"
branch_labels: str | None = None
depends_on: str | None = None

# ``create_type=False``: each type is created/dropped explicitly here so a table
# create never re-emits ``CREATE TYPE``. One instance is reused by every column.
job_application_status_enum = postgresql.ENUM(
    "added", "submitted", name="job_application_status", create_type=False
)
resume_kind_enum = postgresql.ENUM("living", "application", name="resume_kind", create_type=False)
resume_status_enum = postgresql.ENUM("draft", "finalized", name="resume_status", create_type=False)


def upgrade() -> None:
    job_application_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "job_applications",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("role_title", sa.Text(), nullable=False),
        sa.Column(
            "status",
            job_application_status_enum,
            server_default="added",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_applications"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_job_applications_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_job_applications_user_id_id", "job_applications", ["user_id", "id"], unique=False
    )

    resume_kind_enum.create(op.get_bind(), checkfirst=True)
    resume_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "resumes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", resume_kind_enum, nullable=False),
        sa.Column("status", resume_status_enum, server_default="draft", nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("forked_from_resume_id", sa.BigInteger(), nullable=True),
        sa.Column("job_application_id", sa.BigInteger(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resumes"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_resumes_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["forked_from_resume_id"],
            ["resumes.id"],
            name="fk_resumes_forked_from_resume_id_resumes",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_application_id"],
            ["job_applications.id"],
            name="fk_resumes_job_application_id_job_applications",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("job_application_id", name="uq_resumes_job_application_id"),
        sa.CheckConstraint(
            "job_application_id IS NULL OR kind = 'application'",
            name="job_application_kind",
        ),
    )
    op.create_index("ix_resumes_user_id_id", "resumes", ["user_id", "id"], unique=False)

    op.create_table(
        "resume_bullet_ref",
        sa.Column("resume_id", sa.BigInteger(), nullable=False),
        sa.Column("bullet_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("resume_id", "bullet_id", name="pk_resume_bullet_ref"),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name="fk_resume_bullet_ref_resume_id_resumes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bullet_id"],
            ["bulletpoints.id"],
            name="fk_resume_bullet_ref_bullet_id_bulletpoints",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_resume_bullet_ref_bullet_id", "resume_bullet_ref", ["bullet_id"], unique=False
    )

    op.create_table(
        "resume_revisions",
        sa.Column("resume_id", sa.BigInteger(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("pdf_object_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("resume_id", "revision_no", name="pk_resume_revisions"),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name="fk_resume_revisions_resume_id_resumes",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("resume_revisions")
    op.drop_index("ix_resume_bullet_ref_bullet_id", table_name="resume_bullet_ref")
    op.drop_table("resume_bullet_ref")
    op.drop_index("ix_resumes_user_id_id", table_name="resumes")
    op.drop_table("resumes")
    resume_status_enum.drop(op.get_bind(), checkfirst=True)
    resume_kind_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_job_applications_user_id_id", table_name="job_applications")
    op.drop_table("job_applications")
    job_application_status_enum.drop(op.get_bind(), checkfirst=True)
