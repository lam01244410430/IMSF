"""Finance routes. Application services authorize and own transactions."""
import json
import os
from datetime import datetime
from typing import Annotated, Literal

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import bearer, get_db, jwt_secret, require_active_user
from fastapi.security import HTTPAuthorizationCredentials
from app.identity.dto import UserResponse
from app.finance.domain import Actor, FinanceRequestError
from app.finance.dto import (
    AccountCreate, AccountPage, AccountResponse, CategoryCreate, CategoryPage,
    CategoryResponse, CurrencyResponse, Identifier, ItemCreate, ItemPatch,
    BalanceResponse, LedgerPage, PaymentBatchCreate, PaymentBatchResponse, TransactionPost,
    ReversalCreate, ReversalResponse,
    ItemResponse, TransactionDraftCreate, TransactionDraftPatch, TransactionPage, TransactionResponse,
)
from app.finance.infrastructure.household_access import SqlAlchemyHouseholdAccess
from app.finance.infrastructure.repositories import SqlAlchemyFinanceRepository
from app.finance.ledger_service import LedgerService


class FinanceRoute(APIRoute):
    """Finance error codes apply only to this router; identity stays unchanged."""
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def finance_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise FinanceRequestError(422, "FINANCE_INVALID_INPUT") from None
            except StarletteHTTPException as exc:
                code = {401: "FINANCE_UNAUTHENTICATED", 403: "FINANCE_FORBIDDEN",
                        404: "FINANCE_NOT_FOUND"}.get(exc.status_code, "FINANCE_REQUEST_FAILED")
                raise FinanceRequestError(exc.status_code, code) from None
        return finance_handler


router = APIRouter(prefix="/api/v1/households/{household_id}", tags=["finance"], route_class=FinanceRoute)
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[!-~]+$")]
Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[str | None, Query(max_length=2048)]


def finance_actor(
    user: Annotated[UserResponse, Depends(require_active_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> Actor:
    # current_user has already verified this Bearer. Carry its exact session ID
    # into the locked application check; household roles are NEVER JWT authority.
    try:
        claims = jwt.decode(credentials.credentials, jwt_secret(), algorithms=["HS256"],
                            issuer=os.environ["JWT_ISSUER"], audience=os.environ["JWT_AUDIENCE"])
    except jwt.InvalidTokenError:
        # JWT may expire while current_user awaits its database check.
        raise HTTPException(status_code=401) from None
    return Actor(user_id=user.id, session_id=claims["sid"])


def get_finance_service(session: Annotated[AsyncSession, Depends(get_db)]):
    return LedgerService(session, SqlAlchemyFinanceRepository(session), SqlAlchemyHouseholdAccess(session))


Principal = Annotated[Actor, Depends(finance_actor)]
Service = Annotated[LedgerService, Depends(get_finance_service)]


def saved_response(result):
    status, body = result
    if status == 204:
        return Response(status_code=204)
    # JSONB does not preserve object key order. Deterministic encoding makes the
    # first response and a durable replay byte-for-byte identical.
    return Response(status_code=status, media_type="application/json", content=json.dumps(
        body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))


@router.get("/currencies", response_model=list[CurrencyResponse])
async def currencies(household_id: Identifier, actor: Principal, service: Service):
    return await service.currencies(actor, household_id)


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(household_id: Identifier, body: AccountCreate, key: Key, actor: Principal, service: Service):
    return saved_response(await service.create_reference(actor, household_id, "accounts", body, key))


@router.get("/accounts", response_model=AccountPage)
async def accounts(household_id: Identifier, actor: Principal, service: Service,
                   limit: Limit = 50, cursor: Cursor = None, currency_code: str | None = None):
    return await service.page(actor, household_id, "accounts", limit, cursor, currency_code=currency_code)


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def account(household_id: Identifier, account_id: Identifier, actor: Principal, service: Service):
    return await service.get(actor, household_id, "accounts", account_id)


@router.post("/accounts/{account_id}/archive", status_code=204)
async def archive_account(household_id: Identifier, account_id: Identifier, key: Key, actor: Principal, service: Service):
    return saved_response(await service.archive(actor, household_id, "accounts", account_id, key))


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(household_id: Identifier, body: CategoryCreate, key: Key, actor: Principal, service: Service):
    return saved_response(await service.create_reference(actor, household_id, "categories", body, key))


@router.get("/categories", response_model=CategoryPage)
async def categories(household_id: Identifier, actor: Principal, service: Service,
                     limit: Limit = 50, cursor: Cursor = None, kind: Literal["INCOME", "EXPENSE"] | None = None):
    return await service.page(actor, household_id, "categories", limit, cursor, kind=kind)


@router.post("/categories/{category_id}/archive", status_code=204)
async def archive_category(household_id: Identifier, category_id: Identifier, key: Key, actor: Principal, service: Service):
    return saved_response(await service.archive(actor, household_id, "categories", category_id, key))


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
async def create_draft(household_id: Identifier, body: TransactionDraftCreate, key: Key, actor: Principal, service: Service):
    return saved_response(await service.create_draft(actor, household_id, body, key))


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def patch_draft(household_id: Identifier, transaction_id: Identifier, body: TransactionDraftPatch,
                      key: Key, actor: Principal, service: Service):
    return saved_response(await service.patch_draft(actor, household_id, transaction_id, body, key))


@router.post("/transactions/{transaction_id}/items", response_model=ItemResponse, status_code=201)
async def add_item(household_id: Identifier, transaction_id: Identifier, body: ItemCreate, key: Key, actor: Principal, service: Service):
    return saved_response(await service.item(actor, household_id, transaction_id, body, key))


@router.patch("/transactions/{transaction_id}/items/{item_id}", response_model=ItemResponse)
async def patch_item(household_id: Identifier, transaction_id: Identifier, item_id: Identifier,
                     body: ItemPatch, key: Key, actor: Principal, service: Service):
    return saved_response(await service.item(actor, household_id, transaction_id, body, key, item_id=item_id))


@router.get("/transactions", response_model=TransactionPage)
async def transactions(household_id: Identifier, actor: Principal, service: Service,
                       limit: Limit = 50, cursor: Cursor = None,
                       kind: Literal["INCOME", "EXPENSE", "TRANSFER", "OPENING"] | None = None,
                       status: Literal["DRAFT", "POSTED"] | None = None, currency_code: str | None = None):
    return await service.page(actor, household_id, "transactions", limit, cursor,
                              kind=kind, status=status, currency_code=currency_code)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def transaction(household_id: Identifier, transaction_id: Identifier, actor: Principal, service: Service):
    return await service.get(actor, household_id, "transactions", transaction_id)


@router.post("/transactions/{transaction_id}/post", response_model=TransactionResponse)
async def post_transaction(household_id: Identifier, transaction_id: Identifier, body: TransactionPost,
                           key: Key, actor: Principal, service: Service):
    return saved_response(await service.settle(actor, household_id, transaction_id, body, key, posting=True))


@router.post("/transactions/{transaction_id}/payments", response_model=PaymentBatchResponse, status_code=201)
async def add_payments(household_id: Identifier, transaction_id: Identifier, body: PaymentBatchCreate,
                       key: Key, actor: Principal, service: Service):
    return saved_response(await service.settle(actor, household_id, transaction_id, body, key, posting=False))


@router.get("/transactions/{transaction_id}/payments", response_model=PaymentBatchResponse)
async def transaction_payments(household_id: Identifier, transaction_id: Identifier, actor: Principal, service: Service):
    return await service.payments(actor, household_id, transaction_id)


@router.post("/transactions/{transaction_id}/reversals", response_model=ReversalResponse, status_code=201)
async def reverse_transaction(household_id: Identifier, transaction_id: Identifier, body: ReversalCreate,
                              key: Key, actor: Principal, service: Service):
    return saved_response(await service.reverse(actor, household_id, transaction_id, body, key))


@router.get("/ledger", response_model=LedgerPage)
async def ledger(household_id: Identifier, actor: Principal, service: Service,
                 account_id: Identifier | None = None, date_from: datetime | None = None,
                 date_to: datetime | None = None, limit: Limit = 50, cursor: Cursor = None):
    return await service.ledger(actor, household_id, account_id=account_id, date_from=date_from,
                                date_to=date_to, limit=limit, cursor=cursor)


@router.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
async def account_balance(household_id: Identifier, account_id: Identifier, actor: Principal, service: Service,
                          as_of: datetime | None = None, cursor: Cursor = None):
    return await service.balance(actor, household_id, account_id, as_of=as_of, cursor=cursor)
