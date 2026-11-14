"""P06 Step 4 PROPOSAL: bounded SELECT-only finance inputs; caller owns snapshot."""

from sqlalchemy import text


class SqlAlchemyFinanceReportRepository:
    def __init__(self, session):
        self.session = session

    async def currency_aggregates(self, hid, filters):
        # EXISTS counts an item once even when split across several receipts.
        # Money in JSON is text, preserving exact NUMERIC without JSON floats.
        # One aggregate result row; no materialization of items or ledger entries.
        result = await self.session.execute(text("""
            WITH expense_items AS (
                SELECT t.currency_code, i.net_amount,
                    EXISTS(SELECT 1 FROM inventory_lots l
                           WHERE (l.household_id,l.purchase_item_id)=(i.household_id,i.id)) AS linked
                FROM transactions t JOIN transaction_items i
                    ON (i.household_id,i.transaction_id)=(t.household_id,t.id)
                WHERE t.household_id=:hid AND t.kind='EXPENSE' AND t.status='POSTED'
                  AND (CAST(:currency AS text) IS NULL OR t.currency_code=:currency)
            ), purchases AS (
                SELECT currency_code,
                    coalesce(sum(net_amount) FILTER (WHERE linked),0) AS linked_total,
                    count(*) FILTER (WHERE linked) AS linked_item_count,
                    coalesce(sum(net_amount) FILTER (WHERE NOT linked),0) AS unlinked_total,
                    count(*) FILTER (WHERE NOT linked) AS unlinked_item_count
                FROM expense_items GROUP BY currency_code
            ), balances AS (
                SELECT a.currency_code,a.id AS account_id,sum(e.signed_amount) AS balance
                FROM accounts a JOIN account_ledger_entries e
                    ON (e.household_id,e.account_id,e.currency_code)=(a.household_id,a.id,a.currency_code)
                WHERE a.household_id=:hid
                  AND (CAST(:currency AS text) IS NULL OR a.currency_code=:currency)
                GROUP BY a.currency_code,a.id
            ), observed AS (
                SELECT currency_code FROM purchases UNION SELECT currency_code FROM balances
            )
            SELECT coalesce(jsonb_agg(jsonb_build_object('currency',o.currency_code,
                'purchase',jsonb_build_object(
                    'linked_total',coalesce(p.linked_total,0)::text,
                    'linked_item_count',coalesce(p.linked_item_count,0),
                    'unlinked_total',coalesce(p.unlinked_total,0)::text,
                    'unlinked_item_count',coalesce(p.unlinked_item_count,0)),
                'ledger_balances',(SELECT jsonb_agg(jsonb_build_object('account_id',account_id,
                    'balance',balance::text) ORDER BY account_id) FROM balances b
                    WHERE b.currency_code=o.currency_code)
                ) ORDER BY o.currency_code),'[]'::jsonb) AS sections
            FROM observed o LEFT JOIN purchases p USING(currency_code)
        """), {"hid": hid, **filters})
        return result.mappings().one()["sections"]
