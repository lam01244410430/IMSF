"""Step 4 household isolation, lifecycle, explicit RBAC, and transaction evidence."""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from conftest import cleanup_identity_database
from app.api.dependencies import get_db, get_email_provider, require_household_permission
from app.identity.household_dto import HouseholdCreate, InvitationCreate
from app.identity.household_service import HouseholdService, HouseholdRequestError
from app.identity.infrastructure.models import (
    AuditLog, AuthSession, Household, HouseholdInvitation, HouseholdMember, HouseholdSettings, Role, User,
)
from app.identity.permissions import PermissionCode as P, allows, can_grant
from app.identity.session_service import session_security
from app.main import create_app

BASE = "/api/v1/households"


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_ISSUER", "household-test")
    monkeypatch.setenv("JWT_AUDIENCE", "household-test")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://testserver")


@pytest.fixture
def database(identity_database):
    engine = create_async_engine(identity_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    asyncio.run(cleanup_identity_database(engine))


class RecordingEmail:
    def __init__(self):
        self.messages = []

    async def send(self, **message):
        self.messages.append(message)


async def records(factory, model):
    async with factory() as db:
        return list((await db.scalars(select(model).order_by(
            model.household_id if model is HouseholdSettings else model.id))).all())


async def principal(factory, email, state="ACTIVE"):
    now = datetime.now(timezone.utc)
    async with factory() as db, db.begin():
        user = User(email=email, email_key=email, state=state, password_hash="test-only-unused")
        db.add(user)
        await db.flush()
        family = AuthSession(user_id=user.id, created_at=now, last_activity_at=now,
                             expires_at=now + timedelta(days=1), csrf_digest="a" * 64)
        db.add(family)
        await db.flush()
        access = session_security().encode_access({"sub": str(user.id), "sid": family.id,
                                                   "iat": now, "exp": now + timedelta(minutes=15)})
        return SimpleNamespace(id=user.id, email=email, headers={"Authorization": "Bearer " + access})


@pytest.fixture
def h(database):
    app = create_app()
    provider = RecordingEmail()

    async def session():
        async with database() as db:
            yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_email_provider] = lambda: provider
    # These probes execute the production dependency used by future route groups.
    for permission in P:
        def add_probe(permission):
            @app.get(f"/permission/{permission.value}/{{household_id}}")
            async def probe(member: Annotated[object, Depends(require_household_permission(permission))]):
                return {"member_id": member.id}
        add_probe(permission)
    owner = asyncio.run(principal(database, "owner@example.test"))
    other = asyncio.run(principal(database, "other@example.test"))
    pending = asyncio.run(principal(database, "pending@example.test", "PENDING"))
    with TestClient(app, base_url="https://testserver") as client:
        def request(method, path="", *, actor=owner, **kwargs):
            return client.request(method, BASE + path, headers=actor.headers, **kwargs)
        yield SimpleNamespace(client=client, app=app, provider=provider, owner=owner,
                              other=other, pending=pending, request=request)


def create(h, actor=None):
    response = h.request("POST", actor=actor or h.owner, json={"name": "Family"})
    assert response.status_code == 201
    return response.json()["id"]


def members(h, hid):
    response = h.request("GET", f"/{hid}/members")
    assert response.status_code == 200
    return response.json()


def join(h, hid, actor, role="MEMBER", inviter=None):
    response = h.request("POST", f"/{hid}/invitations", actor=inviter or h.owner,
                         json={"email": actor.email, "role": role})
    assert response.status_code == 201
    raw = h.provider.messages[-1]["body"]
    response = h.request("POST", f"/{hid}/invitations/accept", actor=actor, json={"token": raw})
    assert response.status_code == 200
    return response.json()["id"]


# The expected matrix is independent of ROLE_PERMISSIONS and enumerates all grants.
GRANTS = {
    "OWNER": {"household.view", "household.settings", "household.members", "household.archive",
              "household.transfer", "audit.view", "finance.draft", "finance.post", "finance.reverse",
              "inventory.manage", "inventory.consumption_disposal", "recipes.cook_deduct", "recipes.edit"},
    "ADMIN": {"household.view", "household.settings", "household.members", "audit.view"},
    "FINANCE_MANAGER": {"household.view", "finance.draft", "finance.post", "finance.reverse", "recipes.edit"},
    "INVENTORY_MANAGER": {"household.view", "inventory.manage", "inventory.consumption_disposal", "recipes.cook_deduct"},
    "MEMBER": {"household.view", "finance.draft", "inventory.consumption_disposal", "recipes.edit"},
    "VIEWER": {"household.view"},
}


@pytest.mark.parametrize("role", GRANTS)
@pytest.mark.parametrize("permission", list(P) + ["unknown.write"])
def test_explicit_permission_matrix(role, permission):
    assert allows(role, permission) == (permission in GRANTS[role])
    assert not allows("UNKNOWN", permission)


@pytest.mark.parametrize("role", GRANTS)
def test_permission_dependency_matrix(h, role):
    hid = create(h)
    if role == "OWNER":
        actor = h.owner
    else:
        join(h, hid, h.other, role)
        actor = h.other
    for permission in P:
        response = h.client.get(f"/permission/{permission.value}/{hid}", headers=actor.headers)
        assert response.status_code == (200 if permission in GRANTS[role] else 403)
    # Every permission hides a household from a non-member.
    for permission in P:
        assert h.client.get(f"/permission/{permission.value}/{hid + 100000}",
                            headers=actor.headers).status_code == 404


@pytest.mark.parametrize("actor", GRANTS)
@pytest.mark.parametrize("target", GRANTS)
def test_grant_ceiling(actor, target):
    assert can_grant(actor, target) == (actor == "OWNER" or (actor == "ADMIN" and target not in {"OWNER", "ADMIN"}))
    assert not can_grant(actor, "UNKNOWN")


def test_create_get_list_settings_and_archive(h, database):
    hid = create(h)
    result = h.request("GET", f"/{hid}")
    assert result.status_code == 200 and result.json()["settings"] == {}
    assert [row["id"] for row in h.request("GET").json()] == [hid]
    assert h.request("GET", actor=h.other).json() == []
    assert members(h, hid)[0]["role"] == "OWNER"
    settings = asyncio.run(records(database, HouseholdSettings))
    assert len(settings) == 1 and settings[0].values == {}
    response = h.request("PATCH", f"/{hid}", json={"name": "Renamed", "settings": {"currency": "USD", "timezone": "UTC"}})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed" and response.json()["settings"] == {"currency": "USD", "timezone": "UTC"}
    assert h.request("POST", f"/{hid}/archive").status_code == 204
    assert h.request("GET", f"/{hid}").json()["archived_at"] is not None
    assert h.request("PATCH", f"/{hid}", json={"name": "Forbidden"}).status_code == 409
    assert h.request("POST", f"/{hid}/invitations", json={"email": h.other.email, "role": "MEMBER"}).status_code == 409
    assert len(h.request("GET").json()) == 1


@pytest.mark.parametrize("role", list(GRANTS)[1:])
def test_household_endpoint_role_rules(h, role):
    hid = create(h)
    mid = join(h, hid, h.other, role)
    for suffix in (f"/{hid}", f"/{hid}/members"):
        assert h.request("GET", suffix, actor=h.other).status_code == 200
    assert h.request("PATCH", f"/{hid}", actor=h.other, json={"settings": {"locale": "vi"}}).status_code == (200 if role == "ADMIN" else 403)
    assert h.request("PATCH", f"/{hid}", actor=h.other, json={"settings": {"currency": "VND"}}).status_code == 403
    assert h.request("PATCH", f"/{hid}", actor=h.other, json={"name": "Admin rename"}).status_code == 403
    assert h.request("POST", f"/{hid}/archive", actor=h.other).status_code == 403
    assert h.request("POST", f"/{hid}/transfer", actor=h.other, json={"member_id": mid}).status_code == 403
    assert h.request("POST", f"/{hid}/invitations", actor=h.other,
                     json={"email": "new@example.test", "role": "VIEWER"}).status_code == (201 if role == "ADMIN" else 403)


@pytest.mark.parametrize("method,path,body", [
    ("POST", "", {"name": "Pending"}), ("GET", "", None), ("GET", "/{hid}", None),
    ("GET", "/{hid}/members", None), ("PATCH", "/{hid}", {"name": "No"}),
    ("POST", "/{hid}/invitations", {"email": "a@example.test", "role": "MEMBER"}),
    ("POST", "/{hid}/invitations/accept", {"token": "unknown"}),
    ("POST", "/{hid}/archive", None), ("POST", "/{hid}/transfer", {"member_id": 1}),
    ("PATCH", "/{hid}/members/1", {"role": "MEMBER"}), ("DELETE", "/{hid}/members/1", None),
    ("DELETE", "/{hid}/invitations/1", None),
])
def test_pending_cannot_create_join_or_access(h, method, path, body):
    hid = create(h)
    response = h.request(method, path.format(hid=hid), actor=h.pending, **({"json": body} if body else {}))
    assert response.status_code == 403
    assert set(response.json()) == {"error_code", "details", "request_id"}


def test_pending_with_valid_invitation_is_blocked(h, database):
    hid = create(h)
    h.request("POST", f"/{hid}/invitations", json={"email": h.pending.email, "role": "MEMBER"})
    raw = h.provider.messages[-1]["body"]
    assert h.request("POST", f"/{hid}/invitations/accept", actor=h.pending, json={"token": raw}).status_code == 403
    assert len(members(h, hid)) == 1
    assert asyncio.run(records(database, HouseholdInvitation))[0].accepted_at is None


def test_invitation_provenance_replacement_single_use_and_audit(h, database):
    hid = create(h)
    first = h.request("POST", f"/{hid}/invitations", json={"email": " OTHER@EXAMPLE.TEST ", "role": "MEMBER"})
    raw_old = h.provider.messages[-1]["body"]
    assert first.status_code == 201 and raw_old not in first.text
    second = h.request("POST", f"/{hid}/invitations", json={"email": h.other.email, "role": "VIEWER"})
    raw = h.provider.messages[-1]["body"]
    assert second.status_code == 201 and raw not in second.text
    invitations = asyncio.run(records(database, HouseholdInvitation))
    assert invitations[0].revoked_at is not None
    assert invitations[0].inviter_member_id == invitations[1].inviter_member_id == members(h, hid)[0]["id"]
    assert invitations[1].email_key == h.other.email
    assert invitations[1].expires_at - invitations[1].created_at == timedelta(days=7)
    assert invitations[1].emailed_at is not None and invitations[1].token_digest != raw
    assert h.request("POST", f"/{hid}/invitations/accept", actor=h.other, json={"token": raw_old}).status_code == 404
    assert h.request("POST", f"/{hid}/invitations/accept", json={"token": raw}).status_code == 404
    accepted = h.request("POST", f"/{hid}/invitations/accept", actor=h.other, json={"token": raw})
    assert accepted.status_code == 200 and accepted.json()["role"] == "VIEWER"
    assert h.request("POST", f"/{hid}/invitations/accept", actor=h.other, json={"token": raw}).status_code == 404
    actions = [a.action for a in asyncio.run(records(database, AuditLog))]
    assert actions.count("INVITATION_CREATED") == 2
    assert actions.count("INVITATION_REVOKED") == actions.count("INVITATION_ACCEPTED") == 1
    assert all(raw not in str(a.details) for a in asyncio.run(records(database, AuditLog)))


@pytest.mark.parametrize("delivery", ["none", "failure"])
def test_no_provider_or_delivery_failure_persists_without_disclosing_token(h, database, delivery):
    hid = create(h)
    class FailedEmail:
        async def send(self, **message):
            raise RuntimeError("provider failure with secret body")
    h.app.dependency_overrides[get_email_provider] = lambda: None if delivery == "none" else FailedEmail()
    response = h.request("POST", f"/{hid}/invitations", json={"email": h.other.email, "role": "MEMBER"})
    assert response.status_code == 201 and response.json()["emailed_at"] is None
    assert not any("token" in key or "digest" in key for key in response.json())
    assert len(asyncio.run(records(database, HouseholdInvitation))) == 1


@pytest.mark.parametrize("final", ["expired", "revoked"])
def test_invitation_expiry_and_revoke(h, database, final):
    hid = create(h)
    response = h.request("POST", f"/{hid}/invitations", json={"email": h.other.email, "role": "MEMBER"})
    iid = response.json()["id"]
    raw = h.provider.messages[-1]["body"]
    if final == "expired":
        async def expire():
            async with database() as db, db.begin():
                await db.execute(update(HouseholdInvitation).where(HouseholdInvitation.id == iid).values(expires_at=datetime.now(timezone.utc)))
        asyncio.run(expire())
    else:
        assert h.request("DELETE", f"/{hid}/invitations/{iid}").status_code == 204
        assert h.request("DELETE", f"/{hid}/invitations/{iid}").status_code == 409
        assert "INVITATION_REVOKED" in [a.action for a in asyncio.run(records(database, AuditLog))]
    assert h.request("POST", f"/{hid}/invitations/accept", actor=h.other, json={"token": raw}).status_code == 404
    assert len(members(h, hid)) == 1


def test_role_patch_no_self_change_admin_limits_and_delete(h, database):
    hid = create(h)
    owner_mid = members(h, hid)[0]["id"]
    admin_mid = join(h, hid, h.other, "ADMIN")
    third = asyncio.run(principal(database, "third@example.test"))
    third_mid = join(h, hid, third, "MEMBER", inviter=h.other)
    assert h.request("PATCH", f"/{hid}/members/{owner_mid}", json={"role": "ADMIN"}).status_code == 403
    assert h.request("PATCH", f"/{hid}/members/{admin_mid}", actor=h.other, json={"role": "VIEWER"}).status_code == 403
    for role in ("ADMIN", "OWNER"):
        assert h.request("PATCH", f"/{hid}/members/{third_mid}", actor=h.other, json={"role": role}).status_code == 403
        assert h.request("POST", f"/{hid}/invitations", actor=h.other, json={"email": "new@example.test", "role": role}).status_code == 403
    assert h.request("PATCH", f"/{hid}/members/{owner_mid}", actor=h.other, json={"role": "MEMBER"}).status_code == 403
    assert h.request("DELETE", f"/{hid}/members/{owner_mid}", actor=h.other).status_code == 403
    assert h.request("DELETE", f"/{hid}/members/{admin_mid}", actor=h.other).status_code == 403
    assert h.request("PATCH", f"/{hid}/members/{third_mid}", actor=h.other, json={"role": "FINANCE_MANAGER"}).status_code == 200
    assert h.request("DELETE", f"/{hid}/members/{third_mid}", actor=h.other).status_code == 204
    assert h.request("DELETE", f"/{hid}/members/{admin_mid}").status_code == 204


def test_last_owner_rejection_and_owner_promotion(h):
    hid = create(h)
    owner_mid = members(h, hid)[0]["id"]
    assert h.request("DELETE", f"/{hid}/members/{owner_mid}").status_code == 409
    other_mid = join(h, hid, h.other, "MEMBER")
    assert h.request("PATCH", f"/{hid}/members/{other_mid}", json={"role": "OWNER"}).status_code == 200
    assert h.request("PATCH", f"/{hid}/members/{owner_mid}", actor=h.other, json={"role": "ADMIN"}).status_code == 200
    assert h.request("DELETE", f"/{hid}/members/{other_mid}", actor=h.other).status_code == 409
    assert h.request("PATCH", f"/{hid}/members/{other_mid}", json={"role": "VIEWER"}).status_code == 403
    assert sorted(m["role"] for m in members(h, hid)) == ["ADMIN", "OWNER"]


def test_transfer_requires_active_member_and_demotes_old_owner(h, database):
    hid = create(h)
    owner_mid = members(h, hid)[0]["id"]
    assert h.request("POST", f"/{hid}/transfer", json={"member_id": owner_mid}).status_code == 409
    assert h.request("POST", f"/{hid}/transfer", json={"member_id": 999999}).status_code == 404
    mid = join(h, hid, h.other, "VIEWER")
    async def state(value):
        async with database() as db, db.begin():
            await db.execute(update(User).where(User.id == h.other.id).values(state=value))
    asyncio.run(state("PENDING"))
    assert h.request("POST", f"/{hid}/transfer", json={"member_id": mid}).status_code == 409
    asyncio.run(state("ACTIVE"))
    assert h.request("POST", f"/{hid}/transfer", json={"member_id": mid}).status_code == 204
    assert {m["id"]: m["role"] for m in members(h, hid)} == {owner_mid: "ADMIN", mid: "OWNER"}
    assert h.request("POST", f"/{hid}/archive").status_code == 403
    assert h.request("POST", f"/{hid}/archive", actor=h.other).status_code == 204


def test_cross_household_object_isolation_and_removed_member_sessions(h, database):
    hid = create(h)
    second = create(h)
    mid = join(h, hid, h.other, "MEMBER")
    second_mid = join(h, second, h.other, "VIEWER")
    third = create(h, h.other)
    iid = h.request("POST", f"/{second}/invitations", json={"email": "new@example.test", "role": "MEMBER"}).json()["id"]
    for method, path, body in [
        ("GET", f"/{third}", None), ("GET", f"/{third}/members", None),
        ("PATCH", f"/{third}", {"name": "No"}), ("POST", f"/{third}/archive", None),
        ("PATCH", f"/{hid}/members/{second_mid}", {"role": "VIEWER"}),
        ("DELETE", f"/{hid}/members/{second_mid}", None),
        ("POST", f"/{hid}/transfer", {"member_id": second_mid}),
        ("DELETE", f"/{hid}/invitations/{iid}", None),
    ]:
        assert h.request(method, path, **({"json": body} if body else {})).status_code == 404
    assert h.request("DELETE", f"/{hid}/members/{mid}").status_code == 204
    assert h.request("GET", f"/{hid}", actor=h.other).status_code == 404
    assert h.request("GET", f"/{second}", actor=h.other).status_code == 200
    assert h.client.get("/api/v1/users/me", headers=h.other.headers).status_code == 200
    assert all(s.revoked_at is None for s in asyncio.run(records(database, AuthSession)))
    # Rejoining reuses the unique membership row without losing old audit provenance.
    assert join(h, hid, h.other, "VIEWER") == mid


def test_inviter_demotion_invalidates_outstanding_admin_grant(h):
    hid = create(h)
    mid = join(h, hid, h.other, "OWNER")
    response = h.request("POST", f"/{hid}/invitations", actor=h.other, json={"email": "new@example.test", "role": "OWNER"})
    iid = response.json()["id"]
    assert h.request("PATCH", f"/{hid}/members/{mid}", json={"role": "ADMIN"}).status_code == 200
    assert h.request("DELETE", f"/{hid}/invitations/{iid}", actor=h.other).status_code == 403


def test_transaction_rollback_on_audit_failure(h, database, monkeypatch):
    hid = create(h)
    async def scenario():
        async with database() as db:
            service = HouseholdService(db)
            def fail(*args):
                raise RuntimeError("test audit failure")
            monkeypatch.setattr(service, "_audit", fail)
            with pytest.raises(RuntimeError, match="test audit failure"):
                await service.invite(h.owner.id, hid, InvitationCreate(email=h.other.email, role="MEMBER"))
        assert await records(database, HouseholdInvitation) == []
    asyncio.run(scenario())


def test_concurrent_invites_and_accept_are_serialized(h, database):
    hid = create(h)
    async def scenario():
        provider = RecordingEmail()
        async def invite():
            async with database() as db:
                return await HouseholdService(db, provider).invite(h.owner.id, hid,
                    InvitationCreate(email=h.other.email, role="MEMBER"))
        await asyncio.gather(invite(), invite())
        invitations = await records(database, HouseholdInvitation)
        assert len(invitations) == 2 and sum(i.revoked_at is None for i in invitations) == 1
        # Match only the current digest; delivery scheduling need not match commit order.
        from app.identity.infrastructure.security import token_digest
        current = next(i for i in invitations if i.revoked_at is None)
        raw = next(m["body"] for m in provider.messages if token_digest(m["body"]) == current.token_digest)
        async def accept():
            async with database() as db:
                try:
                    await HouseholdService(db).accept(h.other.id, hid, raw)
                    return 200
                except HouseholdRequestError as exc:
                    return exc.status_code
        assert sorted(await asyncio.gather(accept(), accept())) == [200, 404]
        rows = await records(database, HouseholdMember)
        assert sum(m.user_id == h.other.id for m in rows) == 1
    asyncio.run(scenario())


def test_concurrent_owners_cannot_remove_each_other(h, database):
    hid = create(h)
    first_mid = members(h, hid)[0]["id"]
    second_mid = join(h, hid, h.other, "OWNER")
    async def scenario():
        async def remove(uid, mid):
            async with database() as db:
                try:
                    await HouseholdService(db).remove(uid, hid, mid)
                    return 204
                except HouseholdRequestError as exc:
                    return exc.status_code
        assert sorted(await asyncio.gather(remove(h.owner.id, second_mid), remove(h.other.id, first_mid))) == [204, 404]
        assert len([m for m in await records(database, HouseholdMember) if m.removed_at is None]) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("body", [{"name": " "}, {"name": "Valid", "unknown": True}])
def test_invalid_create_contract(h, body):
    assert h.request("POST", json=body).status_code == 422


def test_authentication_and_settings_validation(h):
    assert h.client.get(BASE).status_code == 401
    hid = create(h)
    for settings in ({"timezone": "not/a/zone"}, {"currency": "usd"}, {"unknown": "x"}):
        assert h.request("PATCH", f"/{hid}", json={"settings": settings}).status_code == 422
    assert h.request("PATCH", f"/{hid}/members/{members(h, hid)[0]['id']}", json={"role": "UNKNOWN"}).status_code == 422
    response = h.client.options(BASE + f"/{hid}/members/1", headers={"Origin": "https://testserver", "Access-Control-Request-Method": "DELETE"})
    assert response.status_code == 200


def test_acceptance_rechecks_inviter_grants_and_archival(h, database):
    hid = create(h)
    mid = join(h, hid, h.other, "OWNER")
    third = asyncio.run(principal(database, "third@example.test"))
    assert h.request("POST", f"/{hid}/invitations", actor=h.other,
                     json={"email": third.email, "role": "OWNER"}).status_code == 201
    raw = h.provider.messages[-1]["body"]
    assert h.request("PATCH", f"/{hid}/members/{mid}", json={"role": "ADMIN"}).status_code == 200
    assert h.request("POST", f"/{hid}/invitations/accept", actor=third, json={"token": raw}).status_code == 403
    assert h.request("POST", f"/{hid}/invitations", json={"email": third.email, "role": "MEMBER"}).status_code == 201
    raw = h.provider.messages[-1]["body"]
    assert h.request("POST", f"/{hid}/archive").status_code == 204
    assert h.request("POST", f"/{hid}/invitations/accept", actor=third, json={"token": raw}).status_code == 409


def test_members_cannot_manage_members_or_invitations(h):
    hid = create(h)
    owner_mid = members(h, hid)[0]["id"]
    join(h, hid, h.other, "VIEWER")
    iid = h.request("POST", f"/{hid}/invitations", json={"email": "new@example.test", "role": "MEMBER"}).json()["id"]
    assert h.request("PATCH", f"/{hid}/members/{owner_mid}", actor=h.other, json={"role": "VIEWER"}).status_code == 403
    assert h.request("DELETE", f"/{hid}/members/{owner_mid}", actor=h.other).status_code == 403
    assert h.request("DELETE", f"/{hid}/invitations/{iid}", actor=h.other).status_code == 403


@pytest.mark.parametrize("role", ["OWNER", "ADMIN"])
def test_admin_cannot_replace_higher_role_invitation(h, database, role):
    hid = create(h)
    join(h, hid, h.other, "ADMIN")
    response = h.request("POST", f"/{hid}/invitations", json={"email": "new@example.test", "role": role})
    iid = response.json()["id"]
    before = len(asyncio.run(records(database, AuditLog)))
    response = h.request("POST", f"/{hid}/invitations", actor=h.other,
                         json={"email": "new@example.test", "role": "VIEWER"})
    assert response.status_code == 403
    invitations = asyncio.run(records(database, HouseholdInvitation))
    assert next(i for i in invitations if i.id == iid).revoked_at is None
    assert len(invitations) == 2  # Includes the already accepted ADMIN invitation.
    assert len(asyncio.run(records(database, AuditLog))) == before


def test_last_active_owner_cannot_become_pending_via_email_change(h, database):
    hid = create(h)
    response = h.client.patch("/api/v1/auth/email", headers=h.owner.headers, json={"email": "changed@example.test"})
    assert response.status_code == 400
    assert h.client.get("/api/v1/users/me", headers=h.owner.headers).json()["state"] == "ACTIVE"
    assert h.request("GET", f"/{hid}").status_code == 200
    join(h, hid, h.other, "OWNER")
    response = h.client.patch("/api/v1/auth/email", headers=h.owner.headers, json={"email": "changed@example.test"})
    assert response.status_code == 200
    assert h.client.get("/api/v1/users/me", headers=h.owner.headers).json()["state"] == "PENDING"
    assert h.request("GET", f"/{hid}").status_code == 403
    assert h.request("GET", f"/{hid}", actor=h.other).status_code == 200


def test_concurrent_email_change_and_transfer_preserve_active_owner(h, database):
    from app.identity.auth_service import AuthService, IdentityRequestError
    hid = create(h)
    mid = join(h, hid, h.other, "MEMBER")
    async def scenario():
        async def change_email():
            async with database() as db:
                try:
                    await AuthService(db).change_email(h.other.id, "changed@example.test")
                    return 200
                except IdentityRequestError:
                    return 400
        async def transfer():
            async with database() as db:
                try:
                    await HouseholdService(db).transfer(h.owner.id, hid, mid)
                    return 204
                except HouseholdRequestError as exc:
                    return exc.status_code
        results = await asyncio.gather(change_email(), transfer())
        assert results in ([200, 409], [400, 204])
        async with database() as db:
            owners = (await db.scalars(select(HouseholdMember).join(Role, Role.id == HouseholdMember.role_id).join(
                User, User.id == HouseholdMember.user_id).where(HouseholdMember.household_id == hid,
                    HouseholdMember.removed_at.is_(None), Role.code == "OWNER", User.state == "ACTIVE"))).all()
            assert len(owners) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["change_role", "remove", "transfer"])
def test_membership_mutation_rolls_back_on_audit_failure(h, database, monkeypatch, operation):
    hid = create(h)
    mid = join(h, hid, h.other, "MEMBER")
    before = members(h, hid)
    async def scenario():
        async with database() as db:
            service = HouseholdService(db)
            def fail(*args):
                raise RuntimeError("test audit failure")
            monkeypatch.setattr(service, "_audit", fail)
            args = (h.owner.id, hid, mid, "OWNER") if operation == "change_role" else (h.owner.id, hid, mid)
            with pytest.raises(RuntimeError, match="test audit failure"):
                await getattr(service, operation)(*args)
    asyncio.run(scenario())
    assert members(h, hid) == before
