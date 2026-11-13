"""P04-OPEN-13 proposed Step 2/3 routes; application services own transactions."""

from datetime import date
from typing import Annotated, Literal
from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.api.finance import finance_actor, Key, Limit, Cursor, saved_response
from app.finance.domain import Actor
from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
from app.inventory.authorization import InventoryHouseholdAccess
from app.inventory.domain import InventoryRequestError
from app.inventory.dto import (
    Identifier,
    CategoryCreate,
    CategoryPatch,
    ProductCreate,
    ProductPatch,
    LotReceipt,
    LotMetadataPatch,
    EmptyCommand,
    ReasonCommand,
    ProductCategoryResponse,
    ProductResponse,
    LotResponse,
    MovementResponse,
    UnitPage,
    ConversionPage,
    CategoryPage,
    ProductPage,
    LotReadPage,
    LotReadResponse,
    MovementPage,
    AdjustmentCreate,
    AdjustmentResponse,
    ConsumptionCreate,
    DisposalCreate,
    ReturnCreate,
    StockCommandResponse,
    StockIntegrityReport,
    AdjustmentPage,
    ConsumptionPage,
    DisposalPage,
    LotValuationPage,
    LotValuationResponse,
)
from app.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
from app.inventory.service import InventoryService
from app.inventory.report_service import InventoryReportService


class InventoryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def inventory_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise InventoryRequestError(422, "INVENTORY_INVALID_INPUT") from None
            except HTTPException as exc:
                code = {
                    401: "INVENTORY_UNAUTHENTICATED",
                    403: "INVENTORY_FORBIDDEN",
                    404: "INVENTORY_NOT_FOUND",
                }.get(exc.status_code, "INVENTORY_REQUEST_FAILED")
                raise InventoryRequestError(exc.status_code, code) from None

        return inventory_handler


router = APIRouter(
    prefix="/api/v1/households/{household_id}",
    tags=["inventory"],
    route_class=InventoryRoute,
)


def get_inventory_service(session: Annotated[AsyncSession, Depends(get_db)]):
    return InventoryService(
        session,
        SqlAlchemyInventoryRepository(session),
        InventoryHouseholdAccess(SqlAlchemyHouseholdAccess(session)),
        SqlAlchemyFinanceRepository(session),
    )


Principal = Annotated[Actor, Depends(finance_actor)]
Service = Annotated[InventoryService, Depends(get_inventory_service)]


@router.get("/measurement-units", response_model=UnitPage)
async def units(
    household_id: Identifier,
    actor: Principal,
    service: Service,
    limit: Limit = 50,
    cursor: Cursor = None,
):
    return await service.page(actor, household_id, "measurement-units", limit, cursor)


@router.get("/unit-conversions", response_model=ConversionPage)
async def conversions(
    household_id: Identifier,
    actor: Principal,
    service: Service,
    limit: Limit = 50,
    cursor: Cursor = None,
):
    return await service.page(actor, household_id, "unit-conversions", limit, cursor)


@router.post(
    "/product-categories", response_model=ProductCategoryResponse, status_code=201
)
async def create_category(
    household_id: Identifier,
    body: CategoryCreate,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.create_reference(
            actor, household_id, "product-categories", body, key
        )
    )


@router.get("/product-categories", response_model=CategoryPage)
async def categories(
    household_id: Identifier,
    actor: Principal,
    service: Service,
    limit: Limit = 50,
    cursor: Cursor = None,
    archived: bool | None = None,
):
    return await service.page(
        actor, household_id, "product-categories", limit, cursor, archived=archived
    )


@router.get("/product-categories/{category_id}", response_model=ProductCategoryResponse)
async def category(
    household_id: Identifier,
    category_id: Identifier,
    actor: Principal,
    service: Service,
):
    return await service.get(actor, household_id, "product-categories", category_id)


@router.patch(
    "/product-categories/{category_id}", response_model=ProductCategoryResponse
)
async def patch_category(
    household_id: Identifier,
    category_id: Identifier,
    body: CategoryPatch,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.patch(
            actor, household_id, "product-categories", category_id, body, key
        )
    )


@router.post(
    "/product-categories/{category_id}/archive", response_model=ProductCategoryResponse
)
async def archive_category(
    household_id: Identifier,
    category_id: Identifier,
    body: EmptyCommand,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.archive(
            actor, household_id, "product-categories", category_id, body, key
        )
    )


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    household_id: Identifier,
    body: ProductCreate,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.create_reference(actor, household_id, "products", body, key)
    )


@router.get("/products", response_model=ProductPage)
async def products(
    household_id: Identifier,
    actor: Principal,
    service: Service,
    limit: Limit = 50,
    cursor: Cursor = None,
    category_id: Identifier | None = None,
    archived: bool | None = None,
):
    return await service.page(
        actor,
        household_id,
        "products",
        limit,
        cursor,
        category_id=category_id,
        archived=archived,
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def product(
    household_id: Identifier, product_id: Identifier, actor: Principal, service: Service
):
    return await service.get(actor, household_id, "products", product_id)


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def patch_product(
    household_id: Identifier,
    product_id: Identifier,
    body: ProductPatch,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.patch(actor, household_id, "products", product_id, body, key)
    )


@router.post("/products/{product_id}/archive", response_model=ProductResponse)
async def archive_product(
    household_id: Identifier,
    product_id: Identifier,
    body: EmptyCommand,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.archive(actor, household_id, "products", product_id, body, key)
    )


@router.post("/inventory-lots", response_model=LotResponse, status_code=201)
async def receive(
    household_id: Identifier,
    body: LotReceipt,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(await service.receive(actor, household_id, body, key))


@router.get("/inventory-lots", response_model=LotReadPage)
async def lots(
    household_id: Identifier,
    actor: Principal,
    service: Service,
    limit: Limit = 50,
    cursor: Cursor = None,
    product_id: Identifier | None = None,
    source_kind: Literal["PURCHASE", "GIFT", "MANUAL"] | None = None,
    expires_from: date | None = None,
    expires_to: date | None = None,
    archived: bool | None = None,
):
    return await service.page(
        actor,
        household_id,
        "inventory-lots",
        limit,
        cursor,
        product_id=product_id,
        source_kind=source_kind,
        expires_from=expires_from,
        expires_to=expires_to,
        archived=archived,
    )


@router.get("/inventory-lots/{lot_id}", response_model=LotReadResponse)
async def lot(
    household_id: Identifier, lot_id: Identifier, actor: Principal, service: Service
):
    return await service.get(actor, household_id, "inventory-lots", lot_id)


@router.patch("/inventory-lots/{lot_id}", response_model=LotResponse)
async def patch_lot(
    household_id: Identifier,
    lot_id: Identifier,
    body: LotMetadataPatch,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.patch(actor, household_id, "inventory-lots", lot_id, body, key)
    )


@router.post("/inventory-lots/{lot_id}/archive", response_model=LotResponse)
async def archive_lot(
    household_id: Identifier,
    lot_id: Identifier,
    body: ReasonCommand,
    key: Key,
    actor: Principal,
    service: Service,
):
    return saved_response(
        await service.archive(actor, household_id, "inventory-lots", lot_id, body, key)
    )


@router.get("/inventory-movements", response_model=MovementPage)
async def movements(
    household_id: Identifier,
    actor: Principal,
    service: Service,
    limit: Limit = 50,
    cursor: Cursor = None,
    lot_id: Identifier | None = None,
):
    return await service.page(
        actor, household_id, "inventory-movements", limit, cursor, lot_id=lot_id
    )


@router.get("/inventory-movements/{movement_id}", response_model=MovementResponse)
async def movement(
    household_id: Identifier,
    movement_id: Identifier,
    actor: Principal,
    service: Service,
):
    return await service.get(actor, household_id, "inventory-movements", movement_id)


# P04-OPEN-04/05/08/10/11/13 PROPOSAL commands; fixed identity permissions.
@router.post("/inventory-adjustments", response_model=AdjustmentResponse, status_code=201)
async def create_adjustment(
    household_id: Identifier, body: AdjustmentCreate, key: Key,
    actor: Principal, service: Service,
):
    return saved_response(await service.stock_command(
        actor, household_id, "inventory-adjustments", body, key
    ))


@router.get("/inventory-adjustments", response_model=AdjustmentPage)
async def adjustments(
    household_id: Identifier, actor: Principal, service: Service,
    limit: Limit = 50, cursor: Cursor = None, lot_id: Identifier | None = None,
):
    return await service.page(actor, household_id, "inventory-adjustments", limit, cursor, lot_id=lot_id)


@router.post("/consumption", response_model=StockCommandResponse, status_code=201)
async def create_consumption(
    household_id: Identifier, body: ConsumptionCreate, key: Key,
    actor: Principal, service: Service,
):
    return saved_response(await service.stock_command(
        actor, household_id, "consumption", body, key
    ))


@router.get("/consumption", response_model=ConsumptionPage)
async def consumption(
    household_id: Identifier, actor: Principal, service: Service,
    limit: Limit = 50, cursor: Cursor = None, lot_id: Identifier | None = None,
):
    return await service.page(actor, household_id, "consumption", limit, cursor, lot_id=lot_id)


@router.post("/disposals", response_model=StockCommandResponse, status_code=201)
async def create_disposal(
    household_id: Identifier, body: DisposalCreate, key: Key,
    actor: Principal, service: Service,
):
    return saved_response(await service.stock_command(
        actor, household_id, "disposals", body, key
    ))


@router.get("/disposals", response_model=DisposalPage)
async def disposals(
    household_id: Identifier, actor: Principal, service: Service,
    limit: Limit = 50, cursor: Cursor = None, lot_id: Identifier | None = None,
):
    return await service.page(actor, household_id, "disposals", limit, cursor, lot_id=lot_id)


@router.post("/inventory-lots/{lot_id}/returns", response_model=StockCommandResponse, status_code=201)
async def create_return(
    household_id: Identifier, lot_id: Identifier, body: ReturnCreate, key: Key,
    actor: Principal, service: Service,
):
    return saved_response(await service.stock_command(
        actor, household_id, "returns", body, key, lot_id=lot_id
    ))


@router.get("/inventory/integrity", response_model=StockIntegrityReport)
async def inventory_integrity(
    household_id: Identifier, actor: Principal, service: Service,
    product_id: Identifier | None = None, lot_id: Identifier | None = None,
):
    return await service.integrity(actor, household_id, product_id, lot_id)


# P06 Step 2 PROPOSAL: VIEW reads only; OPEN decisions remain open until closure.
def get_inventory_report_service(session: Annotated[AsyncSession, Depends(get_db)]):
    from app.inventory.infrastructure.report_repository import SqlAlchemyInventoryReportRepository

    return InventoryReportService(
        session, SqlAlchemyInventoryReportRepository(session),
        InventoryHouseholdAccess(SqlAlchemyHouseholdAccess(session)),
    )


ReportService = Annotated[InventoryReportService, Depends(get_inventory_report_service)]


@router.get("/inventory/valuation", response_model=LotValuationPage)
async def inventory_valuation(
    household_id: Identifier, actor: Principal, service: ReportService,
    product_id: Identifier | None = None, lot_id: Identifier | None = None,
    currency: Literal["VND", "JPY", "USD", "EUR", "BHD"] | None = None,
    archived: bool | None = None, limit: Limit = 50, cursor: Cursor = None,
):
    return await service.valuation(actor, household_id, product_id=product_id, lot_id=lot_id,
        currency=currency, archived=archived, limit=limit, cursor=cursor)


@router.get("/inventory/valuation/{lot_id}", response_model=LotValuationResponse)
async def lot_valuation(
    household_id: Identifier, lot_id: Identifier, actor: Principal, service: ReportService,
):
    return await service.valuation(actor, household_id, lot_id=lot_id, single=True)
