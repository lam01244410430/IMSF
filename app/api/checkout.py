"""P04-OPEN-07/13 PROPOSAL routes; application coordinator owns the shared UoW."""
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.api.finance import finance_actor, Key, saved_response
from app.api.inventory import InventoryRoute
from app.finance.domain import Actor
from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
from app.finance.ledger_service import LedgerService
from app.inventory.authorization import InventoryHouseholdAccess
from app.inventory.dto import Identifier, StockCommandResponse
from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
from app.inventory.service import InventoryService
from app.checkout.dto import StockCheckoutCreate, PurchaseCheckoutCreate, PurchaseCheckoutResponse
from app.checkout.service import CheckoutService

router = APIRouter(prefix='/api/v1/households/{household_id}/checkout', tags=['checkout'], route_class=InventoryRoute)


def get_checkout_service(session: Annotated[AsyncSession, Depends(get_db)]):
    commands = SqlAlchemyFinanceRepository(session)
    access = SqlAlchemyHouseholdAccess(session)
    inventory = InventoryService(session, SqlAlchemyInventoryRepository(session), InventoryHouseholdAccess(access), commands)
    return CheckoutService(inventory, LedgerService(session, commands, access))


Principal = Annotated[Actor, Depends(finance_actor)]
Service = Annotated[CheckoutService, Depends(get_checkout_service)]


@router.post('/deductions', response_model=StockCommandResponse, status_code=201)
async def deductions(household_id: Identifier, body: StockCheckoutCreate, key: Key, actor: Principal, service: Service):
    return saved_response(await service.deduct(actor, household_id, body, key))


@router.post('/purchases', response_model=PurchaseCheckoutResponse, status_code=201)
async def purchases(household_id: Identifier, body: PurchaseCheckoutCreate, key: Key, actor: Principal, service: Service):
    return saved_response(await service.purchase(actor, household_id, body, key))
