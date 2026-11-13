"""Step 4 PROPOSAL contracts: atomic real-DB checkout, no mixed partial effects."""
import asyncio
from decimal import Decimal
import pytest
from sqlalchemy import text
from test_inventory_lots import product, receipt
from test_finance_transactions import query, create_draft, post, account, payment

TABLES = ('transactions', 'transaction_items', 'transaction_payments', 'account_ledger_entries',
          'inventory_lots', 'inventory_movements', 'consumption_records', 'audit_logs', 'idempotency_requests')


def snapshot(f):
    return {t: query(f, f'SELECT * FROM {t} WHERE household_id=:hid ORDER BY id') for t in TABLES}


def configure_timezone(f, name='Asia/Ho_Chi_Minh'):
    import json
    async def run():
        async with f.db() as db, db.begin():
            await db.execute(text('INSERT INTO household_settings(household_id,values) VALUES (:hid,CAST(:v AS jsonb)) ON CONFLICT (household_id) DO UPDATE SET values=EXCLUDED.values'),
                             {'hid': f.hid, 'v': json.dumps({} if name is None else {'timezone': name})})
    asyncio.run(run())


def demand(p, quantity='4', **changes):
    return {'items': [{'product_id': p['id'], 'quantity': quantity, 'unit_id': p['base_unit_id']}],
            'reason_code': 'CHECKOUT'} | changes


def purchase_body(f, p, *, payments=None, quantities=('2', '3')):
    tx = create_draft(f, items=[{'line_no': 1, 'description': 'Rice', 'quantity': '1', 'net_amount': '12.30',
                               'product_id': p['id'], 'base_quantity': '5'}])
    return tx, {'transaction_id': tx['id'], 'payments': [] if payments is None else payments,
                'lots': [{'item_id': tx['items'][0]['id'], 'quantity': q, 'unit_id': p['base_unit_id'],
                          'received_at': '2026-11-11T10:00:00Z', 'expires_on': '2027-01-01'} for q in quantities]}


def test_stock_only_checkout_never_creates_finance_rows(f):
    configure_timezone(f)
    p = product(f)
    lot = receipt(f, p).json()
    before = snapshot(f)
    r = f.request('POST', '/checkout/deductions', json=demand(p))
    assert r.status_code == 201, r.text
    allocation, = r.json()['allocations']
    assert allocation['product_id'] == p['id'] and allocation['lot_id'] == lot['id']
    assert isinstance(allocation['base_quantity'], str) and isinstance(allocation['remaining_quantity'], str)
    assert Decimal(allocation['base_quantity']) == 4 and Decimal(allocation['remaining_quantity']) == 1
    assert len(r.json()['movement_ids']) == len(r.json()['consumption_record_ids']) == 1
    assert r.json()['disposal_record_ids'] == r.json()['adjustment_ids'] == r.json()['refund_inventory_link_ids'] == []
    after = snapshot(f)
    for table in TABLES[:4]:
        assert after[table] == before[table]


def test_finance_only_post_never_creates_stock(f):
    p = product(f)
    tx, body = purchase_body(f, p)
    r = post(f, tx, [])
    assert r.status_code == 200
    for t in ('inventory_lots', 'inventory_movements', 'consumption_records'):
        assert snapshot(f)[t] == []


def test_deduction_aggregates_repeated_product_lines_before_allocation(f):
    configure_timezone(f)
    p = product(f)
    lot = receipt(f, p).json()
    body = demand(p, '0.002')
    kg = next(u['id'] for u in f.request('GET', '/measurement-units').json()['items'] if u['code'] == 'kg')
    body['items'][0]['unit_id'] = kg
    body['items'].append({'product_id': p['id'], 'quantity': '2', 'unit_id': p['base_unit_id']})
    r = f.request('POST', '/checkout/deductions', json=body)
    assert r.status_code == 201, r.text
    assert [(a['lot_id'], Decimal(a['base_quantity'])) for a in r.json()['allocations']] == [(lot['id'], Decimal(4))]
    assert len(r.json()['movement_ids']) == 1


def test_any_product_shortage_rolls_back_all_allocations(f):
    configure_timezone(f)
    p, other = product(f), product(f)
    receipt(f, p)
    body = demand(p)
    body['items'] += demand(other)['items']
    before = snapshot(f)
    r = f.request('POST', '/checkout/deductions', key='short', json=body)
    assert r.status_code == 409 and r.json()['error_code'] == 'INVENTORY_STOCK_SHORTAGE'
    assert snapshot(f) == before


def test_deduction_failure_after_first_lot_rolls_back_every_effect(f, monkeypatch):
    from app.inventory.service import InventoryService
    configure_timezone(f)
    p = product(f)
    receipt(f, p, quantity='2')
    receipt(f, p, quantity='3')
    before = snapshot(f)
    original = InventoryService._write_movement_in_uow
    async def fail(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        raise RuntimeError('Injected after projection movement detail flush')
    with monkeypatch.context() as patch:
        patch.setattr(InventoryService, '_write_movement_in_uow', fail)
        with pytest.raises(RuntimeError, match='Injected'):
            f.request('POST', '/checkout/deductions', key='rollback', json=demand(p))
    assert snapshot(f) == before
    assert f.request('POST', '/checkout/deductions', key='rollback', json=demand(p)).status_code == 201


def test_purchase_checkout_failure_after_payment_and_receipt_rolls_back_all_modules(f, monkeypatch):
    from app.inventory.service import InventoryService
    p = product(f)
    tx, body = purchase_body(f, p, payments=[payment(account(f))])
    before = snapshot(f)
    original = InventoryService.receive_in_uow
    async def fail(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        # Prove real finance effects and first receipt exist inside the same UoW.
        for table in ('transaction_payments', 'account_ledger_entries', 'inventory_lots', 'inventory_movements'):
            assert await self.session.scalar(text(f'SELECT count(*) FROM {table} WHERE household_id=:hid'), {'hid': f.hid}) == 1
        assert await self.session.scalar(text('SELECT status FROM transactions WHERE id=:tid'), {'tid': tx['id']}) == 'POSTED'
        raise RuntimeError('Injected after real payment and first receipt')
    with monkeypatch.context() as patch:
        patch.setattr(InventoryService, 'receive_in_uow', fail)
        with pytest.raises(RuntimeError, match='Injected'):
            f.request('POST', '/checkout/purchases', key='rollback', json=body)
    assert snapshot(f) == before
    assert f.request('POST', '/checkout/purchases', key='rollback', json=body).status_code == 201


@pytest.mark.parametrize('paid', ['0', '4.00', '12.30'])
def test_purchase_checkout_preserves_unpaid_and_partial_settlement(f, paid):
    from test_inventory_checkout import configure_timezone
    configure_timezone(f)  # Step 4 lot GET requires explicit household timezone.
    p = product(f)
    existing = receipt(f, p).json()
    payments = [] if paid == '0' else [payment(account(f), paid)]
    tx, body = purchase_body(f, p, payments=payments)
    body['lots'][0] |= {'cost_currency': 'USD', 'unit_cost': '0.123456789012'}
    r = f.request('POST', '/checkout/purchases', json=body)
    assert r.status_code == 201, r.text
    result = r.json()
    assert set(result) == {'transaction', 'lot_ids', 'receipt_movement_ids'}
    assert result['transaction']['status'] == 'POSTED'
    assert Decimal(result['transaction']['settled_amount']) == Decimal(paid)
    assert Decimal(result['transaction']['remaining_amount']) == Decimal('12.30') - Decimal(paid)
    assert len(result['lot_ids']) == len(result['receipt_movement_ids']) == 2
    assert f.request('GET', f"/transactions/{tx['id']}").json() == result['transaction']
    assert Decimal(f.request('GET', f"/inventory-lots/{existing['id']}").json()['remaining_quantity']) == 5
    movements = query(f, 'SELECT * FROM inventory_movements WHERE household_id=:hid AND transaction_id=:tid ORDER BY id', tid=tx['id'])
    assert [m['lot_id'] for m in movements] == result['lot_ids']
    assert [m['id'] for m in movements] == result['receipt_movement_ids']
    assert [m['quantity_delta'] for m in movements] == [Decimal(2), Decimal(3)]


@pytest.mark.parametrize('quantities', [('4',), ('6',), ()])
def test_purchase_requires_full_receipt_equality(f, quantities):
    tx, body = purchase_body(f, product(f), quantities=quantities)
    before = snapshot(f)
    r = f.request('POST', '/checkout/purchases', json=body)
    assert r.status_code == 409, r.text
    assert snapshot(f) == before


@pytest.mark.parametrize('target', ['product', 'lot'])
def test_archived_stock_is_not_selected(f, target):
    configure_timezone(f)
    p = product(f)
    lot = receipt(f, p).json()
    path = f"/products/{p['id']}/archive" if target == 'product' else f"/inventory-lots/{lot['id']}/archive"
    assert f.request('POST', path, json={} if target == 'product' else {'reason': 'Retain'}).status_code == 200
    before = snapshot(f)
    assert f.request('POST', '/checkout/deductions', json=demand(p)).status_code == 409
    assert snapshot(f) == before


@pytest.mark.parametrize('field,value', [('reason_code','DAILY_USE'), ('extra',1), ('items',[])])
def test_stock_checkout_rejects_invalid_contract(f, field, value):
    p = product(f)
    assert f.request('POST', '/checkout/deductions', json=demand(p) | {field:value}).status_code == 422


@pytest.mark.parametrize('changes', [{'unit_cost':'1'}, {'cost_currency':'EUR','unit_cost':'1'}, {'cost_currency':'USD','unit_cost':'-1'}, {'received_at':'2026-11-11T10:00:00'}, {'product_id':1}])
def test_purchase_receipt_inputs_rejected_atomically(f, changes):
    tx, body = purchase_body(f, product(f))
    body['lots'][0] |= changes
    before = snapshot(f)
    assert f.request('POST', '/checkout/purchases', json=body).status_code == 422
    assert snapshot(f) == before


def test_purchase_non_product_lines_stay_finance_only(f):
    tx = create_draft(f)
    r = f.request('POST','/checkout/purchases',json={'transaction_id':tx['id'],'payments':[],'lots':[]})
    assert r.status_code == 201, r.text
    assert r.json()['lot_ids'] == r.json()['receipt_movement_ids'] == []
    assert r.json()['transaction']['status'] == 'POSTED'


def test_purchase_archived_product_keeps_finance_conflict_policy(f):
    p = product(f)
    tx,body = purchase_body(f,p)
    assert f.request('POST',f"/products/{p['id']}/archive",json={}).status_code == 200
    before = snapshot(f)
    r = f.request('POST','/checkout/purchases',json=body)
    assert r.status_code == 409 and r.json()['error_code'] == 'FINANCE_CONFLICT'
    assert snapshot(f) == before


def test_purchase_rejects_other_transaction_item(f):
    p = product(f)
    tx,body = purchase_body(f,p)
    other,unused = purchase_body(f,p)
    body['lots'][0]['item_id'] = other['items'][0]['id']
    before = snapshot(f)
    assert f.request('POST','/checkout/purchases',json=body).status_code == 404
    assert snapshot(f) == before


def test_deduction_rejects_more_than_100_lines_and_inexact_conversion(f):
    configure_timezone(f)
    p = product(f)
    receipt(f,p)
    before = snapshot(f)
    body = demand(p)
    body['items'] *= 101
    assert f.request('POST','/checkout/deductions',json=body).status_code == 422
    units = f.request('GET','/measurement-units').json()['items']
    body = demand(p)
    body['items'][0]['unit_id'] = next(u['id'] for u in units if u['code']=='ml')
    r = f.request('POST','/checkout/deductions',json=body)
    assert r.status_code == 422 and r.json()['error_code'] == 'INVENTORY_UNIT_CONVERSION_INVALID'
    assert snapshot(f) == before


@pytest.mark.parametrize('reference', ['foreign', 'missing'])
def test_scoped_product_miss_precedes_missing_timezone(f, reference):
    # Catch timezone validation hiding the required household-scoped 404.
    p = product(f)
    if reference == 'foreign':
        async def seed():
            async with f.db() as db, db.begin():
                return await db.scalar(text("INSERT INTO products(household_id,name,base_unit_id) VALUES (:hid,'Foreign',:unit) RETURNING id"), {'hid':f.other_hid,'unit':p['base_unit_id']})
        identifier = asyncio.run(seed())
    else:
        identifier = 9223372036854775807
    before = snapshot(f)
    body = demand(p)
    body['items'][0]['product_id'] = identifier
    r = f.request('POST','/checkout/deductions',key='scope-before-timezone',json=body)
    assert r.status_code == 404 and r.json()['error_code'] == 'INVENTORY_NOT_FOUND'
    assert snapshot(f) == before
    assert query(f,'SELECT values FROM household_settings WHERE household_id=:hid')[0]['values'] == {}


def test_purchased_lot_deduction_links_original_without_financial_writes(f):
    from test_inventory_lots import purchase
    configure_timezone(f)
    p = product(f)
    tx = purchase(f,p)
    lot = receipt(f,p,source_kind='PURCHASE',purchase_item_id=tx['items'][0]['id']).json()
    before = snapshot(f)
    r = f.request('POST','/checkout/deductions',json=demand(p))
    assert r.status_code == 201, r.text
    assert [a['lot_id'] for a in r.json()['allocations']] == [lot['id']]
    movements = query(f,"SELECT transaction_id,quantity_delta FROM inventory_movements WHERE household_id=:hid AND kind='CONSUME'")
    assert [(m['transaction_id'],m['quantity_delta']) for m in movements] == [(tx['id'],Decimal(-4))]
    for table in TABLES[:4]:
        assert snapshot(f)[table] == before[table]


def test_purchase_full_receipt_is_per_item_with_shuffled_products(f):
    p,other = product(f),product(f)
    tx = create_draft(f, items=[
        {'line_no':1,'description':'First','quantity':'1','net_amount':'4.00','product_id':p['id'],'base_quantity':'2'},
        {'line_no':2,'description':'Second','quantity':'1','net_amount':'4.00','product_id':p['id'],'base_quantity':'3'},
        {'line_no':3,'description':'Third','quantity':'1','net_amount':'4.30','product_id':other['id'],'base_quantity':'7'}])
    lots = [{'item_id':tx['items'][i]['id'],'quantity':q,'unit_id':p['base_unit_id'],'received_at':'2026-11-11T10:00:00Z'} for i,q in [(2,'7'),(1,'2'),(0,'3')]]
    body = {'transaction_id':tx['id'],'payments':[],'lots':lots}
    before = snapshot(f)
    # Product total is correct (5), but the two items cannot cancel differences.
    assert f.request('POST','/checkout/purchases',key='multi-item',json=body).status_code == 409
    assert snapshot(f) == before
    lots[1]['quantity'],lots[2]['quantity'] = '3','2'
    r = f.request('POST','/checkout/purchases',key='multi-item',json=body)
    assert r.status_code == 201, r.text
    received = query(f,'SELECT product_id,purchase_item_id,received_quantity FROM inventory_lots WHERE household_id=:hid ORDER BY id')
    assert [(l['product_id'],l['purchase_item_id'],l['received_quantity']) for l in received] == [
        (other['id'],tx['items'][2]['id'],Decimal(7)),(p['id'],tx['items'][1]['id'],Decimal(3)),(p['id'],tx['items'][0]['id'],Decimal(2))]


def test_fefo_partial_lot_split_fulfills_whole_demand_or_rolls_back(f, monkeypatch):
    from datetime import datetime, timezone
    from test_inventory_fefo import freeze_inventory_clock
    configure_timezone(f)
    freeze_inventory_clock(monkeypatch, datetime(2026, 11, 11, tzinfo=timezone.utc))
    p = product(f)
    a = receipt(f, p, quantity='2', expires_on='2026-11-11').json()
    b = receipt(f, p, quantity='3', expires_on='2026-11-12').json()
    before = snapshot(f)
    r = f.request('POST', '/checkout/deductions', key='partial-six', json=demand(p, '6'))
    assert r.status_code == 409 and r.json()['error_code'] == 'INVENTORY_STOCK_SHORTAGE'
    assert snapshot(f) == before
    r = f.request('POST', '/checkout/deductions', key='partial-four', json=demand(p, '4'))
    assert r.status_code == 201, r.text
    assert [(x['lot_id'], Decimal(x['base_quantity']), Decimal(x['remaining_quantity'])) for x in r.json()['allocations']] == [(a['id'], Decimal(2), Decimal(0)), (b['id'], Decimal(2), Decimal(1))]
    rows = query(f, "SELECT lot_id,quantity_delta FROM inventory_movements WHERE household_id=:hid AND kind='CONSUME' ORDER BY id")
    assert [(x['lot_id'], x['quantity_delta']) for x in rows] == [(a['id'], -2), (b['id'], -2)]
    assert len(r.json()['movement_ids']) == len(r.json()['consumption_record_ids']) == 2
    after = snapshot(f)
    assert f.request('POST', '/checkout/deductions', key='partial-four', json=demand(p, '4')).content == r.content
    assert snapshot(f) == after
