"""PostgreSQL migration and constraint checks; operator-created fresh DB only."""
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.base import Base
from app.identity.infrastructure import models  # noqa: F401
from app.finance.infrastructure import models as finance_models  # noqa: F401
from conftest import migrate, table_names


def test_upgrade_downgrade_upgrade(disposable_database_url):
    url = disposable_database_url
    migrate("head")
    assert asyncio.run(table_names(url)) == set(Base.metadata.tables) | {"alembic_version"}
    migrate("base", downgrade=True)
    assert asyncio.run(table_names(url)) == {"alembic_version"}
    migrate("head")

    async def verify():
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "000000000005"
                assert set((await connection.execute(text("SELECT code FROM roles"))).scalars()) == {
                    "OWNER", "ADMIN", "FINANCE_MANAGER", "INVENTORY_MANAGER", "MEMBER", "VIEWER",
                }
                differences = await connection.run_sync(lambda sync: compare_metadata(
                    MigrationContext.configure(sync), Base.metadata,
                ))
                assert differences == []
        finally:
            await engine.dispose()
    asyncio.run(verify())


INVALID_WRITES = [
    ("duplicate_email", "INSERT INTO users(email,email_key,password_hash) VALUES ('a@example.test','a@example.test','test-only')"),
    ("non_normalized_email", "INSERT INTO users(email,email_key,password_hash) VALUES (' B@example.test ','B@example.test','test-only')"),
    ("invalid_state", "UPDATE users SET state='UNKNOWN' WHERE id=101"),
    ("duplicate_membership", "INSERT INTO household_members(household_id,user_id,role_id) SELECT 201,101,id FROM roles WHERE code='OWNER'"),
    ("cross_household_invitation", "INSERT INTO household_invitations(household_id,email_key,role_id,inviter_member_id,token_digest,expires_at) SELECT 202,'b@example.test',id,301,repeat('a',64),now()+interval '1 day' FROM roles WHERE code='MEMBER'"),
    ("cross_household_actor", "INSERT INTO audit_logs(household_id,actor_member_id,request_id,action,target_type) VALUES (202,301,'test','TEST','test')"),
    ("conflicting_invitation_state", "INSERT INTO household_invitations(household_id,email_key,role_id,inviter_member_id,token_digest,expires_at,accepted_at,revoked_at) SELECT 201,'b@example.test',id,301,repeat('a',64),now()+interval '1 day',now(),now() FROM roles WHERE code='MEMBER'"),
    ("invalid_challenge_purpose", "INSERT INTO auth_challenges(user_id,purpose,token_digest,expires_at) VALUES (101,'BYPASS',repeat('a',64),now()+interval '1 hour')"),
    ("invalid_challenge_attempts", "INSERT INTO auth_challenges(user_id,purpose,token_digest,expires_at,failed_attempts) VALUES (101,'RESET_PASSWORD',repeat('a',64),now()+interval '1 hour',6)"),
    ("duplicate_active_challenge", "INSERT INTO auth_challenges(user_id,purpose,token_digest,expires_at) VALUES (101,'VERIFY_EMAIL',repeat('b',64),now()+interval '1 hour'),(101,'VERIFY_EMAIL',repeat('c',64),now()+interval '1 hour')"),
    ("plaintext_refresh", "INSERT INTO refresh_tokens(session_id,token_digest,expires_at) VALUES (401,'plaintext',now()+interval '1 day')"),
    ("invalid_grace", "INSERT INTO refresh_tokens(session_id,token_digest,expires_at,successor_ciphertext) VALUES (401,repeat('a',64),now()+interval '1 day',decode('ab','hex'))"),
    ("cross_session_successor", "INSERT INTO refresh_tokens(session_id,token_digest,expires_at,consumed_at,successor_id) VALUES (402,repeat('b',64),now()+interval '1 day',now(),501)"),
    ("nonpositive_rate_counter", "INSERT INTO auth_rate_limits VALUES ('login_ip',repeat('a',64),now(),0)"),
]


@pytest.mark.parametrize("case,sql", INVALID_WRITES, ids=[row[0] for row in INVALID_WRITES])
def test_constraints(identity_database, case, sql):
    async def verify():
        engine = create_async_engine(identity_database)
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    for statement in (
                        "INSERT INTO users(id,email,email_key,password_hash) VALUES (101,'a@example.test','a@example.test','test-only')",
                        "INSERT INTO households(id,name) VALUES (201,'One'),(202,'Two')",
                        "INSERT INTO household_members(id,household_id,user_id,role_id) SELECT 301,201,101,id FROM roles WHERE code='OWNER'",
                        "INSERT INTO auth_sessions(id,user_id,expires_at,csrf_digest) VALUES (401,101,now()+interval '1 day',repeat('d',64)),(402,101,now()+interval '1 day',repeat('e',64))",
                        "INSERT INTO refresh_tokens(id,session_id,token_digest,expires_at) VALUES (501,401,repeat('f',64),now()+interval '1 day')",
                    ):
                        await connection.execute(text(statement))
                    with pytest.raises(IntegrityError) as failure:
                        async with connection.begin_nested():
                            await connection.execute(text(sql))
                    expected = (
                        "23503" if case.startswith("cross_") else
                        "23505" if case.startswith("duplicate_") else "23514"
                    )
                    assert failure.value.orig.sqlstate == expected
                    # A rejected write must not poison the outer transaction.
                    assert (await connection.execute(text("SELECT count(*) FROM users"))).scalar_one() == 1
                finally:
                    await transaction.rollback()
                assert (await connection.execute(text("SELECT count(*) FROM users"))).scalar_one() == 0
        finally:
            await engine.dispose()
    asyncio.run(verify())
