"""
Cola de extracciones en segundo plano (en memoria).

La app ya no espera 15-30 s con la conexión abierta: crea una extracción, recibe un id
al instante y pregunta por su estado cada pocos segundos.

    crear()  -> guarda la extracción como "pendiente" y la pone en la cola
    trabajador (1 solo) -> la toma, la marca "en_proceso", la ejecuta y guarda resultado o error
    obtener() -> devuelve el estado actual (con posición en la cola si sigue pendiente)

Un ÚNICO trabajador procesa en orden de llegada: así nunca hay dos navegadores abiertos
(regla de bajo volumen) y la app puede mostrar "estás en la posición N".

Este módulo no sabe de TikTok: recibe una función async a ejecutar. Qué ejecutar lo decide
app/controllers/extracciones_controller.py. Las extracciones se pierden al reiniciar la API.
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from fastapi import HTTPException

from app.core import config
from app.utils.formato import ahora_iso

log = logging.getLogger("tiktok_api")

Tarea = Callable[[], Awaitable[dict]]


@dataclass
class Extraccion:
    """Una extracción y todo lo que la app puede consultar sobre ella."""
    id: str
    tipo: str                      # "perfil" | "busqueda"
    parametros: dict               # lo que pidió la app (ya normalizado)
    clave: str                     # identifica solicitudes iguales (para no repetirlas)
    tarea: Tarea | None            # qué ejecutar; None si ya nació completada (caché)
    estado: str = "pendiente"      # pendiente -> en_proceso -> completada | error
    creada: str = field(default_factory=ahora_iso)
    iniciada: str | None = None
    terminada: str | None = None
    duracion_seg: float | None = None
    resultado: dict | None = None
    error: dict | None = None      # {"codigo": 404, "detalle": "..."}
    _terminada_en: float | None = None  # time.time() al terminar (para limpiar las viejas)


class ColaExtracciones:
    """Guarda las extracciones (por id), la fila de pendientes y el trabajador que las ejecuta."""
    def __init__(self):
        """Cola vacía; el trabajador se arranca después con iniciar()."""
        self._extracciones: dict[str, Extraccion] = {}
        self._pendientes: list[str] = []          # ids en orden de llegada
        self._hay_trabajo = asyncio.Event()
        self._trabajador: asyncio.Task | None = None

    # ---------- ciclo de vida (lo llama main.py) ----------

    def iniciar(self) -> None:
        """Arranca el trabajador en segundo plano."""
        self._trabajador = asyncio.create_task(self._trabajar())

    def detener(self) -> None:
        """Detiene el trabajador al apagar la API (lo pendiente se pierde)."""
        if self._trabajador:
            self._trabajador.cancel()

    # ---------- operaciones ----------

    def crear(self, tipo: str, parametros: dict, clave: str, tarea: Tarea, en_cache: dict | None) -> Extraccion:
        """
        Registra una extracción y devuelve su estado inicial.

        - Si `en_cache` trae datos, nace "completada" (no entra a la cola).
        - Si ya hay una igual pendiente o en proceso, devuelve ESA (evita trabajo doble).
        - Si la cola está llena, lanza 429.
        """
        self._limpiar_viejas()

        if en_cache is not None:
            ext = Extraccion(self._nuevo_id(), tipo, parametros, clave, None, estado="completada")
            ext.iniciada = ext.terminada = ext.creada
            ext.duracion_seg, ext.resultado, ext._terminada_en = 0.0, en_cache, time.time()
            self._extracciones[ext.id] = ext
            return ext

        for ext in self._extracciones.values():
            if ext.clave == clave and ext.estado in ("pendiente", "en_proceso"):
                return ext

        if len(self._pendientes) >= config.EXTRACCIONES_MAX_EN_COLA:
            raise HTTPException(
                status_code=429,
                detail=f"Hay {len(self._pendientes)} extracciones en cola. Intenta en unos minutos.",
            )

        ext = Extraccion(self._nuevo_id(), tipo, parametros, clave, tarea)
        self._extracciones[ext.id] = ext
        self._pendientes.append(ext.id)
        self._hay_trabajo.set()
        return ext

    def obtener(self, id_extraccion: str) -> Extraccion:
        """Devuelve la extracción o lanza 404 si no existe (o ya venció)."""
        self._limpiar_viejas()
        ext = self._extracciones.get(id_extraccion)
        if not ext:
            raise HTTPException(
                status_code=404,
                detail="Extracción no encontrada: el id no existe, venció o la API se reinició.",
            )
        return ext

    def posicion(self, id_extraccion: str) -> int | None:
        """1 = es la siguiente en ejecutarse. None si no está pendiente."""
        try:
            return self._pendientes.index(id_extraccion) + 1
        except ValueError:
            return None

    # ---------- internos ----------

    async def _trabajar(self) -> None:
        """Bucle del trabajador: toma la extracción más antigua y la ejecuta, una a la vez."""
        while True:
            if not self._pendientes:
                self._hay_trabajo.clear()
                await self._hay_trabajo.wait()
                continue
            ext = self._extracciones.get(self._pendientes.pop(0))
            if ext is None:
                continue
            await self._ejecutar(ext)

    async def _ejecutar(self, ext: Extraccion) -> None:
        """Ejecuta una extracción y guarda el resultado o el error (nunca deja caer al trabajador)."""
        ext.estado, ext.iniciada = "en_proceso", ahora_iso()
        inicio = time.perf_counter()
        log.info("[extracción %s] inicia %s %s", ext.id, ext.tipo, ext.parametros)
        try:
            ext.resultado = await ext.tarea()
            ext.estado = "completada"
        except HTTPException as e:  # errores "esperados" de los controllers (404, 502...)
            ext.estado, ext.error = "error", {"codigo": e.status_code, "detalle": e.detail}
        except Exception as e:  # cualquier otra falla: se informa, el trabajador sigue
            log.exception("[extracción %s] falló", ext.id)
            ext.estado, ext.error = "error", {"codigo": 500, "detalle": f"Error inesperado: {e}"}
        ext.terminada, ext._terminada_en = ahora_iso(), time.time()
        ext.duracion_seg = round(time.perf_counter() - inicio, 1)
        ext.tarea = None  # liberar la referencia
        log.info("[extracción %s] %s en %.1fs", ext.id, ext.estado, ext.duracion_seg)

    def _limpiar_viejas(self) -> None:
        """Borra las extracciones terminadas hace más de EXTRACCIONES_TTL_SEGUNDOS."""
        limite = time.time() - config.EXTRACCIONES_TTL_SEGUNDOS
        for id_ in [i for i, e in self._extracciones.items() if e._terminada_en and e._terminada_en < limite]:
            del self._extracciones[id_]

    @staticmethod
    def _nuevo_id() -> str:
        """Id corto y aleatorio (12 caracteres hex) para que la app consulte la extracción."""
        return uuid.uuid4().hex[:12]


# Instancia única que comparten el controller y main.py
cola = ColaExtracciones()
