# Arquitectura y herramientas

Cómo está construida la TikTok Data API: qué herramientas usa y por qué, cómo están organizadas
las carpetas y qué pasa por dentro en cada petición. Para instalarla y levantarla, ver el
[README](../README.md).

---

## 1. Herramientas

### Servidor web

| Herramienta | Para qué se usa en el proyecto |
|---|---|
| **Python 3.11+** | Lenguaje de todo el backend; se usa `async/await` para no bloquear la API mientras el navegador trabaja |
| **FastAPI** | Framework de la API REST: rutas, validación de parámetros y documentación automática en `/docs` |
| **Pydantic** | Modelos de la respuesta JSON (`app/schemas/`). FastAPI valida la salida contra ellos: si cambia la estructura falla en el servidor, no en el celular |
| **Uvicorn** | Servidor ASGI que ejecuta FastAPI (`python main.py`) |

### Extracción de datos (scraping)

| Herramienta | Para qué se usa en el proyecto |
|---|---|
| **Playwright** | Controla un Chromium real: abre TikTok, hace scroll y clic como una persona |
| **Crawlee** (`PlaywrightCrawler`) | Encima de Playwright: maneja el navegador, reintentos y huellas de navegador (*fingerprints*) realistas. Sin Crawlee, Playwright "pelado" dispara el captcha de TikTok |

TikTok no tiene API pública para esto. La página de TikTok llama a su **propia API interna**
(`/api/post/item_list/`, `/api/comment/list/`, `/api/challenge/item_list/`). El scraper no lee el
HTML: **escucha esas respuestas JSON** mientras navega y además lee el JSON incrustado
`#__UNIVERSAL_DATA_FOR_REHYDRATION__` con los datos del perfil.

### Búsqueda y ranking

| Herramienta | Para qué se usa en el proyecto |
|---|---|
| **fastembed** + **ONNX Runtime** | Ejecutan el modelo de embeddings **en la PC** (sin PyTorch ni APIs externas; los textos no salen del equipo) |
| **paraphrase-multilingual-mpnet-base-v2** | Modelo que convierte un texto en un vector de 768 números; textos con significado parecido quedan cerca ("uñas para boda" ≈ "manicura de novia") |
| **NumPy** | Similitud coseno entre la búsqueda y la descripción de cada video |

### Pruebas

| Herramienta | Para qué se usa en el proyecto |
|---|---|
| **pytest** | 74 pruebas que no tocan TikTok (scrapers simulados en `tests/conftest.py`) + 2 reales con `--tiktok` |
| **TestClient** de FastAPI (httpx) | Llama a los endpoints como lo haría la app, sin levantar el servidor |

---

## 2. Estructura de carpetas

```
main.py                         Punto de entrada: crea la app, CORS, registra routers y, al arrancar,
                                inicia la cola de extracciones y carga el modelo en segundo plano
requirements.txt                Dependencias de la API
requirements-dev.txt            + pytest
pytest.ini                      Configuración y marcadores de las pruebas
docs/ARQUITECTURA.md            Este documento
app/
├── core/
│   └── config.py               TODOS los valores ajustables: límites, tiempos, caché, pesos del ranking,
│                               variables de entorno (HEADLESS, PORT, EXTRACCION_TIEMPO_MAX_SEG…)
├── routes/                     "Cara" HTTP: URL, parámetros, códigos de respuesta y documentación
│   ├── salud.py                GET  /api/salud
│   ├── perfil.py               GET  /api/perfil/{usuario}
│   ├── busqueda.py             GET  /api/busqueda
│   └── extracciones.py         POST /api/extracciones · GET /api/extracciones/{id}
├── validations/                Limpian lo que envía la app y responden 400 si no sirve
│   ├── usuario.py              "@Jordi " → "jordi"
│   └── busqueda.py             "  #Uñas  Acrílicas" → "uñas acrílicas"
├── controllers/                Lógica de cada caso de uso: caché → navegador → errores HTTP
│   ├── perfil_controller.py
│   ├── busqueda_controller.py
│   └── extracciones_controller.py   Convierte una solicitud en una tarea para la cola
├── services/                   Trabajo pesado o con estado
│   ├── tiktok_scraper.py       Extrae perfil + videos + comentarios (Crawlee/Playwright)
│   ├── tiktok_busqueda.py      Junta videos candidatos desde páginas /tag/{hashtag}
│   ├── navegador.py            lock_navegador (un navegador a la vez) y correr_con_limite (tiempo máximo)
│   ├── cola_extracciones.py    Cola en memoria con UN trabajador para las extracciones asíncronas
│   ├── cache.py                Caché en memoria con vencimiento (15 min)
│   ├── embeddings.py           Carga el modelo local y calcula similitudes
│   └── ranking.py              Puntaje = 0.5 relevancia + 0.3 interacción + 0.2 alcance
├── schemas/                    Contrato JSON con la app (modelos Pydantic)
│   ├── perfil.py               RespuestaPerfil, Perfil, Video, Estadisticas, Comentario
│   ├── busqueda.py             RespuestaBusqueda, VideoBusqueda, Creador, Puntaje
│   └── extracciones.py         SolicitudPerfil/Busqueda, EstadoExtraccion
└── utils/                      Funciones pequeñas y puras (fáciles de probar)
    ├── normalizadores.py       JSON de TikTok (inglés) → formato de la API (español)
    ├── formato.py              Fechas ISO 8601 y anonimización SHA-256
    ├── redes_sociales.py       Detecta Instagram/YouTube/X/Facebook escritos en la bio
    ├── texto.py                Consulta → hashtags; limpieza de texto para el modelo
    ├── esperas.py              esperar_hasta(condición, máx.): esperas por condición, no fijas
    └── cronometro.py           Registra en consola cuánto tarda cada etapa
tests/
├── conftest.py                 TikTok simulado + fixtures (cliente, caché limpia)
├── test_utils.py               Funciones puras de utils/
├── test_validaciones.py        Reglas de validations/
├── test_servicios.py           Caché, ranking, cola, tiempo máximo, modelo real
├── test_endpoints.py           Todos los endpoints y códigos HTTP
└── test_tiktok_real.py         Contra TikTok de verdad (solo con --tiktok)
```

### Regla de dependencias

```
routes → validations → controllers → services → utils
                                   ↘ schemas (contrato de salida)
```

Cada capa solo llama a las de su derecha. Así, por ejemplo, el scraper no sabe nada de HTTP y
se puede probar (o reemplazar por un falso en las pruebas) sin levantar la API.

---

## 3. Qué pasa en cada petición

### Perfil — `GET /api/perfil/jordifiallos`

```
1. routes/perfil.py          recibe la petición y los parámetros (FastAPI valida rangos → 422)
2. validations/usuario.py    normaliza el usuario ("@Jordi" → "jordi") o responde 400
3. perfil_controller         ¿está en caché (15 min)? → responde al instante con desde_cache=true
4.                           si no: toma lock_navegador (un navegador a la vez en toda la API)
5. tiktok_scraper            abre https://www.tiktok.com/@jordi en Chromium (vía correr_con_limite)
   a. lee el JSON incrustado del perfil (reintenta si llegó a medio descargar)
   b. hace scroll y captura /api/post/item_list/ → videos
   c. por cada video con comentarios > 0: clic en la cuadrícula → se abre como ventana →
      captura /api/comment/list/ → scroll si faltan → cierra la ventana
6. utils/normalizadores      convierte cada JSON de TikTok al formato en español
                             (autores de comentarios → hash SHA-256)
7. perfil_controller         sin perfil → 404 · error o tiempo agotado → 502 · si todo bien, guarda en caché
8. schemas/perfil.py         FastAPI valida la respuesta contra el contrato y la envía
```

### Búsqueda — `GET /api/busqueda?q=fuerza ecuador cabello`

```
1. validations/busqueda.py   limpia la consulta; 400 si queda vacía o solo con "de", "la"...
2. busqueda_controller       ¿consulta en caché? → recorta a max_resultados y responde
3. utils/texto.py            consulta → hashtags, del más específico al más general:
                             fuerzaecuadorcabello → fuerzaecuador → ecuadorcabello → fuerza → ecuador → cabello
4. tiktok_busqueda           visita /tag/{hashtag} en orden hasta juntar 60 videos
                             (si un hashtag no existe pasa al siguiente)
5. ranking + embeddings      puntúa cada video (relevancia, interacción, alcance) y los ordena
6. busqueda_controller       guarda TODOS los ordenados en caché y responde los primeros max_resultados
```

### Extracción asíncrona — `POST /api/extracciones`

```
POST  → extracciones_controller valida y arma una "tarea" que llama al MISMO controller de arriba
      → cola_extracciones: si está en caché nace "completada"; si ya hay una igual en curso
        devuelve ese mismo id; si hay más de 10 esperando → 429
      → responde 202 con el id
Trabajador (uno solo, en segundo plano): toma la más antigua → "en_proceso" → ejecuta →
        "completada" (con resultado) o "error" (con código y detalle)
GET /api/extracciones/{id} → estado actual, posición en la cola y cada cuánto volver a preguntar
```

---

## 4. Decisiones de diseño

| Decisión | Por qué |
|---|---|
| Escuchar la API interna en vez de leer el HTML | El JSON trae números exactos y cambia menos que el diseño de la página |
| Abrir los videos con **clic** desde la cuadrícula | Abrir `/video/{id}` directamente hace que TikTok rechace la página y no cargue comentarios |
| **Una sola página** para perfil + todos los videos | Pasó de ~98 s a ~14 s con el perfil de prueba |
| Esperas "hasta que llegue el dato" (`esperar_hasta`) | No se pierde tiempo cuando TikTok responde rápido |
| Saltar videos con 0 comentarios | No hace falta abrirlos |
| Hashtags públicos para la búsqueda | `/search` de TikTok exige iniciar sesión (regla: solo datos públicos) |
| Modelo de embeddings **local** | Gratis, sin enviar textos a terceros; entiende sinónimos en español |
| Un navegador a la vez + cola con un trabajador | Bajo volumen (menos bloqueos de TikTok, menos RAM) |
| Tiempo máximo propio (`correr_con_limite`) | `crawler.run()` de Crawlee ignora la cancelación; sin esto un navegador trabado bloqueaba la cola indefinidamente |
| Caché en memoria de 15 min | Evita repetir extracciones; acepta que se pierda al reiniciar |
| Campos en **español** y estructura estable | La app móvil depende de ellos; cualquier cambio se refleja en `schemas/`, normalizadores y README |

## 5. Limitaciones conocidas

- Depende de la API interna de TikTok: si TikTok la cambia, hay que ajustar `normalizadores.py`.
- TikTok puede mostrar captchas o limitar las consultas (sobre todo la búsqueda por hashtags).
- Solo comentarios de primer nivel (el `commentCount` de TikTok incluye respuestas, por eso puede salir menos).
- Los datos son una foto del momento: no hay historial.
- Caché, cola y resultados viven en memoria: se pierden al reiniciar la API.
