"""P06 Step 4 PROPOSAL: SELECT-only full-scope aggregates and bounded pages.

The existing recursive attribution is shared by each report's page and totals.
SQL NUMERIC values inside JSON aggregates are cast to text before decoding: no
JSON floating-point money enters Python. Identifier lists are first 100 with
complete SQL counts; page queries return at most 201 rows, aggregates one row.
The caller owns the single read-only snapshot. No repository starts a transaction.
"""

from sqlalchemy import text


VALUATION_CTES = """
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
"""

VALUATION_SELECT = """
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
"""

VALUATION_AGGREGATES = VALUATION_CTES + ", valued AS (" + VALUATION_SELECT + ")" + """
, quantities AS (
    SELECT v.*, abs(consumed_delta) AS consumed_quantity,
        abs(disposed_delta) AS disposed_quantity, abs(returned_delta) AS returned_quantity,
        -adjusted_delta AS adjusted_out_quantity
    FROM valued v
), checks AS (
    SELECT q.*,
        received_quantity = remaining_quantity + consumed_quantity + disposed_quantity
            + returned_quantity + adjusted_out_quantity AS quantity_tied,
        CASE WHEN unit_cost IS NOT NULL THEN received_quantity * unit_cost =
            remaining_quantity * unit_cost + consumed_quantity * unit_cost + disposed_quantity * unit_cost
            + returned_quantity * unit_cost + adjusted_out_quantity * unit_cost END AS value_tied,
        CASE WHEN purchase_item_id IS NOT NULL THEN
            CASE WHEN unit_cost IS NULL THEN 'UNKNOWN_COST'
                 WHEN received_quantity * unit_cost = purchase_net_amount AND cost_currency = purchase_currency
                 THEN 'AGREEMENT' ELSE 'PURCHASE_MISMATCH' END END AS purchase_status
    FROM quantities q
), scope AS (
    SELECT * FROM checks WHERE CAST(:summary_currency AS text) IS NULL
        OR coalesce(cost_currency,purchase_currency) = :summary_currency
), issues AS (
    SELECT id AS lot_id, coalesce(cost_currency,purchase_currency) AS currency, issue.code, issue.ordinal
    FROM scope CROSS JOIN LATERAL (VALUES
        ('TIE_OUT_MISMATCH', 0, NOT quantity_tied OR value_tied IS FALSE),
        ('PURCHASE_MISMATCH', 1, purchase_status='PURCHASE_MISMATCH'),
        ('REVERSED_ORIGINAL', 2, purchase_item_id IS NOT NULL AND reversed_original)
    ) AS issue(code,ordinal,present) WHERE issue.present
)

SELECT
    (SELECT coalesce(jsonb_agg(jsonb_build_object('currency',cost_currency, 'received_value', received_value::text, 'remaining_value', remaining_value::text, 'consumed_value', consumed_value::text, 'disposed_value', disposed_value::text, 'returned_value', returned_value::text, 'adjusted_out_value', adjusted_out_value::text)
        ORDER BY cost_currency),'[]'::jsonb)
     FROM (SELECT cost_currency, sum(received_quantity * unit_cost) AS received_value,
sum(remaining_quantity * unit_cost) AS remaining_value,
sum(consumed_quantity * unit_cost) AS consumed_value,
sum(disposed_quantity * unit_cost) AS disposed_value,
sum(returned_quantity * unit_cost) AS returned_value,
sum(adjusted_out_quantity * unit_cost) AS adjusted_out_value FROM scope WHERE unit_cost IS NOT NULL GROUP BY cost_currency) totals
    ) AS totals_by_currency,
    (SELECT jsonb_build_object('count',count(*),'items',
        (SELECT coalesce(jsonb_agg(jsonb_build_object('lot_id',id,'product_id',product_id,
            'base_unit_id',base_unit_id, 'received_quantity', received_quantity::text, 'remaining_quantity', remaining_quantity::text, 'consumed_quantity', consumed_quantity::text, 'disposed_quantity', disposed_quantity::text, 'returned_quantity', returned_quantity::text, 'adjusted_out_quantity', adjusted_out_quantity::text) ORDER BY id),'[]'::jsonb)
         FROM (SELECT * FROM checks WHERE unit_cost IS NULL ORDER BY id LIMIT 100) first_unknown))
     FROM checks WHERE unit_cost IS NULL) AS unknown_cost,
    (SELECT jsonb_build_object(
        'checked_lots',count(*),
        'quantity_tied_out_count',count(*) FILTER (WHERE quantity_tied),
        'value_tied_out_count',count(*) FILTER (WHERE value_tied),
        'unknown_cost_count',count(*) FILTER (WHERE unit_cost IS NULL),
        'purchase_agreement_count',count(*) FILTER (WHERE purchase_status='AGREEMENT'),
        'purchase_mismatch_count',count(*) FILTER (WHERE purchase_status='PURCHASE_MISMATCH'),
        'purchase_unknown_cost_count',count(*) FILTER (WHERE purchase_status='UNKNOWN_COST'),
        'reversed_original_count',count(*) FILTER (WHERE purchase_item_id IS NOT NULL AND reversed_original),
        'tie_out_mismatch_count',count(*) FILTER (WHERE NOT quantity_tied OR value_tied IS FALSE))
     FROM scope) AS reconciliation,
    (SELECT jsonb_build_object('count',count(*),'items',
        (SELECT coalesce(jsonb_agg(jsonb_build_object('lot_id',lot_id,'currency',currency,'code',code)
             ORDER BY lot_id,ordinal),'[]'::jsonb)
         FROM (SELECT * FROM issues ORDER BY lot_id,ordinal LIMIT 100) first_issues))
     FROM issues) AS issues,
    (SELECT coalesce(jsonb_agg(currency ORDER BY currency),'[]'::jsonb)
     FROM (SELECT DISTINCT coalesce(cost_currency,purchase_currency) AS currency FROM scope
           WHERE coalesce(cost_currency,purchase_currency) IS NOT NULL) observed) AS currencies
"""

WASTE_CTES = """
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
, waste AS (
SELECT l.*, e.root_id, e.root_kind, e.period, e.net_delta, d.reason_code
            FROM lots l LEFT JOIN events e ON e.lot_id=l.id
            LEFT JOIN disposal_records d
              ON (d.household_id,d.movement_id)=(l.household_id,e.root_id)

), known AS (
    SELECT *, abs(net_delta) AS quantity, abs(net_delta)*unit_cost AS value
    FROM waste WHERE unit_cost IS NOT NULL AND root_kind='DISPOSE'
        AND (CAST(:reason AS text) IS NULL OR reason_code=:reason)
), unknown_events AS (
    SELECT * FROM waste WHERE unit_cost IS NULL AND root_id IS NOT NULL
), denominators AS (
    SELECT cost_currency, sum(received_quantity*unit_cost) AS value FROM lots
    WHERE unit_cost IS NOT NULL AND received_in_period GROUP BY cost_currency
), currencies AS (
    SELECT cost_currency FROM denominators UNION SELECT cost_currency FROM known
), waste_issues AS (
    SELECT id AS lot_id, 'TIE_OUT_MISMATCH' AS code FROM known GROUP BY id,unit_cost
    HAVING sum(abs(net_delta))*unit_cost <> abs(sum(net_delta))*unit_cost
)
"""

WASTE_AGGREGATES = WASTE_CTES + """

SELECT
    (SELECT coalesce(jsonb_agg(jsonb_build_object(
        'currency',c.cost_currency,
        'disposed',jsonb_build_object('quantity',coalesce(d.quantity,0)::text,'value',coalesce(d.value,0)::text),
        'denominator',jsonb_build_object('basis','total_received_value_known_cost',
            'value',coalesce(den.value,0)::text,'scope','same period and filters'),
        'by_reason',(SELECT coalesce(jsonb_agg(jsonb_build_object('reason_code',reason_code,
            'quantity',quantity::text,'value',value::text) ORDER BY
                array_position(ARRAY['EXPIRED','SPOILED','DAMAGED','OTHER'],reason_code)),'[]'::jsonb)
            FROM (SELECT reason_code,sum(quantity) AS quantity,sum(value) AS value
                  FROM known WHERE cost_currency=c.cost_currency GROUP BY reason_code) reasons),
        'by_period',(SELECT coalesce(jsonb_agg(jsonb_build_object('period',period,
            'quantity',quantity::text,'value',value::text) ORDER BY period),'[]'::jsonb)
            FROM (SELECT period,sum(quantity) AS quantity,sum(value) AS value
                  FROM known WHERE cost_currency=c.cost_currency GROUP BY period) periods)
        ) ORDER BY c.cost_currency),'[]'::jsonb)
     FROM currencies c LEFT JOIN denominators den USING(cost_currency)
     LEFT JOIN (SELECT cost_currency,sum(quantity) AS quantity,sum(value) AS value
                FROM known GROUP BY cost_currency) d USING(cost_currency)) AS sections,
    (SELECT jsonb_build_object(
        'disposed_quantity',coalesce(sum(abs(net_delta)) FILTER (WHERE root_kind='DISPOSE'),0)::text,
        'consumed_quantity',coalesce(sum(abs(net_delta)) FILTER (WHERE root_kind='CONSUME'),0)::text,
        'count',count(DISTINCT id),
        'lot_ids',(SELECT coalesce(jsonb_agg(id ORDER BY id),'[]'::jsonb)
                   FROM (SELECT DISTINCT id FROM unknown_events ORDER BY id LIMIT 100) ids),
        'by_reason',(SELECT coalesce(jsonb_agg(jsonb_build_object('reason_code',reason_code,
            'quantity',quantity::text) ORDER BY
                array_position(ARRAY['EXPIRED','SPOILED','DAMAGED','OTHER'],reason_code)),'[]'::jsonb)
            FROM (SELECT reason_code,sum(abs(net_delta)) AS quantity FROM unknown_events
                  WHERE root_kind='DISPOSE' AND reason_code IN ('EXPIRED','SPOILED','DAMAGED','OTHER')
                    AND (CAST(:reason AS text) IS NULL OR reason_code=:reason) GROUP BY reason_code) reasons)
        ) FROM unknown_events) AS unknown_cost,
    (SELECT jsonb_build_object('status',CASE WHEN count(*)=0 THEN 'TIED_OUT' ELSE 'TIE_OUT_MISMATCH' END,
        'issues',jsonb_build_object('count',count(*),'items',
            (SELECT coalesce(jsonb_agg(jsonb_build_object('lot_id',lot_id,'code',code) ORDER BY lot_id),'[]'::jsonb)
             FROM (SELECT * FROM waste_issues ORDER BY lot_id LIMIT 100) first_issues)))
     FROM waste_issues) AS reconciliation
"""

class SqlAlchemyInventoryReportRepository:
    def __init__(self, session):
        self.session = session

    async def contains(self, hid, resource, identifier):
        table = {"product_id": "products", "lot_id": "inventory_lots"}[resource]
        return await self.session.scalar(text(
            f"SELECT EXISTS(SELECT 1 FROM {table} WHERE household_id=:hid AND id=:id)"
        ), {"hid": hid, "id": identifier})

    async def valuation_page_rows(self, hid, filters, position, fetch):
        # P06 Step 4 PROPOSAL: bound even direct repository callers to page size.
        result = await self.session.execute(text(VALUATION_CTES + VALUATION_SELECT +
            " WHERE l.id > :position ORDER BY l.id LIMIT :fetch"),
            {"hid": hid, **filters, "position": position, "fetch": min(fetch, 201)})
        return [dict(row) for row in result.mappings()]

    async def valuation_aggregates(self, hid, filters):
        # summary_currency narrows currency facts but keeps unknown-cost global.
        # Normal valuation continues to scope lots by its original cost_currency.
        result = await self.session.execute(text(VALUATION_AGGREGATES),
            {"summary_currency": None, "hid": hid, **filters})
        return dict(result.mappings().one())

    async def household_timezone(self, hid):
        values = await self.session.scalar(text(
            "SELECT values FROM household_settings WHERE household_id=:hid"
        ), {"hid": hid})
        return values.get("timezone") if isinstance(values, dict) else None

    async def waste_aggregates(self, hid, filters):
        result = await self.session.execute(text(WASTE_AGGREGATES), {"hid": hid, **filters})
        return dict(result.mappings().one())

    async def waste_product_rows(self, hid, filters, position, fetch):
        result = await self.session.execute(text(WASTE_CTES + """
            SELECT cost_currency AS currency, product_id, sum(quantity) AS quantity, sum(value) AS value
            FROM known WHERE (cost_currency,product_id) > (:position_currency,:position_product)
            GROUP BY cost_currency,product_id ORDER BY cost_currency,product_id LIMIT :fetch
        """), {"hid": hid, **filters, "position_currency": position[0],
               "position_product": position[1], "fetch": min(fetch, 201)})
        return [dict(row) for row in result.mappings()]
