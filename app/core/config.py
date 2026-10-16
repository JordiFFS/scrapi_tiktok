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

# --- Caché ---
CACHE_SEGUNDOS = 15 * 60  # evita volver a extraer el mismo perfil seguido

# --- Límites (reglas del proyecto: bajo volumen) ---
VIDEOS_POR_DEFECTO = 10
VIDEOS_MAXIMO = 30
COMENTARIOS_POR_DEFECTO = 20
COMENTARIOS_MAXIMO = 100

# --- Tiempos del scraper (milisegundos) ---
ESPERA_CARGA_MS = 4000         # espera inicial tras abrir una página
ESPERA_SCROLL_PERFIL_MS = 2500  # pausa entre scrolls en el perfil
INTENTOS_SCROLL_PERFIL = 8      # scrolls máximos para juntar videos
ESPERA_SCROLL_VIDEO_MS = 2000   # pausa entre scrolls en los comentarios
INTENTOS_SCROLL_VIDEO = 5       # scrolls máximos para juntar comentarios
