"""
GET /api/analisis/{usuario} — Big Five del creador y sentimiento agregado de sus comentarios.

Aquí solo se define la "cara" HTTP; la lógica está en app/controllers/analisis_controller.py
y los modelos en app/services/analisis.py.
"""
from fastapi import APIRouter, Query

from app.controllers import analisis_controller
from app.core import config
from app.schemas.analisis import RespuestaAnalisis
from app.validations.usuario import normalizar_usuario

router = APIRouter(prefix="/api", tags=["Análisis"])


@router.get(
    "/analisis/{usuario}",
    response_model=RespuestaAnalisis,
    summary="Big Five del creador y sentimiento de sus comentarios (modelos locales)",
    responses={
        400: {"description": "Usuario vacío"},
        404: {"description": "Perfil no encontrado, privado o bloqueado por TikTok"},
        502: {"description": "Fallo durante la extracción"},
        503: {"description": "No se pudieron cargar o ejecutar los modelos"},
    },
)
async def analizar_perfil(
    usuario: str,
    max_videos: int = Query(
        config.VIDEOS_POR_DEFECTO, ge=1, le=config.VIDEOS_MAXIMO,
        description="Cantidad de posts recientes (más posts = Big Five más confiable)",
    ),
    comentarios: bool = Query(True, description="Analizar también los comentarios"),
    max_comentarios: int = Query(
        config.COMENTARIOS_POR_DEFECTO, ge=0, le=config.COMENTARIOS_MAXIMO,
        description="Comentarios por post",
    ),
    refrescar: bool = Query(False, description="Ignorar cachés: volver a extraer y a analizar"),
):
    """
    Mismos parámetros que /api/perfil. Si ese perfil ya está en caché no se vuelve a abrir TikTok.

    La primera vez descarga los modelos (~1.6 GB) y tarda bastante; luego son ~5-15 s de CPU
    además de la extracción. Para la app es mejor usar POST /api/extracciones con tipo "analisis".
    """
    return await analisis_controller.analizar(
        normalizar_usuario(usuario), max_videos, comentarios, max_comentarios, refrescar
    )
