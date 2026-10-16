"""
Configuración central del proyecto.

Todo valor "ajustable" vive aquí para no tener números mágicos repartidos por el código.
Los que dependen del entorno se leen de variables de entorno, por ejemplo:

    env HEADLESS=true python main.py
"""
import os

# --- Servidor ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# --- Navegador ---
# TikTok suele bloquear el modo headless; déjalo en false mientras desarrollas.
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

# No descargar imágenes, videos ni fuentes: los datos llegan por JSON, así las páginas cargan más rápido.
# Activar con BLOQUEAR_RECURSOS=true. Apagado por defecto hasta confirmar que no provoca bloqueos
# en las páginas de video (ERR_HTTP_RESPONSE_CODE_FAILURE).
BLOQUEAR_RECURSOS = os.getenv("BLOQUEAR_RECURSOS", "false").lower() == "true"
TIPOS_BLOQUEADOS = {"image", "media", "font"}

# --- Caché ---
CACHE_SEGUNDOS = 15 * 60  # evita volver a extraer el mismo perfil seguido

# --- Límites (reglas del proyecto: bajo volumen) ---
VIDEOS_POR_DEFECTO = 10
VIDEOS_MAXIMO = 30
COMENTARIOS_POR_DEFECTO = 20
COMENTARIOS_MAXIMO = 100

# --- Tiempos del scraper (milisegundos) ---
# Son tiempos MÁXIMOS: el scraper sigue apenas llegan los datos, no espera siempre todo el tiempo.
ESPERA_MAX_VIDEOS_MS = 8000        # esperar la primera lista de videos del perfil
ESPERA_MAX_SCROLL_PERFIL_MS = 4000  # esperar más videos después de cada scroll
INTENTOS_SCROLL_PERFIL = 8          # scrolls máximos para juntar videos
ESPERA_MAX_COMENTARIOS_MS = 8000    # esperar los primeros comentarios al abrir un video
ESPERA_MAX_MAS_COMENTARIOS_MS = 4000  # esperar más comentarios después de cada scroll
INTENTOS_SCROLL_COMENTARIOS = 10    # scrolls máximos dentro del panel de comentarios
PAUSA_ENTRE_VIDEOS_MS = 600         # pausa corta entre videos (ritmo "humano", bajo volumen)
