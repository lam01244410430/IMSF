"""0006_email_password_auth - email + password login (reform plan SS7.2).

Adds ``email VARCHAR(254)`` (UNIQUE, nullable) and ``password_hash
TEXT`` (nullable) to ``users`` and replaces the login-channel CHECK so
a row is valid when it has (email AND password_hash) OR wechat_openid
OR phone. Email alone is NOT a login method; password_hash alone is
not either -- the pair must go together.

Email is normalised at the application layer (strip().lower() before
every read/write); no CITEXT extension is required.

NO EMAIL VERIFICATION in v1: the system has no SMTP / email-sending
infrastructure, so there is no verification flow. Consequences, stated
explicitly:
- Anyone can register with someone else's email address.
- The system must NEVER send sensitive information to an unverified
  email address.
- An unverified email cannot be used to reset a password (there is no
  reset endpoint in v1; password resets are admin-only, by script).
When email infrastructure exists, a later migration adds
``email_verified_at TIMESTAMPTZ NULL`` + a verification endpoint; only
then may an email count as a verified identity.

Backfill: existing users (WeChat-only, phone-only, the service user
``wechat_openid = 'imsf-service'``) keep email NULL + password_hash
NULL and still satisfy the new CHECK via wechat_openid / phone. Pure
ADD COLUMN + CHECK swap, no long table lock, no downtime.

Downgrade is ONLY safe before any email user exists: it drops the two
columns and restores the old CHECK. If an email-only user already
exists, downgrading would violate the restored CHECK (that row has
neither phone nor wechat_openid), so do NOT downgrade a database that
already has email users.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_NEW_CHECK = (
    "(email IS NOT NULL AND password_hash IS NOT NULL)"
    " OR wechat_openid IS NOT NULL OR phone IS NOT NULL"
)
_OLD_CHECK = "phone IS NOT NULL OR wechat_openid IS NOT NULL"


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.drop_constraint("ck_users_login_channel", "users", type_="check")
    op.create_check_constraint("ck_users_login_channel", "users", _NEW_CHECK)


def downgrade() -> None:
    op.drop_constraint("ck_users_login_channel", "users", type_="check")
    op.create_check_constraint("ck_users_login_channel", "users", _OLD_CHECK)
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
