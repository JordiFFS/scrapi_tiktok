"""
Configuración común de las pruebas (pytest).

Por defecto NINGUNA prueba toca TikTok: los scrapers se reemplazan por versiones falsas
que devuelven datos con la misma forma que los reales. Así las pruebas son rápidas,
repetibles y no gastan el "cupo" de consultas antes de que TikTok empiece a limitar.

    pytest                 -> todo lo simulado (+ el modelo de embeddings local)
    pytest --tiktok        -> además, las pruebas reales contra TikTok (abre el navegador)
    pytest --hf            -> además, los modelos reales de Hugging Face del análisis (~1.6 GB)
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Permite "import main" y "import app..." al ejecutar pytest desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402
from app.controllers import analisis_controller, busqueda_controller, perfil_controller  # noqa: E402
from app.services import analisis, embeddings, ranking, tiktok_busqueda, tiktok_scraper  # noqa: E402
from app.services.cola_extracciones import cola  # noqa: E402
from app.utils.normalizadores import normalizar_video, normalizar_video_busqueda  # noqa: E402


# ---------- opción --tiktok ----------

def pytest_addoption(parser):
    parser.addoption("--tiktok", action="store_true", help="Ejecutar también las pruebas reales contra TikTok")
    parser.addoption("--hf", action="store_true", help="Ejecutar también los modelos reales de Hugging Face")


def pytest_collection_modifyitems(config, items):
    opcionales = {
        "tiktok": pytest.mark.skip(reason="Prueba real contra TikTok: usar `pytest --tiktok`"),
        "hf": pytest.mark.skip(reason="Modelos reales de Hugging Face: usar `pytest --hf`"),
    }
    for item in items:
        for marca, saltar in opcionales.items():
            if marca in item.keywords and not config.getoption(f"--{marca}"):
                item.add_marker(saltar)


# ---------- datos falsos con la forma real de TikTok ----------

def item_tiktok(i: int, autor: str | None = None, desc: str | None = None) -> dict:
    """Un video tal como llega en /api/post/item_list/ o /api/challenge/item_list/."""
    v = {
        "id": f"7000000000000000{i:03d}",
        "desc": desc or f"uñas acrílicas rosas {i} #uñas #fyp",
        "createTime": 1728584400,
        "video": {"cover": f"https://portada/{i}.jpg", "duration": 15},
        "music": {"title": "sonido original"},
        "stats": {"playCount": 1000 * (i + 1), "diggCount": 100 * i, "commentCount": i,
                  "shareCount": 1, "collectCount": 2},
        "textExtra": [{"hashtagName": "uñas"}, {"hashtagName": "fyp"}],
    }
    if autor:
        v["author"] = {"uniqueId": autor, "nickname": autor.title(), "verified": False}
        v["authorStats"] = {"followerCount": 500 + i}
    return v


class TikTokFalso:
    """Reemplazo de los scrapers. `demora` simula lo que tarda el navegador."""

    def __init__(self):
        self.demora = 0.0
        self.llamadas_perfil: list[str] = []
        self.llamadas_busqueda: list[list[str]] = []

    async def extraer_perfil(self, usuario, max_videos=10, con_comentarios=True, max_comentarios=20):
        self.llamadas_perfil.append(usuario)
        await asyncio.sleep(self.demora)
        if usuario == "noexiste":
            return {"usuario": usuario, "fecha_extraccion": "2026-10-16T00:00:00+00:00",
                    "perfil": None, "total_videos_extraidos": 0, "videos": []}
        if usuario == "explota":
            raise RuntimeError("navegador cerrado inesperadamente")
        if usuario == "lento":
            raise TimeoutError("La extracción superó 180 s")
        videos = [normalizar_video(item_tiktok(i), usuario) for i in range(min(3, max_videos))]
        if con_comentarios:
            videos[0]["comentarios"] = [{"id": "c1", "texto": "lindo", "fecha": None, "likes": 1,
                                         "respuestas": 0, "autor_anonimo": "abcdef123456"}][:max_comentarios]
        return {
            "usuario": usuario,
            "fecha_extraccion": "2026-10-16T00:00:00+00:00",
            "perfil": {"usuario": usuario, "nombre": "Prueba", "seguidores": 74,
                       "enlace_bio": None, "redes_en_biografia": {}},
            "total_videos_extraidos": len(videos),
            "videos": videos,
        }

    async def buscar_candidatos(self, hashtags, max_candidatos):
        self.llamadas_busqueda.append(hashtags)
        await asyncio.sleep(self.demora)
        if hashtags and hashtags[0] == "vacio":
            return [], []
        if hashtags and hashtags[0] == "explota":
            raise RuntimeError("timeout en la página del hashtag")
        if hashtags and hashtags[0] == "lento":
            raise TimeoutError("La extracción superó 180 s")
        videos = [normalizar_video_busqueda(item_tiktok(i, f"creador{i}")) for i in range(5)]
        videos.append(normalizar_video_busqueda(item_tiktok(9, "otro", desc="receta de pan casero #pan")))
        return videos[:max_candidatos], hashtags[:1]


def analisis_falso(datos: dict) -> dict:
    """Reemplazo de analisis.analizar_perfil: misma forma de respuesta, sin cargar modelos."""
    comentarios = [c for v in datos["videos"] for c in v["comentarios"]]
    big5 = dict.fromkeys(["apertura", "responsabilidad", "extraversion", "amabilidad", "neuroticismo"], 0.5)
    emociones = dict.fromkeys(["alegria", "tristeza", "enojo", "miedo", "sorpresa", "asco", "otros"], 0.0)
    return {
        "usuario": datos["usuario"], "fecha_analisis": "2026-10-16T00:00:00+00:00",
        "big5_creador": big5, "textos_analizados": len(datos["videos"]) + 1,
        "advertencia": "Solo hay pocos textos", "nota": analisis.NOTA,
        "comentarios": {"total_analizados": len(comentarios),
                        "sentimiento": {"positivo": 100.0, "neutral": 0.0, "negativo": 0.0},
                        "emociones": {**emociones, "alegria": 100.0}},
        "modelos": {"big5": "b", "traduccion": "t", "sentimiento": "s", "emociones": "e"},
    }


def similitudes_falsas(consulta: str, textos: list[str]) -> list[float]:
    """Similitud simple por palabras compartidas (sin cargar el modelo de 1 GB)."""
    q = set(consulta.split())
    return [0.5 + 0.4 * len(q & set(t.split())) / max(len(q), 1) for t in textos]


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
def estado_limpio():
    """Cada prueba empieza con cachés y cola vacías (son globales del proceso)."""
    perfil_controller._cache._datos.clear()
    busqueda_controller._cache._datos.clear()
    analisis_controller._cache._datos.clear()
    cola._extracciones.clear()
    cola._pendientes.clear()
    cola._hay_trabajo = asyncio.Event()  # el Event queda atado al loop anterior
    yield


@pytest.fixture
def tiktok_falso(monkeypatch) -> TikTokFalso:
    falso = TikTokFalso()
    monkeypatch.setattr(tiktok_scraper, "extraer_perfil", falso.extraer_perfil)
    monkeypatch.setattr(tiktok_busqueda, "buscar_candidatos", falso.buscar_candidatos)
    monkeypatch.setattr(ranking, "similitudes", similitudes_falsas)
    monkeypatch.setattr(analisis, "analizar_perfil", analisis_falso)
    return falso


@pytest.fixture
def cliente(tiktok_falso, monkeypatch):
    """Cliente HTTP de la API completa (con lifespan: arranca la cola), sin TikTok ni modelo."""
    monkeypatch.setattr(embeddings, "cargar_modelo", lambda: None)
    with TestClient(main.app) as c:
        yield c
