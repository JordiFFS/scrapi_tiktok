# Proyecto: TikTok Data API (académico – Dispositivos Móviles)

## Qué es
API REST en Python que extrae datos **públicos** de perfiles de TikTok y los devuelve en JSON
para una app móvil que los mostrará en una interfaz gráfica. También analiza el perfil con modelos
locales de Hugging Face (Big Five del creador + sentimiento/emociones agregados de los comentarios).

## Estructura de carpetas
```
main.py                          crea la app, CORS y registra routers (único archivo en la raíz)
app/
  core/config.py                 configuración: HEADLESS, límites, caché, tiempos de espera
  routes/                        endpoints HTTP (ruta, parámetros, docs) → salud, perfil, busqueda, analisis, extracciones
  controllers/perfil_controller  caso de uso: caché → scraper (lock) → errores 404/502
  controllers/busqueda_controller búsqueda: caché → hashtags → candidatos (lock) → ranking
  controllers/analisis_controller caché propia → perfil_controller (reusa su caché) → to_thread(analisis) → 503
  controllers/extracciones_controller solicitud → tarea para la cola; estado → respuesta
  services/tiktok_scraper.py     Crawlee + Playwright, UNA sola página: perfil → clic en cada video de la
                                 cuadrícula (modal) → captura /api/post/item_list/ y /api/comment/list/
                                 + JSON #__UNIVERSAL_DATA_FOR_REHYDRATION__
  services/tiktok_busqueda.py    candidatos desde páginas públicas /tag/{hashtag} (/api/challenge/item_list/)
  services/embeddings.py         modelo local fastembed (paraphrase-multilingual-mpnet-base-v2, ~1 GB)
  services/ranking.py            puntaje = 0.5 relevancia + 0.3 interacción + 0.2 alcance (pesos en config)
  services/analisis.py           IA local (transformers, sin FastAPI): traducción opus-mt es→en + Big Five
                                 (Minej/bert-base-personality) + pysentimiento; carga perezosa de modelos
  services/cola_extracciones.py  cola en memoria + 1 trabajador (iniciado en el lifespan de main.py)
  services/navegador.py          lock_navegador (un navegador a la vez) + correr_con_limite (tiempo máximo real)
  services/cache.py              caché en memoria con TTL (15 min)
  validations/usuario.py         normaliza el usuario (quita @, espacios, mayúsculas)
  schemas/perfil.py              modelos Pydantic = contrato JSON con la app móvil (también busqueda,
                                 analisis, extracciones)
  utils/normalizadores.py        JSON de TikTok → formato en español
  utils/formato.py               fechas ISO, anonimización SHA-256
  utils/redes_sociales.py        detecta redes escritas en la bio/enlace (regex; no busca en otras redes)
  utils/texto.py                 consulta → hashtags (sin tildes, con/sin ñ); texto limpio para embeddings
  utils/esperas.py               esperar_hasta(condición, máx): esperas por condición
  utils/cronometro.py            log de tiempos por etapa (logger "tiktok_api")
```
Flujo: routes → validations → controllers → services → utils → schemas.
Documentación: README.md (levantar y usar) · docs/ARQUITECTURA.md (herramientas, estructura, flujo).
Cada archivo y función lleva docstring en español explicando qué hace.

## Entorno
- Shell: **fish** en Linux. Activar entorno: `source venv/bin/activate.fish`
- Instalar: `pip install torch --index-url https://download.pytorch.org/whl/cpu` PRIMERO (si no, pip baja
  torch con CUDA, ~4 GB), luego `pip install -r requirements.txt && playwright install chromium`
- Ejecutar: `python main.py` → docs en http://localhost:8000/docs
- Modo oculto: `env HEADLESS=true python main.py`
- Crawlee 1.x: `ConcurrencySettings` necesita `min`, `desired` y `max_concurrency` coherentes.
- `BLOQUEAR_RECURSOS=true` bloquea imágenes/video/fuentes (apagado por defecto: sin beneficio medido).
- Pruebas: `pytest` (simuladas, ~6 s) · `pytest --tiktok` (+2 reales) · `pytest --hf` (+modelos reales del
  análisis). Los fakes están en `tests/conftest.py` (usuarios "noexiste"/"explota", búsquedas
  "vacio"/"explota" provocan errores; `analisis_falso` reemplaza `analisis.analizar_perfil`).
  Si cambias el contrato JSON o una regla, actualiza también las pruebas.
- Commits: los hace el usuario. Perfil para pruebas reales: `jordifiallos`.

## Lecciones del scraper (no repetir)
- NO abrir `/video/{id}` directamente: TikTok responde `ERR_HTTP_RESPONSE_CODE_FAILURE` y no carga comentarios.
  Abrir el video con clic desde la cuadrícula (`[data-e2e="user-post-item"] a`), cerrar con `browse-close`.
- Playwright "pelado" (sin Crawlee/fingerprints) dispara captcha; usar siempre `PlaywrightCrawler`.
- Viewport de Crawlee = 2560×1440: no usar coordenadas fijas de mouse; usar selectores `data-e2e`.
- El JSON `#__UNIVERSAL_DATA_FOR_REHYDRATION__` (~180 KB) puede leerse a medio descargar
  ("Unterminated string" → "perfil NO encontrado" falso): esperar `domcontentloaded` y releer (INTENTOS_LEER_PERFIL).
- Esperas por condición (`_esperar_hasta`), no fijas. Saltar videos con `estadisticas.comentarios == 0`.
- `crawler.run()` de Crawlee captura la cancelación (asyncio.wait_for NO lo corta) e intercepta Ctrl+C:
  el tiempo máximo (EXTRACCION_TIEMPO_MAX_SEG=180) lo impone `correr_con_limite` con stop() + cerrar página → 502.
- `commentCount` de TikTok incluye respuestas; solo se extrae primer nivel (puede salir menos).
- Medición (jordifiallos, 7 videos, 2 con comentarios): 98 s con el método viejo → ~14 s con el nuevo.

## Lecciones de la búsqueda (/api/busqueda)
- `/search?q=` exige login (responde vacío) → se usan hashtags públicos `/tag/{h}`.
- La 1.ª página de un navegador nuevo suele recibir `item_list` 200 con cuerpo vacío; se reintenta el
  hashtag UNA vez como página nueva. Si todo sale vacío, probablemente TikTok está limitando: esperar.
- Si la página /tag/ muestra "Something went wrong" (detail 200 con datos, item_list 200 vacío), es
  TikTok negando la lista: no es bug del código y no se debe forzar; esperar (visto el 2026-10-16, mientras el perfil seguía funcionando).
- Con 3+ palabras la combinación completa (#fuerzaecuadorcabello) casi nunca existe: `generar_hashtags`
  prueba juntas → parejas seguidas → palabras solas (máx. BUSQUEDA_MAX_HASHTAGS = 6).
- No encadenar muchas búsquedas de prueba seguidas (~8 en 20 min ya provocó respuestas vacías).
- MiniLM falla con emojis/mayúsculas (0.82 → 0.39); mpnet entiende mejor sinónimos ("manicura de novia").
  El texto se limpia (sin #, emojis, hashtags genéricos) antes del embedding.
- Similitud de mpnet: ~0.5 tema general, ~0.9 casi idéntico → se reescala a 0-1 (SIMILITUD_MINIMA/MAXIMA).

## Lecciones del análisis (/api/analisis)
- `Minej/bert-base-personality`: config.json solo tiene LABEL_0..4; orden real (ficha) = Extroversion,
  Neuroticism, Agreeableness, Conscientiousness, Openness. La ficha dice "0 a 1" pero da logits negativos
  → sigmoide POR RASGO (nunca softmax: los rasgos son independientes). Valores ~0.35–0.55, diferencias chicas.
- opus-mt y BERT aceptan 512 tokens: `dividir_en_trozos` (400 traducción / 500 Big Five), promedio ponderado.
- pysentimiento preprocesa solo (emojis, @usuarios): no limpiar los comentarios antes.
- Modelos en ~/.cache/huggingface (~1.6 GB); 1.ª carga ~5 s; el análisis va en `asyncio.to_thread` con un lock.

## Reglas del proyecto
- **Solo datos públicos.** Nada que requiera iniciar sesión, cuentas privadas ni evasión agresiva de bloqueos.
- **Bajo volumen:** máximo 30 videos y 100 comentarios por post; no subir la concurrencia.
- **Privacidad (LOPDP Ecuador):** los autores de comentarios siempre anonimizados (`autor_anonimo`, hash SHA-256).
  Los **creadores** de videos sí se muestran (`creador` en /api/busqueda): son autores públicos del contenido
  (decisión del usuario, 2026-10-16). No exponer a otros terceros (comentaristas, menciones).
- **Análisis:** el Big Five es SOLO del creador (bio + sus descripciones). **Nunca** estimar personalidad de
  comentaristas individuales ni devolver sentimiento/emoción por comentario o persona: solo porcentajes
  agregados. Siempre incluir `nota` (exploratorio, no diagnóstico) y `advertencia` con < 10 textos.
- **Sin archivos:** la API responde en JSON; no guardar datasets en disco salvo que se pida.
- Mantener los nombres de campos en **español** y la estructura JSON estable (la app móvil depende de ella).
  Si se cambia un campo, actualizar `app/schemas/perfil.py`, el normalizador y el ejemplo del README.

## Estructura de la respuesta
`GET /api/perfil/{usuario}` → el usuario se escribe sin `@` (si viene con `@`, espacios o
mayúsculas, el backend lo normaliza antes de extraer y de usar la caché).

```
desde_cache            bool
usuario                str     (normalizado, sin @)
fecha_extraccion       str     ISO 8601 UTC
perfil                 obj
  usuario, nombre, biografia, avatar, verificado, privado,
  seguidores, siguiendo, likes_totales, total_videos,
  enlace_bio (str|None), redes_en_biografia {instagram|youtube|x|facebook: usuario} (solo lo publicado)
total_videos_extraidos int
videos[]
  id, url, descripcion, fecha, portada, duracion_seg, musica, hashtags[]
  estadisticas { vistas, likes, comentarios, compartidos, guardados }
  comentarios[]
    id, texto, fecha, likes, respuestas, autor_anonimo (hash SHA-256, 12 caracteres)
```

Errores: `400` usuario vacío · `404` perfil no encontrado/privado/bloqueado · `502` fallo en la extracción.

## Limitaciones conocidas
Tarda ~3 s + ~2–7 s por video con comentarios, frágil ante cambios internos de TikTok, captchas/bloqueos,
comentarios solo de primer nivel, datos como foto del momento (sin historial), caché se pierde al reiniciar.

## Respuesta de /api/analisis/{usuario} (mismos parámetros que /api/perfil)
`usuario, desde_cache, fecha_analisis, big5_creador {apertura, responsabilidad, extraversion, amabilidad,
neuroticismo} (0-1, o null sin textos), textos_analizados, advertencia, comentarios {total_analizados,
sentimiento {positivo, neutral, negativo}, emociones {alegria, tristeza, enojo, miedo, sorpresa, asco, otros}}
(porcentajes 0-100), modelos {big5, traduccion, sentimiento, emociones}, nota`. Error extra: `503` si fallan los modelos.

## Extracciones asíncronas (forma recomendada para la app)
`POST /api/extracciones` con `{"tipo":"perfil","usuario":...}`, `{"tipo":"busqueda","q":...}` o
`{"tipo":"analisis","usuario":...}` → 202 con `id`.
`GET /api/extracciones/{id}` → `estado` pendiente|en_proceso|completada|error, `posicion_en_cola`,
`consultar_de_nuevo_en_seg`, `error {codigo, detalle}`, `resultado` (= respuesta de /api/perfil, /busqueda o /analisis).
- `services/cola_extracciones.py`: UN trabajador, orden de llegada, en memoria (se pierde al reiniciar).
- Caché → nace "completada"; solicitud idéntica en curso → mismo id; >10 en cola → 429; terminadas viven 30 min.
- La tarea reutiliza los controllers directos (misma caché, validación, lock y errores).
- Probar sin tocar TikTok: parchear `tiktok_scraper.extraer_perfil` / `tiktok_busqueda.buscar_candidatos`.

## Respuesta de /api/busqueda?q=&max_resultados=&refrescar=
`desde_cache, consulta, hashtags_usados[], fecha_extraccion, total_candidatos, total_resultados,
resultados[]` → cada uno es un video (mismos campos que en perfil, `comentarios` vacío) +
`creador {usuario, nombre, verificado, seguidores}` + `puntaje {relevancia, interaccion, alcance, total}`.

## Pendientes / ideas
- Interfaz gráfica móvil que consuma la API (emulador Android: `http://10.0.2.2:8000`).
- Responder y documentar en **español**.
