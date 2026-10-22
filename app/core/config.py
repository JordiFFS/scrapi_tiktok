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

# --- Memoria de Crawlee ---
# Por defecto Crawlee asume que puede usar el 25 % de la RAM y cuenta TODO el proceso,
# incluido el modelo de embeddings (~1 GB). Con 25 % avisaba "Memory is critically overloaded".
os.environ.setdefault("CRAWLEE_AVAILABLE_MEMORY_RATIO", "0.5")

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
INTENTOS_LEER_PERFIL = 4            # lecturas del JSON del perfil (cada 0.5 s) si llega incompleto
ESPERA_MAX_VIDEOS_MS = 8000       # esperar la primera lista de videos del perfil
ESPERA_MAX_SCROLL_PERFIL_MS = 4000  # esperar más videos después de cada scroll
INTENTOS_SCROLL_PERFIL = 8          # scrolls máximos para juntar videos
ESPERA_MAX_COMENTARIOS_MS = 8000    # esperar los primeros comentarios al abrir un video
ESPERA_MAX_MAS_COMENTARIOS_MS = 4000  # esperar más comentarios después de cada scroll
INTENTOS_SCROLL_COMENTARIOS = 10    # scrolls máximos dentro del panel de comentarios
PAUSA_ENTRE_VIDEOS_MS = 600         # pausa corta entre videos (ritmo "humano", bajo volumen)
# Tiempo máximo de UNA extracción (perfil o búsqueda) con el navegador. Si se pasa, se cancela,
# se cierra el navegador y se responde 502: así un navegador trabado no bloquea la cola para siempre.
EXTRACCION_TIEMPO_MAX_SEG = int(os.getenv("EXTRACCION_TIEMPO_MAX_SEG", "180"))

# --- Extracciones asíncronas (POST /api/extracciones) ---
EXTRACCIONES_MAX_EN_COLA = 10           # más pendientes que esto -> 429 (bajo volumen)
EXTRACCIONES_TTL_SEGUNDOS = 30 * 60     # cuánto se guarda una extracción terminada para consultarla
EXTRACCIONES_SUGERENCIA_CONSULTA_SEG = 3  # cada cuánto debería preguntar la app por el estado

# --- Búsqueda general por tema (GET /api/busqueda) ---
# La búsqueda libre de TikTok exige iniciar sesión; se usan las páginas públicas de hashtags (/tag/...).
BUSQUEDA_RESULTADOS_POR_DEFECTO = 10
BUSQUEDA_RESULTADOS_MAXIMO = 30
BUSQUEDA_MAX_CANDIDATOS = 60      # videos que se juntan antes de ordenar (bajo volumen)
BUSQUEDA_MAX_HASHTAGS = 6         # máx. hashtags a visitar; se detiene antes si ya hay MAX_CANDIDATOS
BUSQUEDA_PAGINAS_POR_HASHTAG = 2  # cada página de un hashtag trae ~30 videos

# --- Embeddings (modelo local, los textos no salen de la PC) ---
# mpnet entiende mejor el español que MiniLM (ej. "manicura de novia" ≈ "uñas para boda": 0.81 vs 0.45).
# Pesa ~1 GB y tarda ~1 s en procesar 90 textos en CPU.
MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
MODELO_CACHE = os.path.expanduser(os.getenv("MODELO_CACHE", "~/.cache/fastembed"))

# --- Ranking: puntaje total = suma de pesos × componentes (cada componente va de 0 a 1) ---
PESO_RELEVANCIA = 0.5   # qué tan relacionado está el video con lo buscado (embeddings)
PESO_INTERACCION = 0.3  # cuánto interactúa la gente respecto a las vistas
PESO_ALCANCE = 0.2      # cuántas vistas tiene
# La similitud coseno de este modelo va de ~0.5 (tema general, ej. solo "uñas") a ~0.9 (casi idéntico);
# ese rango se estira a 0-1 para que la relevancia distinga de verdad entre videos del mismo hashtag.
SIMILITUD_MINIMA = 0.5
SIMILITUD_MAXIMA = 0.9
TASA_INTERACCION_REFERENCIA = 0.15  # 15 % de interacción sobre vistas ya es excelente
SUAVIZADO_VISTAS = 1000         # evita que un video con 10 vistas y 5 likes gane por casualidad
VISTAS_REFERENCIA = 10_000_000  # 10 M de vistas = alcance máximo

# --- Análisis con Hugging Face (GET /api/analisis) ---
# Modelos locales con transformers (sin token). Se descargan la primera vez (~1.6 GB en total)
# a la caché de Hugging Face (~/.cache/huggingface, fuera del proyecto) y se cargan al primer uso.
MODELO_TRADUCCION = "Helsinki-NLP/opus-mt-es-en"            # español -> inglés (~300 MB)
MODELO_BIG5 = "Minej/bert-base-personality"                 # Big Five, solo entiende inglés (~440 MB)
MODELO_SENTIMIENTO = "pysentimiento/robertuito-sentiment-analysis"  # POS/NEU/NEG en español (~435 MB)
MODELO_EMOCIONES = "pysentimiento/robertuito-emotion-analysis"      # 7 emociones en español (~435 MB)
# Con menos textos que esto el Big Five igual se calcula, pero se avisa que es poco confiable
ANALISIS_TEXTOS_MINIMOS = 10
# Tokens máximos por trozo. Ambos modelos aceptan 512; se deja margen para los tokens especiales.
ANALISIS_TOKENS_TRADUCCION = 400
ANALISIS_TOKENS_BIG5 = 500
ANALISIS_LOTE_TRADUCCION = 8  # trozos que se traducen juntos (más = más RAM, no mucho más rápido)
