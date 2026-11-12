"""P04-OPEN-13 PROPOSAL: bounded diagnostics from one committed SQL snapshot.

SELECT only. No locks, repairs, audit records, valuation or financial resolution.
Source totals include every split even when the caller filters to a single lot.
"""

from sqlalchemy import text

# Each category returns its complete count and its first 100 stable identifiers.
# Numeric quantities are cast to text inside SQL, never through JSON floats.
INTEGRITY_QUERY = text("""
WITH scoped AS MATERIALIZED (
    SELECT l.* FROM inventory_lots l
    WHERE l.household_id=:hid
      AND (CAST(:product_id AS bigint) IS NULL OR l.product_id=:product_id)
      AND (CAST(:lot_id AS bigint) IS NULL OR l.id=:lot_id)
), movement_totals AS (
    SELECT m.lot_id, sum(m.quantity_delta) AS total,
        count(*) FILTER (WHERE m.kind='RECEIPT') AS receipts,
        coalesce(sum(m.quantity_delta) FILTER (WHERE m.kind='RECEIPT'),0) AS received,
        count(DISTINCT m.kind) FILTER (WHERE m.quantity_delta<0) AS negative_kinds,
        min(m.kind) FILTER (WHERE m.quantity_delta<0) AS negative_kind
    FROM inventory_movements m JOIN scoped l ON l.id=m.lot_id AND l.household_id=m.household_id
    WHERE m.household_id=:hid GROUP BY m.lot_id
), lots AS (
    SELECT l.*, coalesce(m.total,0) AS movement_total, coalesce(m.receipts,0) AS receipts,
        coalesce(m.received,0) AS receipt_quantity,
        CASE WHEN l.remaining_quantity>0 THEN NULL
             WHEN coalesce(m.negative_kinds,0)<>1 THEN 'MIXED'
             WHEN m.negative_kind='CONSUME' THEN 'CONSUMED'
             WHEN m.negative_kind='DISPOSE' THEN 'DISCARDED'
             WHEN m.negative_kind='RETURN' THEN 'RETURNED'
             WHEN m.negative_kind='ADJUST_OUT' THEN 'ADJUSTED_OUT' END AS expected_terminal
    FROM scoped l LEFT JOIN movement_totals m ON m.lot_id=l.id
), details AS (
    SELECT m.id,m.lot_id,l.product_id,m.kind,
        (SELECT count(*) FROM consumption_records c WHERE c.household_id=:hid AND c.movement_id=m.id) AS consumption_count,
        (SELECT count(*) FROM disposal_records d WHERE d.household_id=:hid AND d.movement_id=m.id) AS disposal_count,
        (SELECT count(*) FROM inventory_adjustments a WHERE a.household_id=:hid AND a.movement_id=m.id) AS adjustment_count
    FROM inventory_movements m JOIN scoped l ON (l.household_id,l.id)=(m.household_id,m.lot_id)
    WHERE m.household_id=:hid
), purchase_totals AS (
    SELECT l.purchase_item_id,sum(l.received_quantity) AS received
    FROM inventory_lots l WHERE l.household_id=:hid AND l.source_kind='PURCHASE'
      AND l.purchase_item_id IN (SELECT purchase_item_id FROM scoped)
    GROUP BY l.purchase_item_id
), purchases AS (
    SELECT l.*, i.transaction_id,i.base_quantity,i.product_id AS item_product_id,
        t.status,t.kind AS transaction_kind,
        EXISTS (SELECT 1 FROM transactions r WHERE r.household_id=:hid
            AND r.original_transaction_id=t.id AND r.kind='REVERSAL' AND r.status='POSTED') AS reversed
    FROM scoped l LEFT JOIN transaction_items i ON (i.household_id,i.id)=(l.household_id,l.purchase_item_id)
    LEFT JOIN transactions t ON (t.household_id,t.id)=(i.household_id,i.transaction_id)
    WHERE l.source_kind='PURCHASE'
), issues AS (
    SELECT 'projection_mismatches' AS category,l.id AS sort_id,
        jsonb_build_object('code','PROJECTION_MISMATCH','lot_id',l.id,'product_id',l.product_id,
            'expected_quantity',l.movement_total::text,'actual_quantity',l.remaining_quantity::text) AS item
    FROM lots l WHERE l.remaining_quantity<>l.movement_total
    UNION ALL
    SELECT 'receipt_anomalies',l.id,
        jsonb_build_object('code','RECEIPT_ANOMALY','lot_id',l.id,'product_id',l.product_id,
            'expected_count',1,'actual_count',l.receipts,
            'expected_quantity',l.received_quantity::text,'actual_quantity',l.receipt_quantity::text)
    FROM lots l WHERE l.receipts<>1 OR l.receipt_quantity<>l.received_quantity
    UNION ALL
    SELECT 'detail_misalignments',d.id,
        jsonb_build_object('code','DETAIL_MISALIGNMENT','movement_id',d.id,'lot_id',d.lot_id,
            'product_id',d.product_id,'kind',d.kind,'consumption_count',d.consumption_count,
            'disposal_count',d.disposal_count,'adjustment_count',d.adjustment_count)
    FROM details d WHERE d.consumption_count<>CASE WHEN d.kind='CONSUME' THEN 1 ELSE 0 END
        OR d.disposal_count<>CASE WHEN d.kind='DISPOSE' THEN 1 ELSE 0 END
        OR d.adjustment_count<>CASE WHEN d.kind IN ('ADJUST_IN','ADJUST_OUT') THEN 1 ELSE 0 END
    UNION ALL
    SELECT 'source_cap_violations',p.purchase_item_id,
        jsonb_build_object('code','SOURCE_CAP_EXCEEDED','purchase_item_id',p.purchase_item_id,
            'product_id',i.product_id,'transaction_id',i.transaction_id,
            'expected_quantity',i.base_quantity::text,'actual_quantity',p.received::text)
    FROM purchase_totals p JOIN transaction_items i ON i.household_id=:hid AND i.id=p.purchase_item_id
    WHERE p.received>i.base_quantity
    UNION ALL
    SELECT 'terminal_state_inconsistencies',l.id,
        jsonb_build_object('code','TERMINAL_STATE_INCONSISTENCY','lot_id',l.id,'product_id',l.product_id,
            'expected_state',l.expected_terminal,'actual_state',l.terminal_state)
    FROM lots l WHERE l.terminal_state IS DISTINCT FROM l.expected_terminal
        OR ((l.remaining_quantity=0)<>(l.terminal_state IS NOT NULL))
    UNION ALL
    SELECT 'purchase_link_inconsistencies',p.id,
        jsonb_build_object('code','PURCHASE_LINK_INCONSISTENCY','lot_id',p.id,'product_id',p.product_id,
            'purchase_item_id',p.purchase_item_id,'transaction_id',p.transaction_id,
            'transaction_status',p.status,'transaction_kind',p.transaction_kind)
    FROM purchases p WHERE p.status IS DISTINCT FROM 'POSTED' OR p.transaction_kind IS DISTINCT FROM 'EXPENSE'
        OR p.product_id IS DISTINCT FROM p.item_product_id OR p.base_quantity IS NULL OR p.base_quantity<=0 OR p.reversed
    UNION ALL
    SELECT 'receipt_posting_mismatches',m.id,
        jsonb_build_object('code','RECEIPT_POSTING_MISMATCH','movement_id',m.id,'lot_id',p.id,
            'product_id',p.product_id,'purchase_item_id',p.purchase_item_id,'transaction_id',p.transaction_id,
            'actual_transaction_id',m.transaction_id)
    FROM purchases p JOIN inventory_movements m ON m.household_id=:hid AND m.lot_id=p.id AND m.kind='RECEIPT'
    WHERE m.transaction_id IS DISTINCT FROM p.transaction_id
    UNION ALL
    SELECT 'unresolved_refund_inventory_links',r.id,
        jsonb_build_object('code','UNRESOLVED_REFUND_INVENTORY_LINK','link_id',r.id,'lot_id',r.lot_id,
            'product_id',l.product_id,'purchase_item_id',r.purchase_item_id,
            'transaction_id',r.original_transaction_id,'return_movement_id',r.return_movement_id)
    FROM refund_inventory_links r JOIN scoped l ON (l.household_id,l.id)=(r.household_id,r.lot_id)
    WHERE r.household_id=:hid
), ranked AS (
    SELECT *,row_number() OVER (PARTITION BY category ORDER BY sort_id) AS position FROM issues
)
SELECT category,count(*) AS count,
    jsonb_agg(item ORDER BY sort_id) FILTER (WHERE position<=100) AS items
FROM ranked GROUP BY category
""")
