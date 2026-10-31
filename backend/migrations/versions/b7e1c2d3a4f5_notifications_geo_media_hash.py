"""notification channels, push subscriptions, language, image perceptual hash

Revision ID: b7e1c2d3a4f5
Revises: cf26600c2038
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e1c2d3a4f5"
down_revision = "cf26600c2038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notify_email", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("notify_sms", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("notify_push", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("preferred_language", sa.String(8), server_default="en", nullable=False))
    op.add_column("media", sa.Column("perceptual_hash", sa.String(16), nullable=True))
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("notification_id", sa.Uuid(), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("delivery_status", sa.Enum("PENDING", "SENT", "FAILED", name="deliverystatus", native_enum=False, length=40), nullable=False),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("notification_id", "channel"),
    )
    op.create_index("ix_notification_deliveries_notification_id", "notification_deliveries", ["notification_id"])
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    op.drop_table("notification_deliveries")
    op.drop_column("media", "perceptual_hash")
    for c in ("preferred_language", "notify_push", "notify_sms", "notify_email"):
        op.drop_column("users", c)
