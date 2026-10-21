"""
Esquemas de la respuesta de /api/busqueda (contrato con la app móvil).

Cada resultado es un Video normal (ver schemas/perfil.py) con dos campos extra:
"creador" (de quién es el video) y "puntaje" (por qué quedó en esa posición).
"""
from pydantic import BaseModel

from app.schemas.perfil import Video


class Creador(BaseModel):
    """Cuenta que publicó el video (autor público del contenido, sí se muestra)."""
    usuario: str | None = None
    nombre: str | None = None
    verificado: bool | None = None
    seguidores: int | None = None


class Puntaje(BaseModel):
    """Por qué el video quedó en esa posición (cada componente va de 0 a 1)."""
    relevancia: float     # 0-1: qué tan relacionado está con lo buscado (embeddings)
    interaccion: float    # 0-1: interacción del público respecto a las vistas
    alcance: float        # 0-1: cantidad de vistas (escala logarítmica)
    total: float          # suma ponderada; los resultados vienen ordenados por este valor


class VideoBusqueda(Video):
    """Un resultado de la búsqueda: un Video normal + su creador y su puntaje."""
    creador: Creador
    puntaje: Puntaje


class RespuestaBusqueda(BaseModel):
    """Respuesta completa de GET /api/busqueda."""
    desde_cache: bool
    consulta: str                   # búsqueda normalizada
    hashtags_usados: list[str]      # hashtags que aportaron videos (sin "#")
    fecha_extraccion: str           # ISO 8601 UTC
    total_candidatos: int           # videos evaluados antes de elegir los mejores
    total_resultados: int
    resultados: list[VideoBusqueda]
