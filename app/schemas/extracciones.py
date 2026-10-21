"""
Esquemas de /api/extracciones (contrato con la app móvil).

Solicitud (POST): un JSON con "tipo" que decide qué otros campos se esperan:

    {"tipo": "perfil",   "usuario": "jordifiallos", "max_videos": 10, "comentarios": true, "max_comentarios": 20}
    {"tipo": "busqueda", "q": "uñas acrílicas", "max_resultados": 10}

Respuesta (POST y GET): el estado de la extracción; "resultado" trae lo mismo que
/api/perfil o /api/busqueda cuando el estado es "completada".
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core import config
from app.schemas.busqueda import RespuestaBusqueda
from app.schemas.perfil import RespuestaPerfil


class SolicitudPerfil(BaseModel):
    """Cuerpo del POST para extraer un perfil (mismos parámetros que GET /api/perfil)."""
    tipo: Literal["perfil"]
    usuario: str = Field(description='Con o sin "@"')
    max_videos: int = Field(config.VIDEOS_POR_DEFECTO, ge=1, le=config.VIDEOS_MAXIMO)
    comentarios: bool = True
    max_comentarios: int = Field(config.COMENTARIOS_POR_DEFECTO, ge=0, le=config.COMENTARIOS_MAXIMO)
    refrescar: bool = False


class SolicitudBusqueda(BaseModel):
    """Cuerpo del POST para buscar por tema (mismos parámetros que GET /api/busqueda)."""
    tipo: Literal["busqueda"]
    q: str = Field(description='Tema a buscar, ej. "uñas acrílicas"')
    max_resultados: int = Field(
        config.BUSQUEDA_RESULTADOS_POR_DEFECTO, ge=1, le=config.BUSQUEDA_RESULTADOS_MAXIMO
    )
    refrescar: bool = False


# FastAPI elige el modelo correcto según el valor de "tipo"
SolicitudExtraccion = Annotated[SolicitudPerfil | SolicitudBusqueda, Field(discriminator="tipo")]


class ErrorExtraccion(BaseModel):
    """Error de una extracción que terminó mal."""
    codigo: int       # mismo código que daría el endpoint directo (400, 404, 502...)
    detalle: str


class EstadoExtraccion(BaseModel):
    """Estado de una extracción: lo devuelven el POST (202) y el GET /api/extracciones/{id}."""
    id: str
    tipo: Literal["perfil", "busqueda"]
    estado: Literal["pendiente", "en_proceso", "completada", "error"]
    parametros: dict                       # lo que se pidió, ya normalizado
    posicion_en_cola: int | None = None    # 1 = la siguiente; solo si está "pendiente"
    consultar_de_nuevo_en_seg: int | None = None  # sugerencia para la app mientras no termine
    creada: str
    iniciada: str | None = None
    terminada: str | None = None
    duracion_seg: float | None = None
    error: ErrorExtraccion | None = None
    resultado: RespuestaPerfil | RespuestaBusqueda | None = None
