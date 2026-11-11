"""Inventory extends the decided P03 key protocol, including DATE values."""

import asyncio
import httpx
from test_inventory_lots import product
from test_finance_transactions import query


def test_same_key_same_body_replays_identical_bytes_and_changed_payload_conflicts(f):
    p = product(f)
    body = {
        "product_id": p["id"],
        "source_kind": "GIFT",
        "quantity": "2",
        "unit_id": p["base_unit_id"],
        "received_at": "2026-11-11T10:00:00Z",
        "expires_on": "2027-01-01",
    }
    r = f.request("POST", "/inventory-lots", key="same", json=body)
    replay = f.request(
        "POST", "/inventory-lots", key="same", json=body | {"quantity": "2.000000"}
    )
    assert r.status_code == replay.status_code == 201 and r.content == replay.content
    conflict = f.request(
        "POST", "/inventory-lots", key="same", json=body | {"expires_on": "2027-01-02"}
    )
    assert (
        conflict.status_code == 409
        and conflict.json()["error_code"] == "INVENTORY_IDEMPOTENCY_CONFLICT"
    )
    lid = r.json()["id"]
    for expiry in ["2027-02-01", None]:
        first = f.request(
            "PATCH",
            f"/inventory-lots/{lid}",
            key=str(expiry),
            json={"expires_on": expiry, "reason": "Label"},
        )
        second = f.request(
            "PATCH",
            f"/inventory-lots/{lid}",
            key=str(expiry),
            json={"expires_on": expiry, "reason": "Label"},
        )
        assert (
            first.status_code == second.status_code == 200
            and first.content == second.content
        )
    assert (
        len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid")) == 1
    )


def test_concurrent_same_key_has_one_effect(f):
    p = product(f)

    async def run():
        barrier = asyncio.Barrier(2)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=f.app), base_url="https://testserver"
        ) as client:

            async def call():
                await barrier.wait()
                return await client.post(
                    f"/api/v1/households/{f.hid}/inventory-lots",
                    headers=f.actors["OWNER"].headers | {"Idempotency-Key": "race"},
                    json={
                        "product_id": p["id"],
                        "source_kind": "GIFT",
                        "quantity": "1",
                        "unit_id": p["base_unit_id"],
                        "received_at": "2026-11-11T10:00:00Z",
                    },
                )

            a, b = await asyncio.gather(call(), call())
            assert a.status_code == b.status_code == 201 and a.content == b.content

    asyncio.run(run())
    assert len(query(f, "SELECT id FROM inventory_lots WHERE household_id=:hid")) == 1
    assert (
        len(query(f, "SELECT id FROM inventory_movements WHERE household_id=:hid")) == 1
    )


import pytest


@pytest.mark.parametrize('route', ['deductions','purchases'])
def test_checkout_replay_same_key_body_and_date_canonicalization(f, route):
    from test_inventory_checkout import configure_timezone, demand, purchase_body
    from test_inventory_lots import receipt
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    body = demand(p) if route=='deductions' else purchase_body(f,p)[1]
    path = '/checkout/'+route
    a = f.request('POST',path,key='checkout-replay',json=body)
    assert a.status_code == 201, a.text
    if route == 'purchases':
        body['lots'][0]['expires_on'] = '2027-01-01T00:00:00Z'
        body['lots'][0]['quantity'] = '2.000000'
    else:
        body['items'][0]['quantity'] = '4.000000'
    b = f.request('POST',path,key='checkout-replay',json=body)
    assert b.status_code == 201 and a.content == b.content
    if route=='purchases':
        body['lots'][0]['expires_on'] = '2027-01-02'
    else:
        body['items'][0]['quantity'] = '3'
    r = f.request('POST',path,key='checkout-replay',json=body)
    assert r.status_code == 409 and r.json()['error_code'] == 'INVENTORY_IDEMPOTENCY_CONFLICT'


@pytest.mark.parametrize('route', ['deductions','purchases'])
def test_checkout_concurrent_same_key_one_effect(f, route):
    from test_inventory_checkout import configure_timezone, demand, purchase_body
    from test_inventory_lots import receipt
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    body = demand(p) if route=='deductions' else purchase_body(f,p)[1]
    async def run():
        barrier = asyncio.Barrier(2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app),base_url='https://testserver') as client:
            async def call():
                await barrier.wait()
                return await client.post(f'/api/v1/households/{f.hid}/checkout/{route}',headers=f.actors['OWNER'].headers | {'Idempotency-Key':'same-checkout'},json=body)
            a,b = await asyncio.gather(call(),call())
            assert a.status_code == b.status_code == 201 and a.content == b.content
    asyncio.run(run())
    assert len(query(f,"SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='same-checkout'")) == 1
    assert len(query(f,'SELECT id FROM inventory_lots WHERE household_id=:hid')) == (1 if route=='deductions' else 3)
    assert len(query(f,'SELECT id FROM consumption_records WHERE household_id=:hid')) == (1 if route=='deductions' else 0)


@pytest.mark.parametrize('route', ['deductions','purchases'])
@pytest.mark.parametrize('failures', [2,3])
def test_checkout_retry_exhaustion_rolls_back_whole_use_case(f, monkeypatch, route, failures):
    from sqlalchemy.exc import DBAPIError
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    from test_inventory_checkout import configure_timezone, demand, purchase_body, snapshot
    from test_inventory_lots import receipt
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    body = demand(p) if route=='deductions' else purchase_body(f,p)[1]
    before = snapshot(f)
    original = SqlAlchemyFinanceRepository.complete
    attempts = []
    class SerializationFailure(Exception):
        sqlstate = '40001'
    async def fail(self,*args):
        await original(self,*args)
        attempts.append(1)
        if len(attempts) <= failures:
            raise DBAPIError('injected',None,SerializationFailure())
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyFinanceRepository,'complete',fail)
        r = f.request('POST','/checkout/'+route,key='retry',json=body)
    assert len(attempts) == 3
    if failures == 3:
        assert r.status_code == 409 and r.json()['error_code'] == 'INVENTORY_RETRY_EXHAUSTED'
        assert snapshot(f) == before
        assert f.request('POST','/checkout/'+route,key='retry',json=body).status_code == 201
    else:
        assert r.status_code == 201
        assert len(query(f,"SELECT id FROM idempotency_requests WHERE household_id=:hid AND request_key='retry'")) == 1


@pytest.mark.parametrize('operation', ['create','patch','ingredient-add','ingredient-patch','archive','cook'])
def test_recipe_mutations_replay_identical_bytes_and_conflict(f, operation):
    from test_inventory_cooking import recipe, ingredient, state
    from test_inventory_checkout import configure_timezone
    from test_inventory_lots import receipt
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    r = recipe(f,p)
    prefix = f"/recipes/{r['id']}"
    method,path,body,changed = {
        'create': ('POST','/recipes',{'name':'New','servings':'1','ingredients':[ingredient(p)]},{'name':'Changed'}),
        'patch': ('PATCH',prefix,{'name':'Renamed'},{'name':'Changed'}),
        'ingredient-add': ('POST',prefix+'/ingredients',ingredient(p,'1',2),{'quantity':'2'}),
        'ingredient-patch': ('PATCH',prefix+f"/ingredients/{r['ingredients'][0]['id']}",{'quantity':'1'},{'quantity':'2'}),
        'archive': ('POST',prefix+'/archive',{},None),
        'cook': ('POST',prefix+'/cook',{'servings':'1'},{'servings':'2'}),
    }[operation]
    first = f.request(method,path,key='recipe-replay',json=body)
    assert first.status_code in {200,201}, first.text
    before = state(f)
    assert f.request(method,path,key='recipe-replay',json=body).content == first.content
    if changed:
        response = f.request(method,path,key='recipe-replay',json=body|changed)
        assert response.status_code == 409 and response.json()['error_code'] == 'INVENTORY_IDEMPOTENCY_CONFLICT'
    assert state(f) == before


@pytest.mark.parametrize('key',[False,'','with space','x'*129,'tab\tkey'])
def test_recipe_mutations_require_valid_key(f,key):
    from test_inventory_cooking import recipe, ingredient
    p=product(f)
    r=recipe(f,p)
    prefix=f"/recipes/{r['id']}"
    for method,path,body in [
        ('POST','/recipes',{'name':'New','servings':'1','ingredients':[ingredient(p)]}),
        ('PATCH',prefix,{'name':'Edited'}),('POST',prefix+'/ingredients',ingredient(p,'1',2)),
        ('PATCH',prefix+f"/ingredients/{r['ingredients'][0]['id']}",{'quantity':'1'}),
        ('POST',prefix+'/archive',{}),('POST',prefix+'/cook',{'servings':'1'})]:
        assert f.request(method,path,key=key,json=body).status_code==422


@pytest.mark.parametrize('failures',[2,3])
def test_cook_retry_restarts_entire_command_and_removes_provisional_keys(f,monkeypatch,failures):
    from sqlalchemy.exc import DBAPIError
    from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
    from test_inventory_cooking import recipe,cook,state
    from test_inventory_checkout import configure_timezone
    from test_inventory_lots import receipt
    configure_timezone(f)
    p=product(f)
    receipt(f,p)
    r=recipe(f,p)
    before=state(f)
    original=SqlAlchemyFinanceRepository.complete
    attempts=[]
    class SerializationFailure(Exception):
        sqlstate='40001'
    async def fail(self,*args):
        await original(self,*args)
        attempts.append(1)
        if len(attempts)<=failures:
            raise DBAPIError('injected',None,SerializationFailure())
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyFinanceRepository,'complete',fail)
        response=cook(f,r,key='whole-cook-retry')
    assert len(attempts)==3
    if failures==3:
        assert response.status_code==409 and response.json()['error_code']=='INVENTORY_RETRY_EXHAUSTED'
        assert state(f)==before
        assert cook(f,r,key='whole-cook-retry').status_code==201
    else:
        assert response.status_code==201,response.text
        assert len(query(f,'SELECT id FROM recipe_cooking_history WHERE household_id=:hid'))==1
        assert len(query(f,'SELECT id FROM consumption_records WHERE household_id=:hid'))==1


def test_concurrent_cook_same_key_has_one_history_and_one_deduction(f):
    from test_inventory_cooking import recipe
    from test_inventory_checkout import configure_timezone
    from test_inventory_lots import receipt
    configure_timezone(f)
    p=product(f)
    receipt(f,p)
    r=recipe(f,p)
    async def run():
        barrier=asyncio.Barrier(2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app),base_url='https://testserver') as client:
            async def call():
                await barrier.wait()
                return await client.post(f"/api/v1/households/{f.hid}/recipes/{r['id']}/cook",headers=f.actors['OWNER'].headers|{'Idempotency-Key':'cook-race'},json={'servings':'2'})
            a,b=await asyncio.gather(call(),call())
            assert a.status_code==b.status_code==201 and a.content==b.content
    asyncio.run(run())
    assert len(query(f,'SELECT id FROM recipe_cooking_history WHERE household_id=:hid'))==1
    assert len(query(f,'SELECT id FROM consumption_records WHERE household_id=:hid'))==1
    assert query(f,'SELECT remaining_quantity FROM inventory_lots WHERE household_id=:hid')[0]['remaining_quantity']==3
