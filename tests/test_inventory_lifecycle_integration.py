"""Step 4 PROPOSALS: integrated reads never become another stock writer."""
import asyncio
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from test_inventory_lots import product, receipt
from test_inventory_checkout import configure_timezone, demand
from test_inventory_lifecycle import deduction
from test_inventory_expiry import freeze_clock, persist_alert
from test_inventory_expiry_jobs import enqueue, jobs
from test_inventory_expiry_jobs_races import business_snapshot
from test_finance_transactions import query
from test_inventory_fefo import freeze_inventory_clock


def read_snapshot(f):
    return business_snapshot(f) | {
        name: query(f, f'SELECT to_jsonb(t)::text AS bytes FROM {name} t WHERE household_id=:hid ORDER BY id')
        for name in ('scheduled_jobs', 'expiration_alerts', 'idempotency_requests')
    }


@pytest.mark.parametrize('zone', [None, '', 'No/Such_Zone', 42, '../UTC'])
def test_lot_reads_require_timezone_but_write_responses_stay_unchanged(f, zone):
    configure_timezone(f, zone)
    p = product(f)
    r = receipt(f, p)
    assert r.status_code == 201, r.text
    lot = r.json()
    fields = {'freshness', 'days_left', 'local_date', 'timezone'}
    assert not fields.intersection(lot)
    path = f"/inventory-lots/{lot['id']}"
    for method, suffix, body in [('PATCH', '', {'expires_on': '2026-11-12', 'reason': 'Label'}),
                                 ('POST', '/archive', {'reason': 'Retain'})]:
        r = f.request(method, path + suffix, json=body)
        assert r.status_code == 200, r.text
        assert set(r.json()) == set(lot)
    before = read_snapshot(f)
    for route in ['/inventory-lots', path]:
        r = f.request('GET', route)
        assert r.status_code == 422 and r.json()['error_code'] == 'INVENTORY_TIMEZONE_REQUIRED'
    assert f.request('GET', '/inventory-lots/9223372036854775807').status_code == 404
    assert f.request('GET', '/inventory-lots', params={'product_id': 9223372036854775807}).status_code == 404
    assert f.request('GET', path, role='OUTSIDER').status_code == 404
    assert read_snapshot(f) == before


@pytest.mark.parametrize('instant,day', [
    ('2026-11-10T16:59:59+00:00', '2026-11-10'),
    ('2026-11-10T17:00:00+00:00', '2026-11-11'),
])
def test_integrated_lot_reads_share_domain_freshness_one_date_and_retained_terminal(f, monkeypatch, instant, day):
    from app.inventory.domain import terminal_state
    from app.lifecycle.domain import freshness
    from datetime import date
    configure_timezone(f)
    p = product(f)
    lots = [receipt(f, p, expires_on=d).json() for d in
            ['2026-11-15', '2026-11-14', '2026-11-11', '2026-11-10', None]]
    assert deduction(f, p, lots[0], quantity='5').status_code == 201
    before = read_snapshot(f)
    calls = freeze_clock(monkeypatch, instant)
    response = f.request('GET', '/inventory-lots')
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    for item, lot in zip(response.json()['items'], lots, strict=True):
        expected = freshness(date.fromisoformat(lot['expires_on']) if lot['expires_on'] else None, date.fromisoformat(day))
        assert (item['freshness'], item['days_left']) == expected
        assert item['local_date'] == day and item['timezone'] == 'Asia/Ho_Chi_Minh'
        detail = f.request('GET', f"/inventory-lots/{lot['id']}")
        assert detail.status_code == 200 and detail.json() == item
        assert item['terminal_state'] == terminal_state(Decimal(item['remaining_quantity']), ['CONSUME'] if item['id'] == lots[0]['id'] else [])
    lifecycle = f.request('GET', '/inventory/lifecycle').json()['items']
    assert [x['terminal_state'] for x in lifecycle] == [x['terminal_state'] for x in response.json()['items']]
    assert read_snapshot(f) == before
    freeze_clock(monkeypatch, '2026-11-11T17:00:00+00:00')
    for route in ['/inventory-lots', '/inventory/lifecycle', f"/inventory-lots/{lots[0]['id']}"]:
        assert f.request('GET', route).status_code == 200
    assert read_snapshot(f) == before  # Crossing midnight never rewrites history.


def test_lifecycle_presents_bounded_latest_standing_alerts_and_retains_provenance(f, monkeypatch):
    configure_timezone(f)
    p = product(f)
    lot = receipt(f, p, expires_on='2026-11-12').json()
    other = receipt(f, p, expires_on='2026-11-12').json()
    for day in ['2026-11-10', '2026-11-06', '2026-11-09', '2026-11-07', '2026-11-08']:
        persist_alert(f, lot, local_date=day)
    freeze_clock(monkeypatch)
    job = enqueue(f)
    claim = asyncio.run(jobs(f).claim(job_id=job['id']))
    assert asyncio.run(jobs(f).work(claim))['state'] == 'SUCCEEDED'
    alerts = query(f, 'SELECT * FROM expiration_alerts WHERE household_id=:hid AND lot_id=:lid ORDER BY id DESC', lid=lot['id'])
    def summary():
        r = f.request('GET', '/inventory/lifecycle', params={'lot_id': lot['id']})
        assert r.status_code == 200, r.text
        return r.json()['items'][0]['standing_alerts']
    result = summary()
    assert len(result) == 5
    assert [a['id'] for a in result] == [a['id'] for a in alerts[:5]]
    assert result[0]['job_id'] == job['id'] and result[0]['alert_kind'] == 'WARNING'
    assert result[0]['local_date'] == '2026-11-11'
    assert all(set(a) == {'id', 'alert_kind', 'local_date', 'job_id', 'created_at'} for a in result)
    assert not {a['id'] for a in result}.intersection(a['id'] for a in query(f, 'SELECT id FROM expiration_alerts WHERE household_id=:hid AND lot_id=:lid', lid=other['id']))
    assert f.request('PATCH', f"/inventory-lots/{lot['id']}", json={'expires_on': '2027-01-01', 'reason': 'Correction'}).status_code == 200
    assert deduction(f, p, lot, 'disposals', '5').status_code == 201
    assert summary() == result
    before = read_snapshot(f)
    assert summary() == result
    assert read_snapshot(f) == before
    assert query(f, 'SELECT * FROM expiration_alerts WHERE household_id=:hid AND lot_id=:lid ORDER BY id DESC', lid=lot['id']) == alerts


def test_explicit_lot_consumption_of_expired_stock_keeps_current_behavior_open_09_unresolved(f, monkeypatch):
    configure_timezone(f)
    freeze_clock(monkeypatch)
    p = product(f)
    lot = receipt(f, p, expires_on='2026-11-10').json()
    assert f.request('GET', f"/inventory-lots/{lot['id']}").json()['freshness'] == 'EXPIRED'
    r = deduction(f, p, lot, quantity='2', role='MEMBER')
    assert r.status_code == 201, r.text
    assert Decimal(r.json()['allocations'][0]['remaining_quantity']) == 3


def test_fefo_same_lots_order_and_partial_splits_with_and_without_lifecycle_records(f, monkeypatch):
    # Receipt dates and writer semantics stay fixed; lawful ADJUST_IN restores
    # the same lots before comparing, retaining prior negative history.
    from test_inventory_lifecycle import adjust
    configure_timezone(f)
    freeze_clock(monkeypatch)
    freeze_inventory_clock(monkeypatch, datetime.fromisoformat('2026-11-10T17:00:00+00:00'))
    p = product(f)
    old = receipt(f, p, expires_on='2026-11-10', quantity='2').json()
    a = receipt(f, p, expires_on='2026-11-11', quantity='2').json()
    b = receipt(f, p, expires_on='2026-11-12', quantity='3').json()
    def consume():
        r = f.request('POST', '/checkout/deductions', json=demand(p))
        assert r.status_code == 201, r.text
        return r.json()['allocations']
    plain = consume()
    assert [(x['lot_id'], Decimal(x['base_quantity']), Decimal(x['remaining_quantity'])) for x in plain] == [(a['id'], Decimal(2), Decimal(0)), (b['id'], Decimal(2), Decimal(1))]
    assert adjust(f, p, a, '2').status_code == 201
    assert adjust(f, p, b, '3').status_code == 201
    job = enqueue(f)
    claim = asyncio.run(jobs(f).claim(job_id=job['id']))
    asyncio.run(jobs(f).work(claim))
    assert f.request('GET', '/inventory/lifecycle').status_code == 200
    assert f.request('GET', '/inventory-lots').status_code == 200
    assert consume() == plain
    assert query(f, 'SELECT remaining_quantity FROM inventory_lots WHERE household_id=:hid AND id=:lid', lid=old['id'])[0]['remaining_quantity'] == 2
