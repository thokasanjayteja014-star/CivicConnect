"""auto-generated public issues from complaint clusters

Revision ID: d4a8f1c2e9b7
Revises: 0e4785e97d2f
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a8f1c2e9b7"
down_revision: Union[str, Sequence[str], None] = "0e4785e97d2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("public_issues", sa.Column("auto_generated", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("public_issues", sa.Column("auto_publish_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("public_issues", sa.Column("published_automatically", sa.Boolean(), server_default="false", nullable=False))
    op.alter_column("public_issues", "created_by", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("public_issue_complaints", "linked_by", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("public_issue_updates", "author_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.alter_column("public_issue_updates", "author_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("public_issue_complaints", "linked_by", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("public_issues", "created_by", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("public_issues", "published_automatically")
    op.drop_column("public_issues", "auto_publish_at")
    op.drop_column("public_issues", "auto_generated")
