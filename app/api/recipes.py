"""P04-OPEN-06/09/13 PROPOSAL routes: definitions and stock-deducting cooking."""
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db
from app.api.finance import Key, Limit, Cursor, saved_response
from app.api.inventory import InventoryRoute, Principal, get_inventory_service
from app.inventory.dto import EmptyCommand, Identifier
from app.recipes.dto import (RecipeCreate, RecipePatch, RecipeResponse, RecipePage,
    IngredientCreate, IngredientPatch, IngredientResponse, CookingCreate, CookingResponse,
    CookingHistoryResponse, CookingHistoryPage)
from app.recipes.infrastructure.repositories import SqlAlchemyRecipeRepository
from app.recipes.service import RecipeService

router = APIRouter(prefix='/api/v1/households/{household_id}',tags=['recipes'],route_class=InventoryRoute)


def get_recipe_service(session: Annotated[AsyncSession, Depends(get_db)]):
    return RecipeService(get_inventory_service(session),SqlAlchemyRecipeRepository(session))


Service = Annotated[RecipeService, Depends(get_recipe_service)]


@router.post('/recipes',response_model=RecipeResponse,status_code=201)
async def create(household_id: Identifier,body: RecipeCreate,key: Key,actor: Principal,service: Service):
    return saved_response(await service.create(actor,household_id,body,key))


@router.get('/recipes',response_model=RecipePage)
async def recipes(household_id: Identifier,actor: Principal,service: Service,limit: Limit=50,cursor: Cursor=None,archived: bool | None=None):
    return await service.page(actor,household_id,'recipes',limit,cursor,archived=archived)


@router.get('/recipes/{recipe_id}',response_model=RecipeResponse)
async def detail(household_id: Identifier,recipe_id: Identifier,actor: Principal,service: Service):
    return await service.get(actor,household_id,'recipes',recipe_id)


@router.patch('/recipes/{recipe_id}',response_model=RecipeResponse)
async def patch(household_id: Identifier,recipe_id: Identifier,body: RecipePatch,key: Key,actor: Principal,service: Service):
    return saved_response(await service.mutate(actor,household_id,recipe_id,body,key))


@router.post('/recipes/{recipe_id}/ingredients',response_model=IngredientResponse,status_code=201)
async def add(household_id: Identifier,recipe_id: Identifier,body: IngredientCreate,key: Key,actor: Principal,service: Service):
    return saved_response(await service.mutate(actor,household_id,recipe_id,body,key,add=True))


@router.patch('/recipes/{recipe_id}/ingredients/{ingredient_id}',response_model=IngredientResponse)
async def ingredient(household_id: Identifier,recipe_id: Identifier,ingredient_id: Identifier,body: IngredientPatch,key: Key,actor: Principal,service: Service):
    return saved_response(await service.mutate(actor,household_id,recipe_id,body,key,ingredient_id=ingredient_id))


@router.post('/recipes/{recipe_id}/archive',response_model=RecipeResponse)
async def archive(household_id: Identifier,recipe_id: Identifier,body: EmptyCommand,key: Key,actor: Principal,service: Service):
    return saved_response(await service.mutate(actor,household_id,recipe_id,body,key,archive=True))


@router.post('/recipes/{recipe_id}/cook',response_model=CookingResponse,status_code=201)
async def cook(household_id: Identifier,recipe_id: Identifier,body: CookingCreate,key: Key,actor: Principal,service: Service):
    return saved_response(await service.cook(actor,household_id,recipe_id,body,key))


@router.get('/recipe-cooking-history',response_model=CookingHistoryPage)
async def history(household_id: Identifier,actor: Principal,service: Service,limit: Limit=50,cursor: Cursor=None):
    return await service.page(actor,household_id,'recipe-cooking-history',limit,cursor)


@router.get('/recipe-cooking-history/{history_id}',response_model=CookingHistoryResponse)
async def history_detail(household_id: Identifier,history_id: Identifier,actor: Principal,service: Service):
    return await service.get(actor,household_id,'recipe-cooking-history',history_id)
