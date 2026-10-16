"""
GET /api/salud — comprueba que la API está encendida (útil para la app y para el túnel/dominio).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["Salud"])


@router.get("/salud", summary="Verifica que la API esté activa")
async def salud():
    return {"estado": "ok"}
