"""P04-OPEN-06/07/09/12/13 PROPOSALS: minimum recipes and atomic cooking.

Recipe mutations lock the parent before ingredients/products. Cooking shares
inventory's command transaction, FEFO allocator and single movement writer.
"""
import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.identity.permissions import PermissionCode as P
from app.inventory.domain import InventoryRequestError
from app.recipes.domain import scale
from app.recipes.dto import RecipeResponse, IngredientResponse, CookingResponse, CookingHistoryResponse
from app.recipes.ports import RecipeRepository


class RecipeService:
    def __init__(self, inventory, repository: RecipeRepository):
        self.inventory, self.repository = inventory, repository

    async def _object(self, resource, hid, identifier, *, lock=False):
        row = await self.repository.get(resource, hid, identifier, lock=lock)
        if row is None:
            raise InventoryRequestError(404, 'INVENTORY_NOT_FOUND')
        return row

    async def _response(self, resource, hid, row):
        if resource == 'recipes':
            row = row | {'ingredients': await self.repository.ingredients(hid, row['id'])}
            dto = RecipeResponse
        else:
            row = row | {'consumption_record_ids': await self.repository.consumption_ids(hid, row['id'])}
            dto = CookingHistoryResponse
        return dto.model_validate(row).model_dump(mode='json')

    async def get(self, actor, hid, resource, identifier):
        async with self.inventory.session.begin():
            await self.inventory.access.resolve(actor, hid, P.VIEW, write=False)
            return await self._response(resource, hid, await self._object(resource, hid, identifier))

    async def page(self, actor, hid, resource, limit, cursor, **filters):
        async with self.inventory.session.begin():
            await self.inventory.access.resolve(actor, hid, P.VIEW, write=False)
            scope = [hid, resource, filters]
            position = None
            if cursor:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    position = decoded['position']
                    if (decoded['scope'] != scope or not isinstance(position, list) or len(position) != 1
                            or type(position[0]) is not int or not 0 < position[0] <= 9223372036854775807):
                        raise ValueError()
                except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
                    raise InventoryRequestError(422, 'INVENTORY_INVALID_INPUT') from None
            rows = await self.repository.page(resource, hid, limit + 1, position, filters)
            next_cursor = None
            if len(rows) > limit:
                rows = rows[:limit]
                next_cursor = base64.urlsafe_b64encode(json.dumps(
                    {'scope': scope, 'position': [rows[-1]['id']]}, sort_keys=True, separators=(',', ':')
                ).encode()).decode()
            return {'items': [await self._response(resource, hid, row) for row in rows], 'next_cursor': next_cursor}

    async def _validate_lines(self, hid, lines):
        pids = sorted({line['product_id'] for line in lines})
        products = await self.inventory.repository.lock_products(hid, pids)
        if len(products) != len(pids):
            raise InventoryRequestError(404, 'INVENTORY_NOT_FOUND')
        products = {p['id']: p for p in products}
        for line in lines:
            product = products[line['product_id']]
            if product['archived_at'] is not None:
                raise InventoryRequestError(409, 'INVENTORY_STATE_CONFLICT')
            await self.inventory._base_quantity(line, product)

    async def create(self, actor, hid, body, key):
        values = body.model_dump()
        async def effect(context):
            await self._validate_lines(hid, values['ingredients'])
            row = await self.repository.create('recipes', {k:v for k,v in values.items() if k != 'ingredients'} | {
                'household_id':hid, 'created_by_member_id':context.member_id})
            for line in values['ingredients']:
                await self.repository.create('recipe-ingredients', line | {'household_id':hid,'recipe_id':row['id']})
            await self.inventory._audit(hid,context,'recipes',row,'CREATED')
            return 201, await self._response('recipes',hid,row)
        return await self.inventory._command(actor,hid,f'POST /households/{hid}/recipes',key,values,effect,permission=P.RECIPE_EDIT)

    async def mutate(self, actor, hid, rid, body, key, *, ingredient_id=None, add=False, archive=False):
        values = body.model_dump(exclude_unset=True)
        method = 'POST' if add or archive else 'PATCH'
        path = f'/households/{hid}/recipes/{rid}'
        if add or ingredient_id is not None:
            path += '/ingredients' + (f'/{ingredient_id}' if ingredient_id is not None else '')
        if archive:
            path += '/archive'
        async def effect(context):
            row = await self._object('recipes',hid,rid,lock=True)
            if row['archived_at'] is not None and not archive:
                raise InventoryRequestError(409,'INVENTORY_STATE_CONFLICT')
            if add or ingredient_id is not None:
                lines = await self.repository.ingredients(hid,rid,lock=True)
                if add:
                    if len(lines) >= 100:
                        raise InventoryRequestError(422,'INVENTORY_INVALID_INPUT')
                    await self._validate_lines(hid,[values])
                    row = await self.repository.create('recipe-ingredients',values | {'household_id':hid,'recipe_id':rid})
                else:
                    line = next((line for line in lines if line['id']==ingredient_id),None)
                    if line is None:
                        raise InventoryRequestError(404,'INVENTORY_NOT_FOUND')
                    await self._validate_lines(hid,[line | values])
                    row = await self.repository.update('recipe-ingredients',hid,ingredient_id,values)
                await self.inventory._audit(hid,context,'recipe-ingredients',row,'CREATED' if add else 'METADATA_UPDATED')
                return 201 if add else 200, IngredientResponse.model_validate(row).model_dump(mode='json')
            updates = {'archived_at':row['archived_at'] or datetime.now(timezone.utc)} if archive else values
            row = await self.repository.update('recipes',hid,rid,updates)
            await self.inventory._audit(hid,context,'recipes',row,'ARCHIVED' if archive else 'METADATA_UPDATED')
            return 200, await self._response('recipes',hid,row)
        return await self.inventory._command(actor,hid,method+' '+path,key,values,effect,permission=P.RECIPE_EDIT)

    async def cook(self, actor, hid, rid, body, key):
        values = body.model_dump()
        async def effect(context):
            row = await self._object('recipes',hid,rid,lock=True)
            lines = await self.repository.ingredients(hid,rid,lock=True)
            if row['archived_at'] is not None:
                raise InventoryRequestError(409,'INVENTORY_STATE_CONFLICT')
            if not lines:
                raise InventoryRequestError(422,'INVENTORY_INVALID_INPUT')
            executed = []
            history = None
            async def demands(products):
                demands = []
                for line in lines:
                    product = products[line['product_id']]
                    factor = (Decimal(1) if line['unit_id']==product['base_unit_id'] else
                              await self.inventory.repository.factor(line['unit_id'],product['base_unit_id']))
                    requested, base = scale(line['quantity'],values['servings'],row['servings'],factor)
                    executed.append({k:line[k] for k in ('id','line_no','product_id','unit_id','essential')} | {
                        'quantity':format(line['quantity'],'f'),'requested_quantity':format(requested,'f'),
                        'base_unit_id':product['base_unit_id'],'base_quantity':format(base,'f'),
                        'conversion_factor':format(factor,'f')})
                    demands.append({'product_id':product['id'],'unit_id':product['base_unit_id'],'quantity':base})
                return demands
            async def record(plans, movement_ids, local_date, zone):
                nonlocal history
                snapshot = {'schema_version':1,
                    'recipe':{'id':row['id'],'name':row['name'],'servings':format(row['servings'],'f'),'instructions':row['instructions']},
                    'servings':format(values['servings'],'f'), 'ingredients':executed,
                    'local_date':local_date.isoformat(),'timezone':zone,
                    'allocations':[{'product_id':lot['product_id'],'lot_id':lot['id'],'movement_id':mid,'base_quantity':format(amount,'f')}
                                   for (lot,amount),mid in zip(plans,movement_ids,strict=True)]}
                history = await self.repository.create('recipe-cooking-history',{
                    'household_id':hid,'recipe_id':rid,'actor_member_id':context.member_id,
                    'cooked_at':datetime.now(timezone.utc),'servings':values['servings'],'recipe_snapshot':snapshot})
                return history['id']
            result = await self.inventory.deduct_in_uow(context,hid,{'items':lines,'reason_code':'COOKING'},
                prepare_demands=demands,before_write=record)
            await self.inventory._audit(hid,context,'recipe-cooking-history',history,'COOKED')
            return 201,CookingResponse.model_validate({'history_id':history['id'],'recipe_id':rid,
                'servings':values['servings'],'consumption_record_ids':result['consumption_record_ids'],
                'allocations':result['allocations']}).model_dump(mode='json')
        return await self.inventory._command(actor,hid,f'POST /households/{hid}/recipes/{rid}/cook',key,values,effect,permission=P.COOK)
