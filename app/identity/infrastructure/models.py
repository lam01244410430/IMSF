"""Identity schema. Composite foreign keys enforce household ownership.

Runtime grants and the application layer must enforce append-only audit access,
active-owner preservation, permission ceilings, and token consumption ordering.
"""

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Key:
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)


class User(Key, Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint("email_key = lower(btrim(email)) AND length(email_key) > 0", name="ck_users_email_key"),
        sa.CheckConstraint("state IN ('PENDING','ACTIVE','DISABLED')", name="ck_users_state"),
        sa.CheckConstraint("locale IN ('en','vi','zh-Hans')", name="ck_users_locale"),
    )
    email: Mapped[str] = mapped_column(sa.Text)
    email_key: Mapped[str] = mapped_column(sa.Text, unique=True)
    password_hash: Mapped[str] = mapped_column(sa.Text)
    locale: Mapped[str] = mapped_column(sa.Text, server_default="en")
    state: Mapped[str] = mapped_column(sa.Text, server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Household(Key, Base):
    __tablename__ = "households"
    name: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Role(Key, Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(sa.Text, unique=True)


class Permission(Key, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(sa.Text, unique=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(sa.ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(sa.ForeignKey("permissions.id"), primary_key=True)


class HouseholdMember(Key, Base):
    __tablename__ = "household_members"
    __table_args__ = (
        sa.UniqueConstraint("household_id", "id"),
        sa.UniqueConstraint("household_id", "user_id"),
    )
    household_id: Mapped[int] = mapped_column(sa.ForeignKey("households.id"), index=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), index=True)
    role_id: Mapped[int] = mapped_column(sa.ForeignKey("roles.id"))
    joined_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    removed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class HouseholdInvitation(Key, Base):
    __tablename__ = "household_invitations"
    __table_args__ = (
        sa.UniqueConstraint("household_id", "id"),
        sa.ForeignKeyConstraint(["household_id", "inviter_member_id"], ["household_members.household_id", "household_members.id"]),
        sa.CheckConstraint("NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)", name="ck_invitations_final_state"),
        sa.CheckConstraint("email_key = lower(btrim(email_key)) AND length(email_key) > 0", name="ck_invitations_email_key"),
        sa.CheckConstraint("token_digest ~ '^[0-9a-f]{64}$'", name="ck_invitations_digest"),
    )
    household_id: Mapped[int] = mapped_column(sa.ForeignKey("households.id"), index=True)
    email_key: Mapped[str] = mapped_column(sa.Text)
    role_id: Mapped[int] = mapped_column(sa.ForeignKey("roles.id"))
    inviter_member_id: Mapped[int] = mapped_column(sa.BigInteger)
    token_digest: Mapped[str] = mapped_column(sa.String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    emailed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuthSession(Key, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (sa.UniqueConstraint("id", "user_id"),)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    last_activity_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    csrf_digest: Mapped[str] = mapped_column(sa.String(64))


class RefreshToken(Key, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "id"),
        sa.ForeignKeyConstraint(["session_id", "successor_id"], ["refresh_tokens.session_id", "refresh_tokens.id"]),
        sa.CheckConstraint("token_digest ~ '^[0-9a-f]{64}$'", name="ck_refresh_digest"),
        sa.CheckConstraint("(successor_ciphertext IS NULL AND grace_expires_at IS NULL) OR (successor_ciphertext IS NOT NULL AND grace_expires_at IS NOT NULL AND consumed_at IS NOT NULL AND successor_id IS NOT NULL AND grace_expires_at = consumed_at + interval '10 seconds')", name="ck_refresh_grace"),
        sa.CheckConstraint("successor_id IS NULL OR (successor_id <> id AND consumed_at IS NOT NULL)", name="ck_refresh_successor"),
    )
    session_id: Mapped[int] = mapped_column(sa.ForeignKey("auth_sessions.id"), index=True)
    token_digest: Mapped[str] = mapped_column(sa.String(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    successor_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    # MANAGER PROPOSAL (merge gate): SHA-256 digests at rest; the issued
    # successor is encrypted under a separate env key for exactly 10 seconds.
    successor_ciphertext: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    grace_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuthChallenge(Key, Base):
    __tablename__ = "auth_challenges"
    __table_args__ = (
        sa.CheckConstraint("purpose IN ('VERIFY_EMAIL','RESET_PASSWORD')", name="ck_challenges_purpose"),
        sa.CheckConstraint("failed_attempts BETWEEN 0 AND 5", name="ck_challenges_attempts"),
        sa.CheckConstraint("token_digest ~ '^[0-9a-f]{64}$'", name="ck_challenges_digest"),
        sa.Index("uq_challenges_unconsumed", "user_id", "purpose", unique=True, postgresql_where=sa.text("consumed_at IS NULL")),
    )
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(sa.Text)
    token_digest: Mapped[str] = mapped_column(sa.String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(sa.Integer, server_default="0")


class AuditLog(Key, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        sa.UniqueConstraint("household_id", "id"),
        sa.ForeignKeyConstraint(["household_id", "actor_member_id"], ["household_members.household_id", "household_members.id"]),
    )
    household_id: Mapped[int] = mapped_column(sa.ForeignKey("households.id"), index=True)
    actor_member_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    event_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    request_id: Mapped[str] = mapped_column(sa.Text)
    action: Mapped[str] = mapped_column(sa.Text)
    target_type: Mapped[str] = mapped_column(sa.Text)
    target_id: Mapped[str | None] = mapped_column(sa.Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))


class AuthAuditEvent(Key, Base):
    __tablename__ = "auth_audit_events"
    user_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id"), index=True)
    event_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    request_id: Mapped[str] = mapped_column(sa.Text)
    event_code: Mapped[str] = mapped_column(sa.Text)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (sa.CheckConstraint("attempts > 0", name="ck_rate_limits_attempts"),)
    scope: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    subject_digest: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), primary_key=True)
    attempts: Mapped[int] = mapped_column(sa.Integer)
