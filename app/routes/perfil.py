"""
GET /api/perfil/{usuario} — perfil, posts recientes, estadísticas y comentarios.

Aquí solo se define la "cara" HTTP: ruta, parámetros con sus límites y documentación.
La lógica está en app/controllers/perfil_controller.py.
"""
from fastapi import APIRouter, Query

from app.controllers import perfil_controller
from app.core import config
from app.schemas.perfil import RespuestaPerfil
from app.validations.usuario import normalizar_usuario

router = APIRouter(prefix="/api", tags=["Perfil"])


@router.get(
    "/perfil/{usuario}",
    response_model=RespuestaPerfil,
    summary="Datos públicos de un perfil de TikTok",
    responses={
        400: {"description": "Usuario vacío"},
        404: {"description": "Perfil no encontrado, privado o bloqueado por TikTok"},
        502: {"description": "Fallo durante la extracción"},
    },
)
async def obtener_perfil(
    usuario: str,
    max_videos: int = Query(
        config.VIDEOS_POR_DEFECTO, ge=1, le=config.VIDEOS_MAXIMO,
        description="Cantidad de posts recientes",
    ),
    comentarios: bool = Query(True, description="Incluir comentarios de cada post"),
    max_comentarios: int = Query(
        config.COMENTARIOS_POR_DEFECTO, ge=0, le=config.COMENTARIOS_MAXIMO,
        description="Comentarios por post",
    ),
    refrescar: bool = Query(False, description="Ignorar caché y volver a extraer"),
):
    """
    El usuario se puede escribir con o sin "@" y en cualquier mayúscula/minúscula.
    La primera consulta tarda (abre un navegador real); las siguientes salen de la caché.
    """
    return await perfil_controller.obtener_perfil(
        normalizar_usuario(usuario), max_videos, comentarios, max_comentarios, refrescar
    )
