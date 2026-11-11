"""FEFO PROPOSALS P04-OPEN-02/08/12: deterministic dates and allocation."""
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from test_inventory_checkout import configure_timezone, demand, snapshot
from test_inventory_lots import product, receipt
from test_finance_transactions import query


def freeze_inventory_clock(monkeypatch, instant):
    from app.inventory import service
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)
    monkeypatch.setattr(service, 'datetime', Clock)


def test_fefo_orders_expiry_nulls_last_received_at_then_id(f, monkeypatch):
    freeze_inventory_clock(monkeypatch, datetime(2026, 11, 11, tzinfo=timezone.utc))
    configure_timezone(f)
    p = product(f)
    lots = [receipt(f, p, quantity='2', expires_on=expiry, received_at=instant).json()
            for expiry, instant in [(None,'2026-11-01T00:00:00Z'), ('2026-12-01','2026-11-02T00:00:00Z'),
                                   ('2026-12-01','2026-11-01T00:00:00Z'), ('2026-12-01','2026-11-01T00:00:00Z')]]
    r = f.request('POST', '/checkout/deductions', json=demand(p, '7'))
    assert r.status_code == 201, r.text
    assert [(a['lot_id'], Decimal(a['base_quantity'])) for a in r.json()['allocations']] == [
        (lots[2]['id'],Decimal(2)), (lots[3]['id'],Decimal(2)), (lots[1]['id'],Decimal(2)), (lots[0]['id'],Decimal(1))]
    movements = query(f, "SELECT lot_id,quantity_delta FROM inventory_movements WHERE household_id=:hid AND kind='CONSUME' ORDER BY id")
    assert [(m['lot_id'],m['quantity_delta']) for m in movements] == [(lots[i]['id'],Decimal(q)) for i,q in [(2,-2),(3,-2),(1,-2),(0,-1)]]


def test_expiry_day_eligible_yesterday_excluded(f, monkeypatch):
    freeze_inventory_clock(monkeypatch, datetime(2026, 11, 11, tzinfo=timezone.utc))
    configure_timezone(f)
    p = product(f)
    old = receipt(f, p, expires_on='2026-11-10').json()
    today = receipt(f, p, expires_on='2026-11-11').json()
    r = f.request('POST', '/checkout/deductions', json=demand(p))
    assert r.status_code == 201, r.text
    assert [a['lot_id'] for a in r.json()['allocations']] == [today['id']]
    assert Decimal(f.request('GET', f"/inventory-lots/{old['id']}").json()['remaining_quantity']) == 5


@pytest.mark.parametrize('zone,instant,expected', [
    ('Asia/Ho_Chi_Minh','2026-11-10T16:59:59+00:00','2026-11-10'),
    ('Asia/Ho_Chi_Minh','2026-11-10T17:00:00+00:00','2026-11-11'),
    ('America/New_York','2026-11-01T05:59:59+00:00','2026-11-01'),
    ('America/New_York','2026-11-01T06:00:00+00:00','2026-11-01'),
])
def test_timezone_midnight_and_dst_use_one_local_date(f, monkeypatch, zone, instant, expected):
    from app.inventory import fefo
    configure_timezone(f, zone)
    freeze_inventory_clock(monkeypatch, datetime.fromisoformat(instant))
    p, second = product(f), product(f)
    receipt(f, p)
    receipt(f, second)
    original = fefo.allocate
    dates = []
    def observe(*args, **kwargs):
        dates.append(kwargs['local_date'])
        return original(*args, **kwargs)
    monkeypatch.setattr(fefo, 'allocate', observe)
    body = demand(p)
    body['items'] += demand(second)['items']
    assert f.request('POST','/checkout/deductions', json=body).status_code == 201
    assert dates == [date.fromisoformat(expected)]  # one shared allocation/date per attempt


def test_missing_timezone_does_not_invent_settings_default(f):
    configure_timezone(f, None)
    p = product(f)
    receipt(f,p)
    before = snapshot(f)
    r = f.request('POST', '/checkout/deductions', json=demand(p))
    assert r.status_code == 422 and r.json()['error_code'] == 'INVENTORY_TIMEZONE_REQUIRED'
    assert query(f, 'SELECT values FROM household_settings WHERE household_id=:hid')[0]['values'] == {}
    assert snapshot(f) == before


@pytest.mark.parametrize('zone', ['No/Such_Zone', '', 42, '../UTC'])
def test_invalid_timezone_uses_required_error(f, zone):
    configure_timezone(f, zone)
    p = product(f)
    receipt(f,p)
    r = f.request('POST', '/checkout/deductions', json=demand(p))
    assert r.status_code == 422 and r.json()['error_code'] == 'INVENTORY_TIMEZONE_REQUIRED'
