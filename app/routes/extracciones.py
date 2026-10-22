"""
Extracciones asíncronas: la forma recomendada de usar la API desde la app móvil.

    POST /api/extracciones        crea la extracción y responde AL INSTANTE con su id (202)
    GET  /api/extracciones/{id}   estado: pendiente -> en_proceso -> completada | error

Flujo en la app:
    1. POST con {"tipo": "perfil", "usuario": "..."}, {"tipo": "busqueda", "q": "..."}
       o {"tipo": "analisis", "usuario": "..."}
    2. Mostrar "cargando" y hacer GET cada `consultar_de_nuevo_en_seg` segundos
    3. Cuando estado = "completada", leer `resultado`; si es "error", mostrar `error.detalle`
"""
from fastapi import APIRouter, Body

from app.controllers import extracciones_controller
from app.schemas.extracciones import EstadoExtraccion, SolicitudExtraccion

router = APIRouter(prefix="/api/extracciones", tags=["Extracciones asíncronas"])


@router.post(
    "",
    response_model=EstadoExtraccion,
    status_code=202,
    summary="Crear una extracción (perfil, búsqueda o análisis) en segundo plano",
    responses={
        400: {"description": "Usuario o búsqueda inválidos"},
        429: {"description": "La cola está llena"},
    },
)
async def crear_extraccion(
    solicitud: SolicitudExtraccion = Body(
        openapi_examples={
            "perfil": {
                "summary": "Perfil",
                "value": {"tipo": "perfil", "usuario": "jordifiallos", "max_videos": 10, "max_comentarios": 20},
            },
            "busqueda": {
                "summary": "Búsqueda por tema",
                "value": {"tipo": "busqueda", "q": "uñas acrílicas", "max_resultados": 10},
            },
            "analisis": {
                "summary": "Análisis (Big Five + sentimiento)",
                "value": {"tipo": "analisis", "usuario": "jordifiallos", "max_videos": 10},
            },
        }
    ),
):
    """
    Responde de inmediato con el `id`. Si el dato ya estaba en caché, la extracción
    llega directamente como "completada". Si se envía una solicitud idéntica a una que
    sigue en curso, se devuelve la misma extracción (no se repite el trabajo).
    """
    return extracciones_controller.crear(solicitud)


@router.get(
    "/{id_extraccion}",
    response_model=EstadoExtraccion,
    summary="Consultar el estado (y resultado) de una extracción",
    responses={404: {"description": "No existe, venció (30 min) o la API se reinició"}},
)
async def consultar_extraccion(id_extraccion: str):
    """
    La app llama a este endpoint cada `consultar_de_nuevo_en_seg` segundos hasta que
    el estado sea "completada" (trae `resultado`) o "error" (trae `error`).
    """
    return extracciones_controller.consultar(id_extraccion)
