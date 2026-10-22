"""
Pruebas de app/services/ que no abren el navegador: caché, ranking, cola y embeddings.
"""
import asyncio
import time

import pytest
from fastapi import HTTPException

from app.core import config
from app.services import cache as modulo_cache
from app.services import embeddings, ranking
from app.services.cache import CacheMemoria
from app.services.cola_extracciones import ColaExtracciones
from app.services.navegador import correr_con_limite
from app.utils.normalizadores import normalizar_video_busqueda
from tests.conftest import item_tiktok, similitudes_falsas


# ---------- caché ----------

def test_cache_guarda_y_vence(monkeypatch):
    c = CacheMemoria(ttl_segundos=10)
    assert c.obtener("x") is None
    c.guardar("x", {"a": 1})
    assert c.obtener("x") == {"a": 1}
    ahora = time.time()
    monkeypatch.setattr(modulo_cache.time, "time", lambda: ahora + 11)
    assert c.obtener("x") is None


def test_cache_borra_las_vencidas_al_guardar(monkeypatch):
    c = CacheMemoria(ttl_segundos=10)
    c.guardar("vieja", {"a": 1})
    ahora = time.time()
    monkeypatch.setattr(modulo_cache.time, "time", lambda: ahora + 11)
    c.guardar("nueva", {"b": 2})
    assert list(c._datos) == ["nueva"]  # la vieja ya no ocupa memoria


# ---------- ranking ----------

def _video(vistas, likes=0, comentarios=0, compartidos=0, guardados=0):
    return {"estadisticas": {"vistas": vistas, "likes": likes, "comentarios": comentarios,
                             "compartidos": compartidos, "guardados": guardados}}


def test_puntuar_componentes_en_rango():
    p = ranking.puntuar(_video(1_000_000, likes=100_000), similitud=0.7)
    assert p["relevancia"] == 0.5                          # 0.7 está a la mitad de [0.5, 0.9]
    assert 0 <= p["interaccion"] <= 1 and 0 <= p["alcance"] <= 1
    esperado = (config.PESO_RELEVANCIA * p["relevancia"] + config.PESO_INTERACCION * p["interaccion"]
                + config.PESO_ALCANCE * p["alcance"])
    assert p["total"] == pytest.approx(esperado, abs=0.002)


def test_puntuar_extremos_y_nulos():
    p = ranking.puntuar(_video(None), similitud=0.1)        # TikTok no mandó estadísticas
    assert p == {"relevancia": 0.0, "interaccion": 0.0, "alcance": 0.0, "total": 0.0}
    p = ranking.puntuar(_video(10**9, likes=10**9), similitud=0.99)
    assert p["relevancia"] == 1.0 and p["interaccion"] == 1.0 and p["alcance"] == 1.0 and p["total"] == 1.0


def test_puntuar_suavizado_evita_videos_con_pocas_vistas():
    poco = ranking.puntuar(_video(10, likes=5), 0.7)["interaccion"]
    mucho = ranking.puntuar(_video(100_000, likes=15_000), 0.7)["interaccion"]
    assert poco < mucho


def test_ordenar_prefiere_lo_relevante(monkeypatch):
    monkeypatch.setattr(ranking, "similitudes", similitudes_falsas)
    videos = [normalizar_video_busqueda(item_tiktok(1, "a", desc="receta de pan")),
              normalizar_video_busqueda(item_tiktok(1, "b", desc="uñas acrílicas rosas"))]
    mejores = ranking.ordenar("uñas acrílicas", videos, 1)
    assert len(mejores) == 1 and mejores[0]["creador"]["usuario"] == "b"
    assert set(mejores[0]["puntaje"]) == {"relevancia", "interaccion", "alcance", "total"}


# ---------- embeddings (modelo local real, ~1 GB ya descargado) ----------

@pytest.mark.modelo
def test_embeddings_modelo_real():
    sims = embeddings.similitudes("uñas para boda", ["manicura de novia", "receta de pan casero"])
    assert len(sims) == 2 and sims[0] > sims[1]
    assert embeddings.similitudes("x", []) == []
    assert embeddings.cargar_modelo() is embeddings.cargar_modelo()   # se carga una sola vez


# ---------- cola de extracciones ----------

def _correr(coro):
    return asyncio.run(coro)


async def _esperar_estado(cola, id_, estados, max_seg=3):
    for _ in range(int(max_seg / 0.01)):
        if cola.obtener(id_).estado in estados:
            return cola.obtener(id_)
        await asyncio.sleep(0.01)
    raise AssertionError(f"la extracción quedó en {cola.obtener(id_).estado}")


def test_cola_ejecuta_en_orden_y_guarda_resultado():
    async def probar():
        cola, orden = ColaExtracciones(), []

        def tarea(n):
            async def t():
                orden.append(n)
                await asyncio.sleep(0.02)
                return {"n": n}
            return t

        cola.iniciar()
        a = cola.crear("perfil", {}, "a", tarea(1), None)
        b = cola.crear("perfil", {}, "b", tarea(2), None)
        assert a.estado == "pendiente" and cola.posicion(b.id) in (1, 2)
        fin = await _esperar_estado(cola, b.id, {"completada"})
        cola.detener()
        return orden, fin, cola.obtener(a.id)

    orden, b, a = _correr(probar())
    assert orden == [1, 2]
    assert a.resultado == {"n": 1} and b.resultado == {"n": 2}
    assert b.duracion_seg is not None and b.terminada and b.tarea is None


def test_cola_cache_nace_completada():
    cola = ColaExtracciones()
    ext = cola.crear("perfil", {}, "k", lambda: None, en_cache={"desde_cache": True})
    assert ext.estado == "completada" and ext.duracion_seg == 0.0 and cola.posicion(ext.id) is None


def test_cola_solicitud_duplicada_devuelve_misma():
    cola = ColaExtracciones()
    a = cola.crear("perfil", {}, "igual", lambda: None, None)
    b = cola.crear("perfil", {}, "igual", lambda: None, None)
    assert a.id == b.id and len(cola._pendientes) == 1


def test_cola_llena_da_429():
    cola = ColaExtracciones()
    for i in range(config.EXTRACCIONES_MAX_EN_COLA):
        cola.crear("perfil", {}, f"k{i}", lambda: None, None)
    with pytest.raises(HTTPException) as e:
        cola.crear("perfil", {}, "una_mas", lambda: None, None)
    assert e.value.status_code == 429


def test_cola_errores_no_detienen_al_trabajador():
    async def probar():
        cola = ColaExtracciones()

        async def http_404():
            raise HTTPException(status_code=404, detail="no existe")

        async def revienta():
            raise ValueError("algo raro")

        async def bien():
            return {"ok": True}

        cola.iniciar()
        e1 = cola.crear("perfil", {}, "1", http_404, None)
        e2 = cola.crear("perfil", {}, "2", revienta, None)
        e3 = cola.crear("perfil", {}, "3", bien, None)
        await _esperar_estado(cola, e3.id, {"completada"})
        cola.detener()
        return cola.obtener(e1.id), cola.obtener(e2.id), cola.obtener(e3.id)

    e1, e2, e3 = _correr(probar())
    assert e1.estado == "error" and e1.error == {"codigo": 404, "detalle": "no existe"}
    assert e2.estado == "error" and e2.error["codigo"] == 500 and "algo raro" in e2.error["detalle"]
    assert e3.estado == "completada"


def test_cola_borra_las_viejas_y_404(monkeypatch):
    cola = ColaExtracciones()
    ext = cola.crear("perfil", {}, "k", lambda: None, en_cache={"x": 1})
    ext._terminada_en = time.time() - config.EXTRACCIONES_TTL_SEGUNDOS - 1
    with pytest.raises(HTTPException) as e:
        cola.obtener(ext.id)
    assert e.value.status_code == 404


# ---------- tiempo máximo de la extracción ----------

class CrawlerTrabado:
    """Imita a Crawlee: run() se traga la cancelación y solo termina con stop() o al cerrar la página."""

    def __init__(self):
        self.detenido = asyncio.Event()

    async def run(self, solicitudes):
        while not self.detenido.is_set():
            try:
                await self.detenido.wait()
            except asyncio.CancelledError:
                pass  # como crawler.run(): ignora la cancelación

    def stop(self, motivo=""):
        self.detenido.set()


class PaginaFalsa:
    def __init__(self):
        self.cerrada = False

    async def close(self):
        self.cerrada = True


def test_correr_con_limite_detiene_un_crawler_trabado():
    crawler, pagina = CrawlerTrabado(), PaginaFalsa()
    inicio = time.perf_counter()
    with pytest.raises(TimeoutError):
        asyncio.run(correr_con_limite(crawler, [], {pagina}, segundos=0.2))
    assert time.perf_counter() - inicio < 2          # no esperó a que el crawler "terminara solo"
    assert crawler.detenido.is_set() and pagina.cerrada


def test_correr_con_limite_no_interfiere_si_termina_a_tiempo():
    class CrawlerRapido:
        async def run(self, solicitudes):
            await asyncio.sleep(0.01)

    asyncio.run(correr_con_limite(CrawlerRapido(), [], set(), segundos=5))
