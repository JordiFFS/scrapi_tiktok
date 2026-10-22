"""
Controller de extracciones asíncronas.

Traduce una solicitud de la app (perfil, búsqueda o análisis) en una tarea para la cola
(services/cola_extracciones.py) y convierte el estado interno al formato de respuesta.

La tarea reutiliza los MISMOS controllers que los endpoints directos, así que caché,
validaciones, lock del navegador y errores se comportan igual en ambos caminos.
"""
from app.controllers import analisis_controller, busqueda_controller, perfil_controller
from app.core import config
from app.schemas.extracciones import SolicitudAnalisis, SolicitudBusqueda, SolicitudPerfil
from app.services.cola_extracciones import Extraccion, cola
from app.validations.busqueda import normalizar_consulta
from app.validations.usuario import normalizar_usuario


def crear(solicitud: SolicitudPerfil | SolicitudBusqueda | SolicitudAnalisis) -> dict:
    """Valida, arma la tarea y la registra en la cola. Devuelve el estado inicial."""
    if isinstance(solicitud, SolicitudPerfil | SolicitudAnalisis):
        usuario = normalizar_usuario(solicitud.usuario)
        p = {
            "usuario": usuario,
            "max_videos": solicitud.max_videos,
            "comentarios": solicitud.comentarios,
            "max_comentarios": solicitud.max_comentarios,
        }
        # Perfil y análisis reciben los mismos parámetros; solo cambia qué controller se usa
        es_analisis = isinstance(solicitud, SolicitudAnalisis)
        en_cache = None if solicitud.refrescar else (
            analisis_controller.desde_cache(**p) if es_analisis else perfil_controller.desde_cache(**p)
        )

        async def tarea() -> dict:
            """Extrae (y si es análisis, analiza) el perfil cuando le llegue el turno en la cola."""
            if es_analisis:
                return await analisis_controller.analizar(**p, refrescar=solicitud.refrescar)
            return await perfil_controller.obtener_perfil(**p, refrescar=solicitud.refrescar)

    else:
        consulta = normalizar_consulta(solicitud.q)
        p = {"consulta": consulta, "max_resultados": solicitud.max_resultados}
        en_cache = None if solicitud.refrescar else busqueda_controller.desde_cache(**p)

        async def tarea() -> dict:
            """Ejecuta la búsqueda cuando le llegue el turno en la cola."""
            return await busqueda_controller.buscar(**p, refrescar=solicitud.refrescar)

    # refrescar va en la clave: un "refrescar" no debe unirse a una tarea normal que respondería desde caché
    clave = f"{solicitud.tipo}|" + "|".join(str(v) for v in p.values()) + f"|{solicitud.refrescar}"
    return a_respuesta(cola.crear(solicitud.tipo, p, clave, tarea, en_cache))


def consultar(id_extraccion: str) -> dict:
    """Estado actual de una extracción (404 si no existe o venció)."""
    return a_respuesta(cola.obtener(id_extraccion))


def a_respuesta(ext: Extraccion) -> dict:
    """Convierte la extracción interna al formato de schemas/extracciones.py."""
    terminada = ext.estado in ("completada", "error")
    return {
        "id": ext.id,
        "tipo": ext.tipo,
        "estado": ext.estado,
        "parametros": ext.parametros,
        "posicion_en_cola": cola.posicion(ext.id),
        "consultar_de_nuevo_en_seg": None if terminada else config.EXTRACCIONES_SUGERENCIA_CONSULTA_SEG,
        "creada": ext.creada,
        "iniciada": ext.iniciada,
        "terminada": ext.terminada,
        "duracion_seg": ext.duracion_seg,
        "error": ext.error,
        "resultado": ext.resultado,
    }
