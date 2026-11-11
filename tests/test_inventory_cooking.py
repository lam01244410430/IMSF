"""Step 5 PROPOSAL: real PostgreSQL cooking, snapshots and strict rollback."""
import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

import pytest
from sqlalchemy import text
from test_finance_transactions import query
from test_inventory_lots import product, receipt
from test_inventory_checkout import configure_timezone, snapshot


def ingredient(p, quantity='2', line_no=1, **changes):
    return dict(line_no=line_no, product_id=p['id'], quantity=quantity,
                unit_id=p['base_unit_id'], essential=True) | changes


def recipe(f, p=None, **changes):
    p = p or product(f)
    body = dict(name='Rice bowl', servings='2', instructions='Steam gently.',
                ingredients=[ingredient(p)]) | changes
    r = f.request('POST', '/recipes', json=body)
    assert r.status_code == 201, r.text
    return r.json()


def cook(f, r, servings='2', **kwargs):
    return f.request('POST', f"/recipes/{r['id']}/cook", json={'servings': servings}, **kwargs)


def state(f):
    return snapshot(f) | {t: query(f, f'SELECT * FROM {t} WHERE household_id=:hid ORDER BY id')
                          for t in ('recipes', 'recipe_ingredients', 'recipe_cooking_history')}


def stored_snapshot(f, identifier):
    return query(f, 'SELECT recipe_snapshot::text AS bytes FROM recipe_cooking_history WHERE household_id=:hid AND id=:id', id=identifier)[0]['bytes'].encode()


def test_cook_snapshot_links_every_consumption(f, record_testsuite_property):
    configure_timezone(f)
    p = product(f)
    a = receipt(f, p, quantity='1', expires_on='2090-01-01').json()
    b = receipt(f, p, quantity='4', expires_on='2091-01-01').json()
    r = recipe(f, p)
    result = cook(f, r)
    assert result.status_code == 201, result.text
    body = result.json()
    history = f.request('GET', f"/recipe-cooking-history/{body['history_id']}").json()
    snap = history['recipe_snapshot']
    assert snap['schema_version'] == 1
    assert snap['recipe']['id'] == r['id']
    assert snap['recipe']['name'] == r['name']
    assert snap['recipe']['servings'] == r['servings']
    assert snap['recipe']['instructions'] == r['instructions']
    assert snap['timezone'] == 'Asia/Ho_Chi_Minh' and len(snap['local_date']) == 10
    line, = snap['ingredients']
    assert line['id'] == r['ingredients'][0]['id'] and line['line_no'] == 1
    assert line['unit_id'] == line['base_unit_id'] == p['base_unit_id']
    assert Decimal(line['requested_quantity']) == Decimal(line['base_quantity']) == 2
    assert Decimal(line['conversion_factor']) == 1
    rows = query(f, '''SELECT c.id,c.reason_code,c.cooking_history_id,m.id AS movement_id,
        m.lot_id,m.quantity_delta FROM consumption_records c JOIN inventory_movements m
        ON (m.household_id,m.id)=(c.household_id,c.movement_id)
        JOIN recipe_cooking_history h ON (h.household_id,h.id)=(c.household_id,c.cooking_history_id)
        WHERE h.household_id=:hid AND h.id=:id ORDER BY m.id''', id=body['history_id'])
    assert [x['lot_id'] for x in rows] == [a['id'], b['id']]
    assert [x['id'] for x in rows] == body['consumption_record_ids']
    assert all(x['reason_code'] == 'COOKING' for x in rows)
    assert [x['movement_id'] for x in rows] == [x['movement_id'] for x in snap['allocations']]
    before = stored_snapshot(f, body['history_id'])
    assert f.request('PATCH', f"/recipes/{r['id']}", json={'name':'Changed', 'servings':'4', 'instructions':None}).status_code == 200
    assert f.request('PATCH', f"/recipes/{r['id']}/ingredients/{line['id']}", json={'quantity':'9'}).status_code == 200
    assert stored_snapshot(f, body['history_id']) == before
    after = query(f, '''SELECT c.id,c.reason_code,c.cooking_history_id,m.id AS movement_id,
        m.lot_id,m.quantity_delta FROM consumption_records c JOIN inventory_movements m
        ON (m.household_id,m.id)=(c.household_id,c.movement_id)
        JOIN recipe_cooking_history h ON (h.household_id,h.id)=(c.household_id,c.cooking_history_id)
        WHERE h.household_id=:hid AND h.id=:id ORDER BY m.id''', id=body['history_id'])
    assert after == rows
    record_testsuite_property('cooking_snapshot_evidence', json.dumps({
        'household_id':f.hid, 'history_id':body['history_id'],
        'snapshot_bytes_before':len(before), 'snapshot_bytes_after':len(stored_snapshot(f,body['history_id'])),
        'sha256_before':hashlib.sha256(before).hexdigest(),
        'sha256_after':hashlib.sha256(stored_snapshot(f,body['history_id'])).hexdigest(),
        'joined_allocations_before':rows, 'joined_allocations_after':after},default=str))
    assert f.request('GET', '/recipe-cooking-history').json()['items'][0] == history


def test_duplicate_ingredients_aggregate_before_fefo(f):
    configure_timezone(f)
    p = product(f)
    late = receipt(f,p,quantity='3',expires_on='2099-01-01').json()
    early = receipt(f,p,quantity='2',expires_on='2090-01-01').json()
    r = recipe(f,p,ingredients=[ingredient(p,'1'),ingredient(p,'2',2)])
    result = cook(f,r)
    assert result.status_code == 201, result.text
    assert [a['lot_id'] for a in result.json()['allocations']] == [early['id'],late['id']]
    assert [Decimal(a['base_quantity']) for a in result.json()['allocations']] == [2,1]
    assert len(result.json()['consumption_record_ids']) == 2


def test_shortage_and_midway_failure_roll_back_history_and_all_stock(f, monkeypatch, record_testsuite_property):
    from app.inventory.service import InventoryService
    configure_timezone(f)
    p,q = product(f),product(f)
    receipt(f,p,quantity='5')
    r = recipe(f,p,ingredients=[ingredient(p),ingredient(q,'2',2,essential=False)])
    before = state(f)
    response = cook(f,r,key='atomic')
    assert response.status_code == 409 and response.json()['error_code'] == 'INVENTORY_STOCK_SHORTAGE'
    assert state(f) == before
    shortage_counts={t:{'before':len(before[t]),'after':len(state(f)[t])} for t in before}
    receipt(f,q,quantity='5')
    before = state(f)
    original = InventoryService._write_movement_in_uow
    seen = []
    async def fail(self,*args,**kwargs):
        result = await original(self,*args,**kwargs)
        seen.append(result[0]['id'])
        if len(seen) == 2:
            assert await self.session.scalar(text('SELECT count(*) FROM recipe_cooking_history WHERE household_id=:hid'), {'hid':f.hid}) == 1
            assert await self.session.scalar(text("SELECT count(*) FROM consumption_records WHERE household_id=:hid"), {'hid':f.hid}) == 2
            raise RuntimeError('Injected late ingredient write failure')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(InventoryService,'_write_movement_in_uow',fail)
        with pytest.raises(RuntimeError,match='late ingredient'):
            cook(f,r,key='atomic')
    assert len(seen) == 2 and state(f) == before
    record_testsuite_property('cooking_rollback_evidence',json.dumps({
        'household_id':f.hid, 'shortage':shortage_counts,
        'late_failure':{t:{'before':len(before[t]),'after':len(state(f)[t])} for t in before},
        'flushed_movements_in_failed_attempt':seen, 'all_rows_unchanged':state(f)==before}))
    assert cook(f,r,key='atomic').status_code == 201


@pytest.mark.parametrize('servings,quantity,expected', [('1','2','1'),('3','1',None)])
def test_scaling_requires_exact_base_demand(f,servings,quantity,expected):
    configure_timezone(f)
    p=product(f)
    receipt(f,p,quantity='10')
    r=recipe(f,p,servings='3' if expected is None else '2',ingredients=[ingredient(p,quantity)])
    # One third of a base unit is inexact; successful half demand is exact.
    requested = '1' if expected is None else servings
    before=state(f)
    response=cook(f,r,requested)
    if expected is None:
        assert response.status_code == 422 and response.json()['error_code']=='INVENTORY_UNIT_CONVERSION_INVALID'
        assert state(f)==before
    else:
        assert response.status_code == 201, response.text
        assert Decimal(response.json()['allocations'][0]['base_quantity'])==Decimal(expected)


def test_scaling_converts_before_base_exactness_check(f):
    configure_timezone(f)
    p=product(f)
    units=f.request('GET','/measurement-units').json()['items']
    kg=next(u['id'] for u in units if u['code']=='kg')
    receipt(f,p,quantity='1')
    r=recipe(f,p,servings='10',ingredients=[ingredient(p,'0.000001',unit_id=kg)])
    response=cook(f,r,'1')
    assert response.status_code==201, response.text
    assert Decimal(response.json()['allocations'][0]['base_quantity'])==Decimal('0.0001')


@pytest.mark.parametrize('timezone',[None,'Invalid/Zone'])
def test_missing_timezone_leaves_settings_unchanged(f,timezone):
    configure_timezone(f,timezone)
    p=product(f)
    receipt(f,p)
    r=recipe(f,p)
    before=state(f)
    settings=query(f,'SELECT values FROM household_settings WHERE household_id=:hid')
    response=cook(f,r)
    assert response.status_code==422 and response.json()['error_code']=='INVENTORY_TIMEZONE_REQUIRED'
    assert state(f)==before and query(f,'SELECT values FROM household_settings WHERE household_id=:hid')==settings


def test_archive_blocks_new_cooking_but_retains_reads(f):
    configure_timezone(f)
    p=product(f)
    receipt(f,p)
    r=recipe(f,p)
    h=cook(f,r).json()
    assert f.request('POST',f"/recipes/{r['id']}/archive",json={}).status_code==200
    before=state(f)
    assert cook(f,r).status_code==409 and state(f)==before
    assert f.request('GET',f"/recipes/{r['id']}").status_code==200
    assert f.request('GET',f"/recipe-cooking-history/{h['history_id']}").status_code==200


def test_cook_idempotent_replay_and_changed_payload(f):
    configure_timezone(f)
    p=product(f)
    receipt(f,p)
    r=recipe(f,p)
    first=cook(f,r,key='cook-once')
    assert first.status_code==201,first.text
    before=state(f)
    assert cook(f,r,key='cook-once').content==first.content
    conflict=cook(f,r,'4',key='cook-once')
    assert conflict.status_code==409 and conflict.json()['error_code']=='INVENTORY_IDEMPOTENCY_CONFLICT'
    assert state(f)==before


def test_ingredient_add_patch_only_and_recipe_contract(f):
    p=product(f)
    r=recipe(f,p)
    prefix=f"/recipes/{r['id']}"
    added=f.request('POST',prefix+'/ingredients',json=ingredient(p,'3',2))
    assert added.status_code==201,added.text
    iid=added.json()['id']
    response=f.request('PATCH',prefix+f'/ingredients/{iid}',json={'quantity':'4','essential':False})
    assert response.status_code==200 and response.json()['essential'] is False
    for path in (prefix,prefix+f'/ingredients/{iid}','/recipe-cooking-history/1'):
        assert f.request('DELETE',path).status_code in {404,405}
    for body in ({'ingredients':[]},{'name':None},{'servings':None},{'instructions':'x'*10001}):
        assert f.request('PATCH',prefix,json=body).status_code==422
    assert f.request('PATCH',prefix+f'/ingredients/{iid}',json={'line_no':3}).status_code==422
    for body in ({'ingredients':[ingredient(p,str(i+1),i+1) for i in range(101)]}, {'instructions':'x'*10001}):
        assert f.request('POST','/recipes',json={'name':'Cap','servings':'1','ingredients':[ingredient(p)]}|body).status_code==422
    assert len(f.request('GET',prefix).json()['ingredients'])==2


def test_cross_household_recipe_and_ingredient_references_return_404(f):
    p=product(f)
    r=recipe(f,p)
    async def foreign():
        async with f.db() as db,db.begin():
            return await db.scalar(text("INSERT INTO recipes(household_id,name,servings,created_by_member_id) VALUES (:hid,'Foreign',1,:mid) RETURNING id"),{'hid':f.other_hid,'mid':f.actors['OUTSIDER'].member_id})
    identifier=asyncio.run(foreign())
    for method,path,body in [('GET',f'/recipes/{identifier}',None),('POST',f'/recipes/{identifier}/cook',{'servings':'1'}),('PATCH',f'/recipes/{identifier}',{'name':'X'})]:
        assert f.request(method,path,**({'json':body} if body else {})).status_code==404
    before=state(f)
    bad=ingredient(p,product_id=9223372036854775807)
    assert f.request('POST','/recipes',json={'name':'X','servings':'1','ingredients':[bad]}).status_code==404
    assert state(f)==before
    other=recipe(f,p)
    assert f.request('PATCH',f"/recipes/{r['id']}/ingredients/{other['ingredients'][0]['id']}",json={'quantity':'1'}).status_code==404


@pytest.mark.parametrize('role',['OWNER','ADMIN','FINANCE_MANAGER','INVENTORY_MANAGER','MEMBER','VIEWER'])
def test_cook_permission_does_not_follow_recipe_edit_permission(f,role):
    configure_timezone(f)
    p=product(f)
    receipt(f,p,quantity='20')
    r=recipe(f,p)
    edit=f.request('PATCH',f"/recipes/{r['id']}",role=role,json={'name':'Role edited'})
    assert edit.status_code==(200 if role in {'OWNER','FINANCE_MANAGER','MEMBER'} else 403)
    cooked=cook(f,r,role=role)
    assert cooked.status_code==(201 if role in {'OWNER','INVENTORY_MANAGER'} else 403),cooked.text


def test_recipe_edit_race_preserves_executed_snapshot(f,monkeypatch):
    from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
    configure_timezone(f)
    p=product(f)
    receipt(f,p,quantity='10')
    r=recipe(f,p)
    entered,release,editing=Event(),Event(),Event()
    original=SqlAlchemyInventoryRepository.lock_products
    async def blocked(self,*args,**kwargs):
        entered.set()
        assert await asyncio.to_thread(release.wait,10)
        return await original(self,*args,**kwargs)
    with monkeypatch.context() as patch,ThreadPoolExecutor(2) as pool:
        patch.setattr(SqlAlchemyInventoryRepository,'lock_products',blocked)
        cooking=pool.submit(cook,f,r)
        assert entered.wait(10)
        def edit():
            editing.set()
            return f.request('PATCH',f"/recipes/{r['id']}",role='MEMBER',json={'name':'Later','instructions':'Later steps'})
        edit_future=pool.submit(edit)
        assert editing.wait(10)
        release.set()
        cooked=cooking.result(timeout=20)
        assert cooked.status_code==201,cooked.text
        assert edit_future.result(timeout=20).status_code==200
    history=f.request('GET',f"/recipe-cooking-history/{cooked.json()['history_id']}").json()
    assert history['recipe_snapshot']['recipe']['name']=='Rice bowl'
    assert history['recipe_snapshot']['recipe']['instructions']=='Steam gently.'
    assert f.request('GET',f"/recipes/{r['id']}").json()['name']=='Later'


def test_cook_waits_on_recipe_before_products_and_rereads_all_lines(f):
    """Independent SQL editor bypasses household serialization to test real locks."""
    import httpx
    configure_timezone(f)
    p=product(f)
    receipt(f,p,quantity='10')
    r=recipe(f,p)
    async def run():
        async with f.db() as editor:
            await editor.begin()
            pid=await editor.scalar(text('SELECT pg_backend_pid()'))
            await editor.execute(text('SELECT id FROM recipes WHERE household_id=:hid AND id=:rid FOR UPDATE'),{'hid':f.hid,'rid':r['id']})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app),base_url='https://testserver') as client:
                task=asyncio.create_task(client.post(f"/api/v1/households/{f.hid}/recipes/{r['id']}/cook",
                    headers=f.actors['OWNER'].headers|{'Idempotency-Key':'recipe-row-lock'},json={'servings':'2'}))
                try:
                    async with asyncio.timeout(10):
                        while True:
                            async with f.db() as observer:
                                blocked=await observer.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND query LIKE '%recipes%' AND query LIKE '%FOR UPDATE%')"),{'pid':pid})
                            if blocked:
                                break
                            await asyncio.sleep(0)
                    async with f.db() as observer,observer.begin():
                        await observer.execute(text('SELECT id FROM products WHERE household_id=:hid AND id=:pid FOR UPDATE NOWAIT'),{'hid':f.hid,'pid':p['id']})
                    await editor.execute(text("UPDATE recipes SET name='Concurrent edit',servings=4,instructions='New steps' WHERE household_id=:hid AND id=:rid"),{'hid':f.hid,'rid':r['id']})
                    await editor.execute(text('UPDATE recipe_ingredients SET quantity=6 WHERE household_id=:hid AND recipe_id=:rid'),{'hid':f.hid,'rid':r['id']})
                    await editor.commit()
                    response=await asyncio.wait_for(task,10)
                    assert response.status_code==201,response.text
                    return response.json()['history_id']
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task,return_exceptions=True)
    hid=asyncio.run(run())
    snap=f.request('GET',f'/recipe-cooking-history/{hid}').json()['recipe_snapshot']
    assert snap['recipe']['name']=='Concurrent edit' and Decimal(snap['recipe']['servings'])==4
    assert snap['recipe']['instructions']=='New steps'
    assert Decimal(snap['ingredients'][0]['quantity'])==6
    assert Decimal(snap['ingredients'][0]['base_quantity'])==3


def test_cook_product_scope_error_precedes_missing_timezone(f):
    p=product(f)
    r=recipe(f,p)
    async def foreign_product():
        async with f.db() as db,db.begin():
            return await db.scalar(text("INSERT INTO products(household_id,name,base_unit_id) VALUES (:hid,'Foreign',:unit) RETURNING id"),{'hid':f.other_hid,'unit':p['base_unit_id']})
    foreign=asyncio.run(foreign_product())
    for method,path,body in [
        ('POST','/recipes',{'name':'Bad','servings':'1','ingredients':[ingredient(p,product_id=foreign)]}),
        ('POST',f"/recipes/{r['id']}/ingredients",ingredient(p,'1',2,product_id=foreign)),
        ('PATCH',f"/recipes/{r['id']}/ingredients/{r['ingredients'][0]['id']}",{'product_id':foreign})]:
        assert f.request(method,path,json=body).status_code==404
    # A retained ingredient prevents reassigning its scoped product; normal
    # runtime permissions also forbid altering the household column.
    async def remove_product():
        async with f.db() as db,db.begin():
            await db.execute(text('UPDATE products SET household_id=:other WHERE household_id=:hid AND id=:pid'),{'other':f.other_hid,'hid':f.hid,'pid':p['id']})
    # Runtime column grants reject household reassignment before the composite
    # FK could be violated; do not relax privileges to manufacture bad input.
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError) as denied:
        asyncio.run(remove_product())
    assert denied.value.orig.sqlstate == "42501"
    assert f.request('POST','/recipes/9223372036854775807/cook',json={'servings':'1'}).status_code==404


def test_recipe_pages_are_bounded_and_cursors_scoped(f):
    p=product(f)
    recipes=[recipe(f,p,name=f'Recipe {i}') for i in range(3)]
    first=f.request('GET','/recipes',params={'limit':2}).json()
    assert [r['id'] for r in first['items']]==[r['id'] for r in recipes[:2]]
    second=f.request('GET','/recipes',params={'limit':2,'cursor':first['next_cursor']}).json()
    assert [r['id'] for r in second['items']]==[recipes[2]['id']] and second['next_cursor'] is None
    assert f.request('GET','/recipe-cooking-history',params={'cursor':first['next_cursor']}).status_code==422
    assert f.request('GET','/recipes',params={'limit':201}).status_code==422
    assert f.request('GET','/recipes',params={'cursor':first['next_cursor'],'archived':True}).status_code==422


def test_recipe_ingredient_cap_applies_to_add(f):
    p=product(f)
    r=recipe(f,p,ingredients=[ingredient(p,'1',i+1) for i in range(100)])
    before=state(f)
    response=f.request('POST',f"/recipes/{r['id']}/ingredients",json=ingredient(p,'1',101))
    assert response.status_code==422 and state(f)==before
