"""
Esquema de GET /api/analisis/{usuario} (contrato con la app móvil).

Big Five: cada rasgo va de 0 a 1 y es independiente de los demás (no suman 1).
Comentarios: solo porcentajes del conjunto (0-100), nunca datos por persona.
"""
from pydantic import BaseModel


class Big5(BaseModel):
    """Personalidad que proyecta el creador en sus textos (0 = bajo, 1 = alto)."""
    apertura: float
    responsabilidad: float
    extraversion: float
    amabilidad: float
    neuroticismo: float


class Sentimiento(BaseModel):
    """% de comentarios con cada sentimiento (suman ~100)."""
    positivo: float
    neutral: float
    negativo: float


class Emociones(BaseModel):
    """% de comentarios cuya emoción principal es cada una (suman ~100)."""
    alegria: float
    tristeza: float
    enojo: float
    miedo: float
    sorpresa: float
    asco: float
    otros: float


class AnalisisComentarios(BaseModel):
    """Resumen agregado de todos los comentarios extraídos."""
    total_analizados: int
    sentimiento: Sentimiento
    emociones: Emociones


class Modelos(BaseModel):
    """Modelos de Hugging Face usados (para citarlos en la app o en el informe)."""
    big5: str
    traduccion: str
    sentimiento: str
    emociones: str


class RespuestaAnalisis(BaseModel):
    """Respuesta completa de /api/analisis/{usuario}."""
    usuario: str
    desde_cache: bool
    fecha_analisis: str
    big5_creador: Big5 | None   # None si el creador no tiene ningún texto que analizar
    textos_analizados: int      # biografía + descripciones con contenido
    advertencia: str | None
    comentarios: AnalisisComentarios
    modelos: Modelos
    nota: str
