"""
Análisis con modelos de Hugging Face, ejecutados EN LA PC con transformers (sin token ni APIs).

Este archivo no sabe nada de FastAPI ni de TikTok: recibe textos (o la respuesta del scraper)
y devuelve diccionarios. Así se puede estudiar y probar por separado:

    from app.services import analisis
    analisis.analizar_big5(["Me encanta viajar", "Hoy cociné pasta"])
    analisis.analizar_comentarios(["qué lindo", "no me gustó"])

Hace dos análisis distintos:

  1. Big Five del CREADOR (`analizar_big5`): con la biografía y las descripciones de SUS videos.
     El modelo de personalidad solo entiende inglés, así que primero se traduce es -> en.
  2. Sentimiento y emociones de los COMENTARIOS (`analizar_comentarios`), solo como porcentajes
     del conjunto. Nunca se analiza ni se devuelve nada por persona (LOPDP: los comentaristas
     no son el sujeto del análisis).

Los modelos pesan ~1.6 GB en total: se cargan una sola vez, la primera vez que se usan
(carga perezosa), y quedan en memoria para las siguientes peticiones.

Todas las funciones públicas son BLOQUEANTES (usan CPU varios segundos): desde código async
llamarlas con asyncio.to_thread (ver app/controllers/analisis_controller.py).
"""
import logging
import re
import threading
from collections import Counter
from typing import Callable

from app.core import config
from app.utils.formato import ahora_iso
from app.utils.texto import HASHTAGS_GENERICOS

log = logging.getLogger("tiktok_api")

# Orden REAL de las 5 salidas de Minej/bert-base-personality. Su config.json solo dice
# LABEL_0..LABEL_4; el orden está en la ficha del modelo (model card) en Hugging Face.
_ORDEN_BIG5 = ["extraversion", "neuroticismo", "amabilidad", "responsabilidad", "apertura"]
# Orden en que se devuelven (el habitual en español: modelo OCEAN)
_RASGOS = ["apertura", "responsabilidad", "extraversion", "amabilidad", "neuroticismo"]

# Etiquetas de pysentimiento -> nombres en español de la respuesta
_SENTIMIENTOS = {"POS": "positivo", "NEU": "neutral", "NEG": "negativo"}
_EMOCIONES = {
    "joy": "alegria", "sadness": "tristeza", "anger": "enojo", "fear": "miedo",
    "surprise": "sorpresa", "disgust": "asco", "others": "otros",
}

NOTA = "Análisis exploratorio: personalidad proyectada en el contenido, no un diagnóstico."


# ======================================================================
# 1. Carga perezosa de modelos
# ======================================================================

_modelos: dict[str, object] = {}
_lock_carga = threading.Lock()  # si llegan dos peticiones juntas, el modelo se carga una sola vez


def _modelo(nombre: str, crear: Callable[[], object]) -> object:
    """
    Devuelve el modelo `nombre`; la primera vez lo crea con `crear()` (descarga + carga en RAM).

    Es la "carga perezosa": la API arranca rápido y solo paga el costo cuando alguien
    pide un análisis por primera vez.
    """
    with _lock_carga:
        if nombre not in _modelos:
            # Sin barras de progreso ("Loading weights", "Map") en la consola de la API
            from datasets.utils.logging import disable_progress_bar
            from transformers.utils import logging as logging_hf
            disable_progress_bar()
            logging_hf.disable_progress_bar()
            log.info("Cargando modelo %s ...", nombre)
            _modelos[nombre] = crear()
            log.info("Modelo %s listo", nombre)
    return _modelos[nombre]


def _traductor():
    """Tokenizer + modelo Marian (opus-mt) para traducir español -> inglés."""
    def crear():
        """Descarga/carga el traductor en modo evaluación (sin entrenamiento)."""
        from transformers import MarianMTModel, MarianTokenizer
        tokenizer = MarianTokenizer.from_pretrained(config.MODELO_TRADUCCION)
        return tokenizer, MarianMTModel.from_pretrained(config.MODELO_TRADUCCION).eval()
    return _modelo(config.MODELO_TRADUCCION, crear)


def _big5():
    """Tokenizer + modelo BERT de personalidad (5 salidas, una por rasgo)."""
    def crear():
        """Descarga/carga el clasificador Big Five en modo evaluación."""
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(config.MODELO_BIG5)
        return tokenizer, AutoModelForSequenceClassification.from_pretrained(config.MODELO_BIG5).eval()
    return _modelo(config.MODELO_BIG5, crear)


def _analizador(tarea: str, modelo: str):
    """Analizador de pysentimiento ("sentiment" o "emotion") para español."""
    def crear():
        """Crea el analizador; pysentimiento descarga el modelo robertuito correspondiente."""
        from pysentimiento import create_analyzer
        return create_analyzer(task=tarea, lang="es", model_name=modelo)
    return _modelo(modelo, crear)


# ======================================================================
# 2. Preparación de textos (funciones puras, fáciles de probar)
# ======================================================================

def limpiar_texto(texto: str | None) -> str:
    """
    Deja solo lo que "dice" la persona, para que el modelo no se confunda:

        "Nueva receta 🍝 @amiga #fyp #cocina https://x.co"  ->  "Nueva receta cocina"

    - URLs y menciones (@usuario) se quitan: no son contenido y las menciones son terceros.
    - De los hashtags se quita el "#" y se conserva la palabra (suele describir el tema),
      salvo los genéricos (#fyp, #viral...) que no dicen nada del creador.
    - Emojis y símbolos se quitan (el traductor los convierte en ruido).
    """
    texto = re.sub(r"https?://\S+|www\.\S+", " ", texto or "")
    texto = re.sub(r"@\w[\w.]*", " ", texto)
    texto = re.sub(
        r"#(\w+)", lambda m: " " if m.group(1).lower() in HASHTAGS_GENERICOS else f" {m.group(1)}", texto
    )
    texto = re.sub(r"[^\w\s.,;:!?¿¡'\"()-]", " ", texto)  # fuera emojis y símbolos
    return re.sub(r"\s+", " ", texto).strip()


def dividir_en_trozos(texto: str, contar_tokens: Callable[[str], int], max_tokens: int) -> list[str]:
    """
    Parte `texto` en trozos de como máximo `max_tokens` tokens, sin cortar oraciones.

    Los modelos tipo BERT/Marian aceptan 512 tokens; si se les pasa más, ignoran el resto
    (lo truncan). Por eso se agrupan oraciones enteras hasta llenar cada trozo. Una oración
    que sola ya es demasiado larga se parte por palabras.

    `contar_tokens` es una función (normalmente el tokenizer del modelo) para que esta lógica
    no dependa de un modelo concreto y se pueda probar con algo simple como len(t.split()).
    """
    oraciones = [o for o in re.split(r"(?<=[.!?])\s+", texto) if o.strip()]
    trozos: list[str] = []
    actual = ""
    for oracion in oraciones:
        candidato = f"{actual} {oracion}".strip()
        if contar_tokens(candidato) <= max_tokens:
            actual = candidato
            continue
        if actual:
            trozos.append(actual)
        if contar_tokens(oracion) <= max_tokens:
            actual = oracion
            continue
        # Oración demasiado larga: se reparte palabra por palabra
        actual = ""
        for palabra in oracion.split():
            candidato = f"{actual} {palabra}".strip()
            if actual and contar_tokens(candidato) > max_tokens:
                trozos.append(actual)
                actual = palabra
            else:
                actual = candidato
    if actual:
        trozos.append(actual)
    return trozos


def porcentajes(etiquetas: list[str], nombres: dict[str, str]) -> dict[str, float]:
    """
    Convierte una lista de etiquetas en porcentajes (0-100, 1 decimal) con nombres en español.

        porcentajes(["POS", "POS", "NEG", "NEU"], _SENTIMIENTOS)
        -> {"positivo": 50.0, "neutral": 25.0, "negativo": 25.0}

    Todas las categorías aparecen aunque tengan 0, para que la app siempre reciba las mismas claves.
    """
    conteo = Counter(etiquetas)
    total = len(etiquetas)
    return {
        nombre: round(100 * conteo[etiqueta] / total, 1) if total else 0.0
        for etiqueta, nombre in nombres.items()
    }


# ======================================================================
# 3. Big Five del creador
# ======================================================================

def _traducir(texto: str) -> str:
    """
    Traduce un texto largo de español a inglés, por trozos.

    Cada trozo respeta el límite de tokens del traductor; los trozos se traducen en lotes
    (varios a la vez es más rápido que uno por uno) y al final se vuelven a unir.
    """
    import torch

    tokenizer, modelo = _traductor()
    trozos = dividir_en_trozos(
        texto, lambda t: len(tokenizer(t)["input_ids"]), config.ANALISIS_TOKENS_TRADUCCION
    )
    traducidos: list[str] = []
    for i in range(0, len(trozos), config.ANALISIS_LOTE_TRADUCCION):
        lote = trozos[i : i + config.ANALISIS_LOTE_TRADUCCION]
        entrada = tokenizer(lote, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():  # solo inferencia: no se calculan gradientes (menos RAM, más rápido)
            salida = modelo.generate(**entrada)
        traducidos += tokenizer.batch_decode(salida, skip_special_tokens=True)
    return " ".join(traducidos)


def _puntuar_big5(texto_en: str) -> dict[str, float]:
    """
    Aplica el modelo de personalidad a un texto en inglés y devuelve los 5 rasgos (0 a 1).

    Detalles importantes del modelo (revisados en su ficha y probados):
      - Tiene 5 salidas INDEPENDIENTES, una por rasgo. Una persona puede ser a la vez muy
        extravertida y muy amable, así que NO se usa softmax (que obligaría a que sumen 1
        y los haría competir entre sí).
      - La ficha dice que la salida va de 0 a 1, pero en la práctica los logits salen
        negativos o mayores que 1 (ej. -0.75). Por eso a CADA rasgo se le aplica la función
        sigmoide por separado: 1 / (1 + e^-x) lo lleva a 0-1 sin mezclarlo con los demás.
      - Si el texto supera 512 tokens se parte en trozos y se promedia el resultado de cada
        trozo, ponderado por cuántos tokens tiene (un trozo largo pesa más que uno corto).
    """
    import torch

    tokenizer, modelo = _big5()
    trozos = dividir_en_trozos(
        texto_en, lambda t: len(tokenizer(t)["input_ids"]), config.ANALISIS_TOKENS_BIG5
    )
    suma = torch.zeros(len(_ORDEN_BIG5))
    total_tokens = 0
    for trozo in trozos:
        entrada = tokenizer(trozo, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = modelo(**entrada).logits.squeeze(0)  # 5 números, en el orden de _ORDEN_BIG5
        tokens = entrada["input_ids"].shape[1]
        suma += torch.sigmoid(logits) * tokens  # sigmoide rasgo por rasgo (no softmax)
        total_tokens += tokens
    promedio = (suma / max(total_tokens, 1)).tolist()
    valores = dict(zip(_ORDEN_BIG5, promedio))
    return {rasgo: round(valores[rasgo], 3) for rasgo in _RASGOS}


def analizar_big5(textos: list[str]) -> dict:
    """
    Estima el Big Five que PROYECTA el creador en sus textos públicos.

    Pasos:
      1. Limpia cada texto (sin URLs, menciones ni emojis) y descarta los que quedan vacíos.
      2. Los une en un solo texto (biografía + descripciones de los videos).
      3. Lo traduce de español a inglés por trozos (el modelo de personalidad es solo inglés).
      4. Aplica el modelo y convierte cada rasgo a 0-1 con sigmoide.

    Devuelve {"big5": {apertura, responsabilidad, extraversion, amabilidad, neuroticismo} | None,
              "textos_analizados": n, "advertencia": str | None}.
    Con menos de ANALISIS_TEXTOS_MINIMOS textos igual se analiza, pero con advertencia;
    sin ningún texto útil no hay nada que analizar y "big5" es None.
    """
    limpios = [t for t in (limpiar_texto(x) for x in textos) if t]
    if not limpios:
        return {
            "big5": None,
            "textos_analizados": 0,
            "advertencia": "El creador no tiene biografía ni descripciones con texto: no se pudo estimar el Big Five.",
        }

    # Cada texto termina en punto para que, al unirlos, sigan siendo oraciones separadas
    unido = " ".join(t if t[-1] in ".!?" else f"{t}." for t in limpios)
    texto_en = _traducir(unido)
    advertencia = None
    if len(limpios) < config.ANALISIS_TEXTOS_MINIMOS:
        advertencia = (
            f"Solo hay {len(limpios)} textos con contenido (se recomiendan al menos "
            f"{config.ANALISIS_TEXTOS_MINIMOS}): el resultado es poco confiable."
        )
    return {"big5": _puntuar_big5(texto_en), "textos_analizados": len(limpios), "advertencia": advertencia}


# ======================================================================
# 4. Sentimiento y emociones de los comentarios (solo agregados)
# ======================================================================

def analizar_comentarios(comentarios: list[str]) -> dict:
    """
    Sentimiento (positivo/neutral/negativo) y emociones del CONJUNTO de comentarios.

    Usa pysentimiento (modelos robertuito, entrenados con tuits en español: entienden
    jerga, emojis y faltas de ortografía mejor que un modelo traducido). pysentimiento hace
    su propio preprocesamiento (emojis -> texto, usuarios -> "@usuario"), así que aquí no
    se limpian los comentarios.

    Cada comentario recibe UNA etiqueta (la más probable) y se cuentan: el resultado son
    solo porcentajes del total. Las etiquetas individuales se descartan al terminar; nunca
    se devuelve qué comentario (ni qué persona) tuvo qué sentimiento.
    """
    textos = [c.strip() for c in comentarios if c and c.strip()]
    if not textos:
        return {
            "total_analizados": 0,
            "sentimiento": porcentajes([], _SENTIMIENTOS),
            "emociones": porcentajes([], _EMOCIONES),
        }
    sentimiento = _analizador("sentiment", config.MODELO_SENTIMIENTO).predict(textos)
    emociones = _analizador("emotion", config.MODELO_EMOCIONES).predict(textos)
    return {
        "total_analizados": len(textos),
        "sentimiento": porcentajes([r.output for r in sentimiento], _SENTIMIENTOS),
        "emociones": porcentajes([r.output for r in emociones], _EMOCIONES),
    }


# ======================================================================
# 5. Todo junto, a partir de la respuesta del scraper
# ======================================================================

def analizar_perfil(datos: dict) -> dict:
    """
    Recibe la respuesta de /api/perfil (perfil + videos + comentarios) y arma el análisis.

    - Textos del CREADOR: su biografía y la descripción de cada uno de sus videos.
    - Textos de los COMENTARIOS: todos los comentarios de todos los videos, mezclados
      (solo se usa el texto; el autor_anonimo ni siquiera se lee).
    """
    perfil = datos.get("perfil") or {}
    videos = datos.get("videos") or []
    textos_creador = [perfil.get("biografia") or ""] + [v.get("descripcion") or "" for v in videos]
    textos_comentarios = [c.get("texto") or "" for v in videos for c in v.get("comentarios") or []]

    big5 = analizar_big5(textos_creador)
    return {
        "usuario": datos.get("usuario"),
        "fecha_analisis": ahora_iso(),
        "big5_creador": big5["big5"],
        "textos_analizados": big5["textos_analizados"],
        "advertencia": big5["advertencia"],
        "comentarios": analizar_comentarios(textos_comentarios),
        "modelos": {
            "big5": config.MODELO_BIG5,
            "traduccion": config.MODELO_TRADUCCION,
            "sentimiento": config.MODELO_SENTIMIENTO,
            "emociones": config.MODELO_EMOCIONES,
        },
        "nota": NOTA,
    }
