"""P06 Step 2 PROPOSAL: household-scoped SELECTs only; caller owns snapshot."""

from sqlalchemy import text


class SqlAlchemyInventoryReportRepository:
    def __init__(self, session):
        self.session = session

    async def contains(self, hid, resource, identifier):
        # Only these internal resource names may choose a relation.
        table = {"product_id": "products", "lot_id": "inventory_lots"}[resource]
        return await self.session.scalar(text(
            f"SELECT EXISTS(SELECT 1 FROM {table} WHERE household_id=:hid AND id=:id)"
        ), {"hid": hid, "id": identifier})

    async def valuation_rows(self, hid, filters):
        # Corrections are adjustments in storage. Attribute their signed deltas
        # to the root movement kind so consumption/disposal/return corrections
        # net there; ordinary adjustments (and receipt corrections) stay net stock
        # adjustments. Retained append-only links give an acyclic ancestry.
        result = await self.session.execute(text("""
            WITH RECURSIVE lots AS (
                SELECT l.*, p.base_unit_id, p.archived_at AS product_archived_at
                FROM inventory_lots l
                JOIN products p ON (p.household_id,p.id)=(l.household_id,l.product_id)
                WHERE l.household_id=:hid
                  AND (CAST(:product_id AS bigint) IS NULL OR l.product_id=:product_id)
                  AND (CAST(:lot_id AS bigint) IS NULL OR l.id=:lot_id)
                  AND (CAST(:currency AS text) IS NULL OR l.cost_currency=:currency)
                  AND (CAST(:archived AS boolean) IS NULL OR (l.archived_at IS NOT NULL)=:archived)
            ), movements AS (
                SELECT m.* FROM inventory_movements m
                JOIN lots l ON (l.household_id,l.id)=(m.household_id,m.lot_id)
            ), attributed AS (
                SELECT id, lot_id, kind AS root_kind, kind, quantity_delta
                FROM movements WHERE correction_of_movement_id IS NULL
                UNION ALL
                SELECT m.id, m.lot_id, a.root_kind, m.kind, m.quantity_delta
                FROM movements m JOIN attributed a
                  ON a.id=m.correction_of_movement_id AND a.lot_id=m.lot_id
            ), deltas AS (
                SELECT lot_id,
                    coalesce(sum(quantity_delta) FILTER (WHERE root_kind='CONSUME'),0) AS consumed_delta,
                    coalesce(sum(quantity_delta) FILTER (WHERE root_kind='DISPOSE'),0) AS disposed_delta,
                    coalesce(sum(quantity_delta) FILTER (WHERE root_kind='RETURN'),0) AS returned_delta,
                    coalesce(sum(quantity_delta) FILTER (WHERE root_kind IN ('ADJUST_IN','ADJUST_OUT')
                        OR (root_kind='RECEIPT' AND kind<>'RECEIPT')),0) AS adjusted_delta
                FROM attributed GROUP BY lot_id
            )
            SELECT l.*, coalesce(d.consumed_delta,0) AS consumed_delta,
                coalesce(d.disposed_delta,0) AS disposed_delta,
                coalesce(d.returned_delta,0) AS returned_delta,
                coalesce(d.adjusted_delta,0) AS adjusted_delta,
                i.net_amount AS purchase_net_amount, i.transaction_id AS purchase_transaction_id,
                t.currency_code AS purchase_currency,
                EXISTS(SELECT 1 FROM transactions r
                    WHERE r.household_id=l.household_id AND r.original_transaction_id=t.id
                      AND r.kind='REVERSAL' AND r.status='POSTED') AS reversed_original
            FROM lots l LEFT JOIN deltas d ON d.lot_id=l.id
            LEFT JOIN transaction_items i
              ON (i.household_id,i.id,i.product_id)=(l.household_id,l.purchase_item_id,l.product_id)
            LEFT JOIN transactions t
              ON (t.household_id,t.id)=(i.household_id,i.transaction_id)
            ORDER BY l.id
        """), {"hid": hid, **filters})
        return [dict(row) for row in result.mappings()]

    async def household_timezone(self, hid):
        # Same settings read as the inventory repository, with no default/write.
        values = await self.session.scalar(text(
            "SELECT values FROM household_settings WHERE household_id=:hid"
        ), {"hid": hid})
        return values.get("timezone") if isinstance(values, dict) else None

    async def waste_rows(self, hid, filters):
        # Extend valuation's recursive attribution with root identity/time.
        # Restrict roots by time, never their corrections: later corrections
        # must still repair the original event's month and recorded reason.
        result = await self.session.execute(text("""
            WITH RECURSIVE lots AS (
                SELECT l.id, l.household_id, l.product_id, l.cost_currency,
                    l.unit_cost, l.received_quantity,
                    ((CAST(:from_date AS date) IS NULL OR l.received_at >=
                        (CAST(:from_date AS date)::timestamp AT TIME ZONE :timezone))
                     AND (CAST(:to_date AS date) IS NULL OR l.received_at <
                        ((CAST(:to_date AS date)+1)::timestamp AT TIME ZONE :timezone))) AS received_in_period
                FROM inventory_lots l
                WHERE l.household_id=:hid
                  AND (CAST(:product_id AS bigint) IS NULL OR l.product_id=:product_id)
                  AND (CAST(:currency AS text) IS NULL OR l.cost_currency=:currency)
            ), movements AS (
                SELECT m.* FROM inventory_movements m
                JOIN lots l ON (l.household_id,l.id)=(m.household_id,m.lot_id)
            ), attributed AS (
                SELECT id, lot_id, id AS root_id, kind AS root_kind,
                    occurred_at AS root_occurred_at, quantity_delta
                FROM movements
                WHERE correction_of_movement_id IS NULL AND kind IN ('DISPOSE','CONSUME')
                  AND (CAST(:from_date AS date) IS NULL OR occurred_at >=
                    (CAST(:from_date AS date)::timestamp AT TIME ZONE :timezone))
                  AND (CAST(:to_date AS date) IS NULL OR occurred_at <
                    ((CAST(:to_date AS date)+1)::timestamp AT TIME ZONE :timezone))
                UNION ALL
                SELECT m.id, m.lot_id, a.root_id, a.root_kind,
                    a.root_occurred_at, m.quantity_delta
                FROM movements m JOIN attributed a
                  ON a.id=m.correction_of_movement_id AND a.lot_id=m.lot_id
            ), events AS (
                SELECT lot_id, root_id, root_kind,
                    to_char(root_occurred_at AT TIME ZONE :timezone,'YYYY-MM') AS period,
                    sum(quantity_delta) AS net_delta
                FROM attributed GROUP BY lot_id, root_id, root_kind, root_occurred_at
                HAVING sum(quantity_delta) <> 0
            )
            SELECT l.*, e.root_id, e.root_kind, e.period, e.net_delta, d.reason_code
            FROM lots l LEFT JOIN events e ON e.lot_id=l.id
            LEFT JOIN disposal_records d
              ON (d.household_id,d.movement_id)=(l.household_id,e.root_id)
            ORDER BY l.id, e.root_id
        """), {"hid": hid, **filters})
        return [dict(row) for row in result.mappings()]
