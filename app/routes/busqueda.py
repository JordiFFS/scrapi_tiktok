"""
GET /api/busqueda?q=uñas — los mejores videos sobre un tema.

Aquí solo se define la "cara" HTTP; la lógica está en app/controllers/busqueda_controller.py.
"""
from fastapi import APIRouter, Query

from app.controllers import busqueda_controller
from app.core import config
from app.schemas.busqueda import RespuestaBusqueda
from app.validations.busqueda import normalizar_consulta

router = APIRouter(prefix="/api", tags=["Búsqueda"])


@router.get(
    "/busqueda",
    response_model=RespuestaBusqueda,
    summary="Mejores videos sobre un tema",
    responses={
        400: {"description": "Búsqueda vacía, muy corta o muy larga"},
        404: {"description": "Ningún hashtag relacionado devolvió videos"},
        502: {"description": "Fallo durante la extracción"},
    },
)
async def buscar(
    q: str = Query(..., description='Tema a buscar, ej. "uñas acrílicas" (con o sin #)'),
    max_resultados: int = Query(
        config.BUSQUEDA_RESULTADOS_POR_DEFECTO, ge=1, le=config.BUSQUEDA_RESULTADOS_MAXIMO,
        description="Cantidad de videos a devolver",
    ),
    refrescar: bool = Query(False, description="Ignorar caché y volver a buscar"),
):
    """
    Busca en los hashtags públicos relacionados con `q` y ordena los videos por
    relevancia (embeddings locales), interacción y alcance. Cada resultado trae su
    "puntaje" para que la app pueda explicar el orden.
    """
    return await busqueda_controller.buscar(normalizar_consulta(q), max_resultados, refrescar)
