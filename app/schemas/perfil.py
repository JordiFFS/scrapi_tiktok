"""
Esquemas (modelos Pydantic) de la respuesta de /api/perfil/{usuario}.

Son el "contrato" con la app móvil:
  - Aparecen en http://localhost:8000/docs, así la app sabe qué campos y tipos recibe.
  - FastAPI valida la salida contra ellos: si un cambio rompe la estructura, falla aquí
    y no en el celular.

Casi todo es opcional (None) porque TikTok no siempre envía todos los datos.
Si cambias un campo: actualiza este archivo, el normalizador y el ejemplo del README.
"""
from pydantic import BaseModel


class Comentario(BaseModel):
    """Comentario de primer nivel. El autor NUNCA se muestra: solo su hash (LOPDP)."""
    id: str | None = None
    texto: str | None = None
    fecha: str | None = None            # ISO 8601 UTC
    likes: int | None = None
    respuestas: int | None = None       # cantidad de respuestas (no se extraen)
    autor_anonimo: str | None = None    # hash SHA-256 de 12 caracteres


class Estadisticas(BaseModel):
    """Contadores públicos del video en el momento de la extracción."""
    vistas: int | None = None
    likes: int | None = None
    comentarios: int | None = None
    compartidos: int | None = None
    guardados: int | None = None


class Video(BaseModel):
    """Un post del perfil con sus estadísticas y comentarios."""
    id: str | None = None
    url: str
    descripcion: str | None = None
    fecha: str | None = None
    portada: str | None = None
    duracion_seg: int | None = None
    musica: str | None = None
    hashtags: list[str] = []
    estadisticas: Estadisticas
    comentarios: list[Comentario] = []


class Perfil(BaseModel):
    """Datos públicos de la cuenta."""
    usuario: str | None = None
    nombre: str | None = None
    biografia: str | None = None
    avatar: str | None = None
    verificado: bool | None = None
    privado: bool | None = None
    seguidores: int | None = None
    siguiendo: int | None = None
    likes_totales: int | None = None
    total_videos: int | None = None
    enlace_bio: str | None = None                 # web del perfil, si la cuenta la configuró
    redes_en_biografia: dict[str, str] = {}       # ej. {"instagram": "usuario"}; claves: instagram, youtube, x, facebook


class RespuestaPerfil(BaseModel):
    """Respuesta completa de GET /api/perfil/{usuario}."""
    desde_cache: bool                   # true si salió de la caché de 1 hora
    usuario: str                        # normalizado, sin "@"
    fecha_extraccion: str               # cuándo se extrajo (ISO 8601 UTC)
    perfil: Perfil
    total_videos_extraidos: int
    videos: list[Video]
