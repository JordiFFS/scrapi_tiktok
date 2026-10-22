"""
Pruebas de app/services/analisis.py.

Las normales reemplazan los modelos por falsos (rápidas, sin descargar nada) y comprueban
la lógica propia: limpieza, trozos, porcentajes, advertencias y que no salga nada por persona.
Las marcadas "hf" usan los modelos reales (`pytest --hf`).
"""
from types import SimpleNamespace

import pytest

from app.core import config
from app.services import analisis


# ---------- funciones puras ----------

def test_limpiar_texto():
    assert analisis.limpiar_texto("Nueva receta 🍝 @amiga #fyp #Cocina https://x.co/a") == "Nueva receta Cocina"
    assert analisis.limpiar_texto("🔥🔥 #viral") == ""
    assert analisis.limpiar_texto(None) == ""


def test_dividir_en_trozos_respeta_el_limite_y_no_corta_oraciones():
    contar = lambda t: len(t.split())  # noqa: E731  "tokens" = palabras
    assert analisis.dividir_en_trozos("Uno dos. Tres. Cuatro cinco seis.", contar, 3) == [
        "Uno dos. Tres.", "Cuatro cinco seis."
    ]
    # Una oración más larga que el límite se parte por palabras
    trozos = analisis.dividir_en_trozos("a b c d e f g.", contar, 3)
    assert trozos == ["a b c", "d e f", "g."]
    assert analisis.dividir_en_trozos("", contar, 3) == []


def test_porcentajes_incluye_todas_las_categorias():
    r = analisis.porcentajes(["POS", "POS", "NEG", "NEU"], analisis._SENTIMIENTOS)
    assert r == {"positivo": 50.0, "neutral": 25.0, "negativo": 25.0}
    assert analisis.porcentajes([], analisis._EMOCIONES) == dict.fromkeys(analisis._EMOCIONES.values(), 0.0)


# ---------- con modelos falsos ----------

@pytest.fixture
def modelos_falsos(monkeypatch):
    """Traducción identidad, Big Five constante y analizadores que etiquetan por palabras."""
    traducidos = []

    def traducir(texto):
        traducidos.append(texto)
        return texto

    monkeypatch.setattr(analisis, "_traducir", traducir)
    monkeypatch.setattr(analisis, "_puntuar_big5", lambda t: dict.fromkeys(analisis._RASGOS, 0.5))

    class Analizador:
        def __init__(self, tarea):
            self.tarea = tarea

        def predict(self, textos):
            if self.tarea == "sentiment":
                return [SimpleNamespace(output="NEG" if "feo" in t else "POS") for t in textos]
            return [SimpleNamespace(output="anger" if "feo" in t else "joy") for t in textos]

    monkeypatch.setattr(analisis, "_analizador", lambda tarea, modelo: Analizador(tarea))
    return traducidos


def test_big5_pocos_textos_da_advertencia(modelos_falsos):
    r = analisis.analizar_big5(["Me encanta viajar", "", "🔥", "Hoy cociné pasta #fyp"])
    assert r["textos_analizados"] == 2 and r["advertencia"]
    assert set(r["big5"]) == {"apertura", "responsabilidad", "extraversion", "amabilidad", "neuroticismo"}
    assert modelos_falsos == ["Me encanta viajar. Hoy cociné pasta."]  # unidos como oraciones


def test_big5_suficientes_textos_sin_advertencia(modelos_falsos):
    r = analisis.analizar_big5([f"texto número {i}" for i in range(config.ANALISIS_TEXTOS_MINIMOS)])
    assert r["advertencia"] is None


def test_big5_sin_textos(modelos_falsos):
    r = analisis.analizar_big5(["", "🔥🔥", "#fyp"])
    assert r["big5"] is None and r["textos_analizados"] == 0 and r["advertencia"]
    assert modelos_falsos == []  # ni siquiera se llama al traductor


def test_comentarios_solo_agregados(modelos_falsos):
    r = analisis.analizar_comentarios(["qué lindo", "qué feo", "me gusta", "  ", "genial"])
    assert r == {
        "total_analizados": 4,
        "sentimiento": {"positivo": 75.0, "neutral": 0.0, "negativo": 25.0},
        "emociones": {"alegria": 75.0, "tristeza": 0.0, "enojo": 25.0, "miedo": 0.0,
                      "sorpresa": 0.0, "asco": 0.0, "otros": 0.0},
    }


def test_analizar_perfil_usa_bio_descripciones_y_comentarios(modelos_falsos):
    datos = {
        "usuario": "prueba",
        "perfil": {"biografia": "Cocinera de Quito"},
        "videos": [
            {"descripcion": "Receta de pan", "comentarios": [{"texto": "qué lindo", "autor_anonimo": "a1"}]},
            {"descripcion": None, "comentarios": [{"texto": "qué feo", "autor_anonimo": "b2"}]},
        ],
    }
    r = analisis.analizar_perfil(datos)
    assert r["usuario"] == "prueba" and r["textos_analizados"] == 2
    assert r["comentarios"]["total_analizados"] == 2
    assert "a1" not in str(r) and "b2" not in str(r)  # nada que identifique a un comentarista
    assert r["nota"] == analisis.NOTA and r["modelos"]["big5"] == config.MODELO_BIG5


# ---------- modelos reales (pytest --hf) ----------

@pytest.mark.hf
def test_modelos_reales():
    big5 = analisis.analizar_big5(["Me encanta salir de fiesta y conocer gente nueva"] * 3)
    assert all(0 <= v <= 1 for v in big5["big5"].values()) and big5["advertencia"]
    com = analisis.analizar_comentarios(["me encantó este video", "qué horrible, no me gustó"])
    assert com["sentimiento"]["positivo"] == 50.0 and com["sentimiento"]["negativo"] == 50.0
