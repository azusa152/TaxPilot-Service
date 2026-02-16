from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.algorithm_service import (
    activate_algorithm,
    get_algorithm,
    list_algorithms,
    register_algorithm,
)
from src.application.tax_service import calculate_tax
from src.domain.schemas import AlgorithmCreate, AlgorithmResponse, TaxCalculationResult
from src.infrastructure.database import get_db

router = APIRouter(tags=["Tax Calculations"])


# --- Tax Calculation ---


@router.post(
    "/tax/calculate/{user_id}/{year}",
    response_model=TaxCalculationResult,
    summary="Run full tax calculation for a user and year",
)
async def calculate(user_id: str, year: int, db: AsyncSession = Depends(get_db)):
    return await calculate_tax(db, user_id, year)


# --- Algorithm Registry ---


@router.get("/algorithms", response_model=list[AlgorithmResponse], summary="List all registered algorithms")
async def list_algos(db: AsyncSession = Depends(get_db)):
    return await list_algorithms(db)


@router.get(
    "/algorithms/{function_name}",
    response_model=AlgorithmResponse,
    summary="Get the active version of a specific algorithm",
)
async def get_algo(function_name: str, db: AsyncSession = Depends(get_db)):
    return await get_algorithm(db, function_name)


@router.post("/algorithms", response_model=AlgorithmResponse, status_code=201, summary="Register a new algorithm")
async def register_algo(data: AlgorithmCreate, db: AsyncSession = Depends(get_db)):
    return await register_algorithm(db, data.function_name, data.version, data.code_content, data.source_law_hash)


@router.put(
    "/algorithms/{algorithm_id}/activate",
    response_model=AlgorithmResponse,
    summary="Activate an algorithm version (archives previous active version)",
)
async def activate_algo(algorithm_id: int, db: AsyncSession = Depends(get_db)):
    return await activate_algorithm(db, algorithm_id)
