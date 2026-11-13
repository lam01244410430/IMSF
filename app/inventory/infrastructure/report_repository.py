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
