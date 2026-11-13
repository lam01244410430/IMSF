"""P05-OPEN-07 PROPOSAL: thin scoped reads and authorized enqueue, fixed role grants."""
from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.api.finance import Limit, Cursor, Key, saved_response
from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
from app.inventory.dto import EmptyCommand
from app.api.inventory import InventoryRoute, Principal
from app.finance.dto import Identifier
from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
from app.inventory.authorization import InventoryHouseholdAccess
from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
from app.lifecycle.dto import Freshness, AlertKind, LifecyclePage, ExpirationAlertPage, ExpirationAlertResponse, ExpiryRunResponse
from app.lifecycle.infrastructure.repositories import SqlAlchemyLifecycleRepository
from app.lifecycle.service import LifecycleService

router = APIRouter(prefix="/api/v1/households/{household_id}", tags=["lifecycle"], route_class=InventoryRoute)


def get_lifecycle_service(session: Annotated[AsyncSession, Depends(get_db)]):
    return LifecycleService(session, SqlAlchemyLifecycleRepository(session),
        SqlAlchemyInventoryRepository(session), InventoryHouseholdAccess(SqlAlchemyHouseholdAccess(session)),
        SqlAlchemyFinanceRepository(session))


Service = Annotated[LifecycleService, Depends(get_lifecycle_service)]


@router.get("/inventory/lifecycle", response_model=LifecyclePage)
async def lifecycle(household_id: Identifier, actor: Principal, service: Service,
                    limit: Limit = 50, cursor: Cursor = None,
                    product_id: Identifier | None = None, lot_id: Identifier | None = None,
                    freshness: Freshness | None = None):
    return await service.lifecycle(actor, household_id, limit, cursor,
                                   product_id=product_id, lot_id=lot_id, freshness=freshness)


@router.get("/expiration-alerts", response_model=ExpirationAlertPage)
async def alerts(household_id: Identifier, actor: Principal, service: Service,
                 limit: Limit = 50, cursor: Cursor = None, lot_id: Identifier | None = None,
                 kind: AlertKind | None = None, local_date_from: date | None = None,
                 local_date_to: date | None = None):
    return await service.alerts(actor, household_id, limit, cursor, lot_id=lot_id, kind=kind,
                                local_date_from=local_date_from, local_date_to=local_date_to)


@router.get("/expiration-alerts/{alert_id}", response_model=ExpirationAlertResponse)
async def alert(household_id: Identifier, alert_id: Identifier, actor: Principal, service: Service):
    return await service.alert(actor, household_id, alert_id)


@router.post("/inventory/expiry-runs", response_model=ExpiryRunResponse, status_code=202)
async def enqueue(household_id: Identifier, body: EmptyCommand, key: Key,
                  actor: Principal, service: Service):
    return saved_response(await service.enqueue(actor, household_id, body, key))


@router.get("/inventory/expiry-runs/{job_id}", response_model=ExpiryRunResponse)
async def expiry_run(household_id: Identifier, job_id: Identifier,
                     actor: Principal, service: Service):
    return await service.expiry_run(actor, household_id, job_id)
