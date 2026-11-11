"""P04-OPEN-07/13 PROPOSAL: one key and transaction across application seams."""
from decimal import Decimal, localcontext
from app.finance.authorization import ADMINISTER
from app.finance.dto import TransactionPost
from app.finance.ports import FinancePosting
from app.inventory.domain import InventoryRequestError
from app.inventory.service import InventoryService
from app.checkout.dto import PurchaseCheckoutResponse


class CheckoutService:
    def __init__(self, inventory: InventoryService, finance: FinancePosting):
        self.inventory, self.finance = inventory, finance

    async def deduct(self, actor, hid, body, key):
        values = body.model_dump()

        async def effect(context):
            return 201, await self.inventory.deduct_in_uow(context, hid, values)

        return await self.inventory._command(
            actor, hid, f"POST /households/{hid}/checkout/deductions", key, values, effect
        )

    async def purchase(self, actor, hid, body, key):
        values = body.model_dump()

        async def effect(context):
            # P04-OPEN-07 PROPOSAL: public settle is never nested here. Finance
            # locks its original/accounts and writes its established effects.
            transaction = await self.finance.post_in_uow(
                context, hid, body.transaction_id, TransactionPost(payments=body.payments)
            )
            if transaction['kind'] != 'EXPENSE':
                raise InventoryRequestError(409, 'INVENTORY_STATE_CONFLICT')
            items = {item['id']: item for item in transaction['items'] if item['product_id'] is not None}
            repo = self.inventory.repository
            # Acquire ALL purchase items before ALL products before ANY lot.
            purchases = await repo.lock_purchases(hid, sorted(items))
            pids = sorted({item['product_id'] for item in items.values()})
            products = {p['id']: p for p in await repo.lock_products(hid, pids)}
            if len(purchases) != len(items) or len(products) != len(pids):
                raise InventoryRequestError(404, 'INVENTORY_NOT_FOUND')
            await repo.lock_lots(hid, pids)
            totals = {iid: Decimal(0) for iid in items}
            receipts = []
            with localcontext() as ctx:
                ctx.prec = 80
                for line in values['lots']:
                    item = items.get(line['item_id'])
                    if item is None:
                        raise InventoryRequestError(404, 'INVENTORY_NOT_FOUND')
                    product = products[item['product_id']]
                    totals[item['id']] += await self.inventory._base_quantity(line, product)
                    receipts.append({k: v for k, v in line.items() if k != 'item_id'} | {
                        'product_id': product['id'], 'purchase_item_id': item['id'],
                        'source_kind': 'PURCHASE', 'reason': None,
                    })
                if any(totals[iid] != Decimal(item['base_quantity']) for iid, item in items.items()):
                    raise InventoryRequestError(409, 'INVENTORY_STATE_CONFLICT')
            lots = [await self.inventory.receive_in_uow(context, hid, receipt) for receipt in receipts]
            result = {'transaction': transaction, 'lot_ids': [lot['id'] for lot in lots],
                      'receipt_movement_ids': [lot['receipt_movement_id'] for lot in lots]}
            return 201, PurchaseCheckoutResponse.model_validate(result).model_dump(mode='json')

        return await self.inventory._command(
            actor, hid, f"POST /households/{hid}/checkout/purchases", key, values, effect,
            additional_permissions=(ADMINISTER,),
        )
