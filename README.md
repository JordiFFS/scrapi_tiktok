# TikTok Data API (uso académico)

API REST en Python que extrae datos **públicos** de TikTok (perfiles, posts, estadísticas,
comentarios y búsqueda por tema) y los devuelve en **JSON** para una app móvil. Además analiza
los perfiles con modelos locales de Hugging Face (Big Five del creador y sentimiento de los comentarios).
No guarda archivos: todo vive en memoria.

> ¿Cómo está hecho por dentro y qué herramientas usa? → [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)

---

## 1. Requisitos

| Necesitas | Versión | Para qué |
|---|---|---|
| Python | 3.11 o superior (probado con 3.14) | Ejecutar la API |
| Conexión a internet | — | Abrir TikTok y descargar los modelos la primera vez |
| Espacio en disco | ~4 GB | Chromium (~300 MB) + embeddings (~1 GB) + torch CPU (~1 GB) + modelos del análisis (~1.6 GB) |
| RAM | 4 GB libres (6 GB si se usa `/api/analisis`) | Navegador + modelos cargados |

## 2. Instalación (una sola vez)

```bash
# 1) Crear el entorno virtual
python -m venv venv

# 2) Activarlo (elige tu terminal)
source venv/bin/activate.fish     # fish
source venv/bin/activate          # bash / zsh
venv\Scripts\activate             # Windows

# 3) Instalar torch para CPU PRIMERO (si no, pip baja la versión con CUDA: ~4 GB más)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 4) Instalar el resto de dependencias y el navegador Chromium que usa Playwright
pip install -r requirements.txt
playwright install chromium
```

## 3. Levantar la API

```bash
python main.py
```

Verás en consola `Uvicorn running on http://0.0.0.0:8000`. Luego comprueba:

| Qué | URL |
|---|---|
| ¿Está viva? | http://localhost:8000/api/salud → `{"estado":"ok"}` |
| Documentación interactiva (probar endpoints desde el navegador) | http://localhost:8000/docs |
| Perfil de prueba | http://localhost:8000/api/perfil/jordifiallos?max_videos=5 |
| Búsqueda de prueba | http://localhost:8000/api/busqueda?q=uñas |
| Análisis de prueba | http://localhost:8000/api/analisis/jordifiallos |

**La primera vez** que arranca descarga el modelo de embeddings (~1 GB, a `~/.cache/fastembed`).
La API responde mientras tanto; la primera búsqueda espera a que termine la descarga.

Por defecto se abre una **ventana de Chromium** cuando se extrae algo: es normal. Si aparece un
captcha, resuélvelo a mano en esa ventana.

Para detener la API: **Ctrl+C** (si hay una extracción en curso, Crawlee pide un segundo Ctrl+C).

### Variables de entorno (opcionales)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `HEADLESS` | `false` | `true` = navegador oculto (TikTok lo bloquea con más frecuencia) |
| `PORT` | `8000` | Puerto de la API |
| `HOST` | `0.0.0.0` | Interfaz de red (`0.0.0.0` permite conectarse desde el celular) |
| `EXTRACCION_TIEMPO_MAX_SEG` | `180` | Tiempo máximo de una extracción; si se pasa, se cierra el navegador y responde `502` |
| `BLOQUEAR_RECURSOS` | `false` | `true` = no descarga imágenes/videos/fuentes (sin beneficio medido) |
| `MODELO_CACHE` | `~/.cache/fastembed` | Carpeta donde se guarda el modelo de embeddings |
| `HF_HOME` | `~/.cache/huggingface` | Carpeta donde se guardan los modelos del análisis (variable de Hugging Face) |

```bash
env HEADLESS=true PORT=9000 python main.py     # fish
HEADLESS=true PORT=9000 python main.py         # bash / zsh
```

## 4. Conectar la app móvil

| Desde | URL base |
|---|---|
| Navegador en la misma PC | `http://localhost:8000` |
| Emulador de Android | `http://10.0.2.2:8000` |
| Celular físico (misma red Wi-Fi) | `http://<IP-de-tu-PC>:8000`, ej. `http://192.168.1.10:8000` |

Para el celular físico: averigua la IP con `ip addr` (Linux) o `ipconfig` (Windows) y permite el
puerto 8000 en el firewall si hace falta.

**Forma recomendada para la app:** usar las extracciones asíncronas (sección 6.3): la app recibe
un `id` al instante y consulta el estado, en vez de esperar 10–40 s con la conexión abierta.

## 5. Pruebas

```bash
pip install -r requirements-dev.txt
pytest              # 89 pruebas, ~6 s, SIN tocar TikTok ni los modelos del análisis (simulados)
pytest --tiktok     # además 2 pruebas reales: perfil jordifiallos y búsqueda #uñas (abre el navegador)
pytest --hf         # además la prueba con los modelos reales de Hugging Face (~10 s ya descargados)
```

Las reales pueden fallar si TikTok está limitando las consultas: no es necesariamente un bug
(ver "Solución de problemas").

---

## 6. Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/salud` | Verifica que la API esté activa |
| GET | `/api/perfil/{usuario}` | Perfil, últimos posts, estadísticas y comentarios (usuario con o sin `@`) |
| GET | `/api/busqueda?q=...` | Mejores videos sobre un tema (hashtags públicos + ranking) |
| GET | `/api/analisis/{usuario}` | Big Five del creador + sentimiento/emociones agregados de los comentarios (sección 10) |
| POST | `/api/extracciones` | **Recomendado para la app:** crea una extracción (perfil, búsqueda o análisis) y responde con un `id` |
| GET | `/api/extracciones/{id}` | Estado de la extracción y, al terminar, su resultado |

### Errores

| Código | Cuándo |
|---|---|
| `400` | Usuario vacío, búsqueda muy corta/larga o solo con palabras como "de la" |
| `404` | Perfil inexistente/privado/bloqueado, o ningún hashtag devolvió videos |
| `422` | Parámetro fuera de rango (ej. `max_videos=50`) |
| `429` | Más de 10 extracciones esperando en la cola |
| `502` | Falló la extracción o superó `EXTRACCION_TIEMPO_MAX_SEG` |
| `503` | No se pudieron cargar o ejecutar los modelos del análisis (p. ej. sin internet en la primera descarga) |

### 6.1 Perfil — `GET /api/perfil/{usuario}`

| Parámetro | Por defecto | Descripción |
|---|---|---|
| `max_videos` | 10 (máx. 30) | Posts recientes a extraer |
| `comentarios` | true | Incluir comentarios |
| `max_comentarios` | 20 (máx. 100) | Comentarios por post (solo primer nivel) |
| `refrescar` | false | Ignorar la caché de 15 min |

```json
{
  "desde_cache": false,
  "usuario": "nombre_usuario",
  "fecha_extraccion": "2026-10-16T14:00:00+00:00",
  "perfil": {
    "usuario": "nombre_usuario", "nombre": "Nombre", "biografia": "...",
    "avatar": "https://...", "verificado": true, "privado": false,
    "seguidores": 12500, "siguiendo": 80, "likes_totales": 340000, "total_videos": 120,
    "enlace_bio": "https://linktr.ee/nombre_usuario",
    "redes_en_biografia": { "instagram": "nombre.usuario", "youtube": "MiCanal" }
  },
  "total_videos_extraidos": 1,
  "videos": [{
    "id": "7412345678901234567",
    "url": "https://www.tiktok.com/@nombre_usuario/video/7412345678901234567",
    "descripcion": "...", "fecha": "2026-10-10T18:20:00+00:00",
    "portada": "https://...", "duracion_seg": 32, "musica": "sonido original",
    "hashtags": ["ecuador", "quito"],
    "estadisticas": { "vistas": 45000, "likes": 3200, "comentarios": 150, "compartidos": 40, "guardados": 90 },
    "comentarios": [
      { "id": "...", "texto": "...", "fecha": "...", "likes": 12, "respuestas": 2, "autor_anonimo": "a1b2c3d4e5f6" }
    ]
  }]
}
```

- `autor_anonimo`: hash SHA-256 (12 caracteres) del autor del comentario; nunca se muestra quién comentó.
- `redes_en_biografia`: solo las redes que el dueño escribió en su bio o enlace (`instagram`, `youtube`, `x`, `facebook`).

### 6.2 Búsqueda por tema — `GET /api/busqueda?q=uñas acrílicas&max_resultados=10`

La búsqueda libre de TikTok exige iniciar sesión, así que se visitan páginas públicas de hashtags
derivadas de la consulta (`#uñasacrilicas`, `#unasacrilicas`, `#uñas`…), se juntan hasta 60 videos
y se ordenan por:

| Componente | Peso | Qué mide |
|---|---|---|
| `relevancia` | 0.5 | Similitud de significado con la búsqueda (modelo local de embeddings) |
| `interaccion` | 0.3 | (likes + comentarios + compartidos + guardados) / vistas |
| `alcance` | 0.2 | Vistas en escala logarítmica (10 M = 1.0) |

```json
{
  "desde_cache": false, "consulta": "uñas acrílicas",
  "hashtags_usados": ["uñasacrilicas", "unasacrilicas"],
  "fecha_extraccion": "2026-10-16T18:00:00+00:00",
  "total_candidatos": 60, "total_resultados": 10,
  "resultados": [{
    "id": "7094396577250381061", "url": "https://www.tiktok.com/@creador/video/7094396577250381061",
    "descripcion": "...", "hashtags": ["uñas", "uñasacrilicas"], "estadisticas": { "vistas": 2100000, "...": 0 },
    "comentarios": [],
    "creador": { "usuario": "creador", "nombre": "Nombre", "verificado": false, "seguidores": 15000 },
    "puntaje": { "relevancia": 0.79, "interaccion": 1.0, "alcance": 0.9, "total": 0.87 }
  }]
}
```

`max_resultados`: 10 por defecto (máx. 30). Cambiarlo no vuelve a abrir TikTok si la búsqueda está en caché.

### 6.3 Extracciones asíncronas (recomendado para la app)

```http
POST /api/extracciones
{"tipo": "perfil", "usuario": "jordifiallos", "max_videos": 10, "max_comentarios": 20}
{"tipo": "busqueda", "q": "uñas acrílicas", "max_resultados": 10}
{"tipo": "analisis", "usuario": "jordifiallos", "max_videos": 10}
```

Responde `202` al instante:

```json
{ "id": "b2d79cf7bd71", "tipo": "perfil", "estado": "pendiente", "posicion_en_cola": 1,
  "consultar_de_nuevo_en_seg": 3, "resultado": null, "error": null, "...": "..." }
```

Luego `GET /api/extracciones/b2d79cf7bd71` cada `consultar_de_nuevo_en_seg` segundos hasta que `estado` sea:
- `completada` → `resultado` trae exactamente lo mismo que `/api/perfil`, `/api/busqueda` o `/api/analisis`.
- `error` → `error: {"codigo": 404, "detalle": "..."}` (mismos códigos que los endpoints directos).

Se procesa una extracción a la vez; si el dato está en caché nace `completada`; pedir dos veces lo
mismo devuelve el mismo `id`; los resultados se pueden consultar 30 min y se pierden al reiniciar.

```javascript
const API = "http://10.0.2.2:8000";   // emulador Android

async function extraer(solicitud) {
  let ext = await (await fetch(`${API}/api/extracciones`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(solicitud),
  })).json();
  while (ext.estado === "pendiente" || ext.estado === "en_proceso") {
    await new Promise(r => setTimeout(r, ext.consultar_de_nuevo_en_seg * 1000));
    ext = await (await fetch(`${API}/api/extracciones/${ext.id}`)).json();
  }
  if (ext.estado === "error") throw new Error(ext.error.detalle);
  return ext.resultado;
}
```

---

## 7. Tiempos esperados

| Operación | Tiempo aproximado |
|---|---|
| Respuesta desde caché (15 min) | instantánea |
| Perfil sin comentarios | ~5–7 s |
| Perfil con comentarios | ~3 s + 2–7 s por cada video que tenga comentarios |
| Búsqueda por tema | ~10–30 s (según cuántos hashtags existan) |
| Análisis | lo que tarde el perfil (o 0 s si está en caché) + ~2–10 s de CPU; la 1.ª vez +5 s de carga de modelos (y la descarga de ~1.6 GB) |
| Límite duro de cualquier extracción | 180 s (`EXTRACCION_TIEMPO_MAX_SEG`) |

## 8. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La búsqueda da `404` incluso para temas comunes ("cabello") | TikTok está limitando las listas de hashtags (pasa tras ~8 búsquedas en 20 min) | Esperar 20–30 min; usar la caché; no repetir búsquedas seguidas |
| `404` en un perfil que sí existe | Captcha o bloqueo de TikTok | Usar `HEADLESS=false` y resolver el captcha en la ventana |
| `502 ... superó 180 s` | El navegador se trabó o TikTok no respondió | Reintentar; si se repite, reiniciar la API |
| Ctrl+C no detiene la API | Crawlee intercepta el primer Ctrl+C mientras extrae | Presionar Ctrl+C otra vez |
| `playwright ... Executable doesn't exist` | Falta el navegador | `playwright install chromium` |
| La primera búsqueda tarda mucho | Se está descargando el modelo (~1 GB) | Esperar; solo pasa la primera vez |
| El primer análisis tarda mucho o da `503` | Se están descargando los modelos (~1.6 GB) o no hay internet | Esperar / revisar la conexión; solo pasa la primera vez |
| `pip install` descarga paquetes `nvidia-*` | Se instaló torch con CUDA | `pip uninstall torch` y repetir el paso 3 de la instalación |
| Un campo deja de llegar | TikTok cambió su API interna | Revisar en el navegador la pestaña **Network** (`/api/post/item_list/`, `/api/comment/list/`) |

## 9. Reglas de uso

- Solo datos **públicos**: nada que requiera iniciar sesión, ni cuentas privadas.
- **Bajo volumen**: máximo 30 videos y 100 comentarios por post, una extracción a la vez.
- **Privacidad (LOPDP Ecuador)**: los autores de comentarios siempre van anonimizados. Los creadores
  de videos en la búsqueda sí se muestran (son autores públicos del contenido).
- **Análisis**: la personalidad solo se estima del **creador** del perfil; de los comentarios solo se
  publican porcentajes del conjunto, nunca nada por persona.
- Proyecto académico (Dispositivos Móviles).

---

## 10. Análisis con Hugging Face

`GET /api/analisis/{usuario}` estima **dos cosas distintas** con modelos que corren **en la PC**
(librería `transformers`, sin token ni APIs externas: los textos no salen del equipo):

1. **Big Five del creador**: la personalidad que *proyecta* el dueño del perfil en su biografía y
   en las descripciones de sus videos.
2. **Sentimiento y emociones de los comentarios**, solo como **porcentajes del conjunto**.

El código está en `app/services/analisis.py` (sin nada de FastAPI, comentado paso a paso para estudiarlo).

### Modelos usados y por qué

| Tarea | Modelo | Por qué este |
|---|---|---|
| Traducción es → en | [`Helsinki-NLP/opus-mt-es-en`](https://huggingface.co/Helsinki-NLP/opus-mt-es-en) | El modelo de personalidad solo entiende inglés. Es pequeño (~300 MB), rápido en CPU y de buena calidad |
| Big Five | [`Minej/bert-base-personality`](https://huggingface.co/Minej/bert-base-personality) | BERT ajustado para los 5 rasgos; uno de los pocos modelos públicos de Big Five en Hugging Face |
| Sentimiento | [`pysentimiento/robertuito-sentiment-analysis`](https://huggingface.co/pysentimiento/robertuito-sentiment-analysis) | Entrenado con tuits **en español**: entiende jerga, emojis y faltas de ortografía, como en TikTok |
| Emociones | [`pysentimiento/robertuito-emotion-analysis`](https://huggingface.co/pysentimiento/robertuito-emotion-analysis) | Igual que el anterior, con 7 categorías (alegría, tristeza, enojo, miedo, sorpresa, asco, otros) |

### Cómo funciona paso a paso

```
1. analisis_controller   ¿análisis en caché (15 min)? → responde al instante (desde_cache=true)
2.                       obtiene el perfil con el MISMO controller de /api/perfil:
                         si ya fue extraído (caché) NO se vuelve a abrir TikTok
3. asyncio.to_thread     los modelos usan CPU varios segundos: corren en otro hilo para que la
                         API siga respondiendo a otras peticiones (un análisis a la vez)
4. services/analisis.py
   Big Five del creador:
   a. junta biografía + descripción de cada video y las limpia (sin URLs, @menciones, emojis, #fyp)
   b. traduce al inglés por trozos de ≤ 400 tokens (el traductor acepta máx. 512)
   c. aplica el modelo por trozos de ≤ 500 tokens y promedia (ponderado por tokens)
   d. el modelo da 5 números INDEPENDIENTES (uno por rasgo): a cada uno se le aplica sigmoide
      por separado para llevarlo a 0-1. NO se usa softmax (obligaría a que los 5 sumen 1)
   Comentarios:
   e. pysentimiento etiqueta cada comentario (POS/NEU/NEG y su emoción principal)
   f. se cuentan las etiquetas → porcentajes; las etiquetas individuales se descartan
5. se guarda en la caché del análisis y se responde
```

Detalles verificados del modelo Big Five (la ficha y el modelo no coinciden del todo):
- Su `config.json` solo dice `LABEL_0…LABEL_4`; el orden real, según la ficha, es
  **Extroversion, Neuroticism, Agreeableness, Conscientiousness, Openness**.
- La ficha dice que la salida va de 0 a 1, pero en la práctica da valores negativos (ej. `-0.75`):
  por eso se aplica sigmoide a cada rasgo.

### Endpoint

| Parámetro | Por defecto | Descripción |
|---|---|---|
| `max_videos` | 10 (máx. 30) | Posts a analizar (más posts → Big Five más confiable) |
| `comentarios` | true | Analizar también los comentarios |
| `max_comentarios` | 20 (máx. 100) | Comentarios por post |
| `refrescar` | false | Ignorar las cachés: volver a extraer y a analizar |

Respuesta real (`GET /api/analisis/jordifiallos`, 2026-10-21):

```json
{
  "usuario": "jordifiallos",
  "desde_cache": false,
  "fecha_analisis": "2026-10-22T04:49:00.003058+00:00",
  "big5_creador": {
    "apertura": 0.492, "responsabilidad": 0.348, "extraversion": 0.551,
    "amabilidad": 0.468, "neuroticismo": 0.516
  },
  "textos_analizados": 3,
  "advertencia": "Solo hay 3 textos con contenido (se recomiendan al menos 10): el resultado es poco confiable.",
  "comentarios": {
    "total_analizados": 2,
    "sentimiento": { "positivo": 0.0, "neutral": 100.0, "negativo": 0.0 },
    "emociones": { "alegria": 50.0, "tristeza": 0.0, "enojo": 0.0, "miedo": 0.0,
                   "sorpresa": 0.0, "asco": 0.0, "otros": 50.0 }
  },
  "modelos": {
    "big5": "Minej/bert-base-personality",
    "traduccion": "Helsinki-NLP/opus-mt-es-en",
    "sentimiento": "pysentimiento/robertuito-sentiment-analysis",
    "emociones": "pysentimiento/robertuito-emotion-analysis"
  },
  "nota": "Análisis exploratorio: personalidad proyectada en el contenido, no un diagnóstico."
}
```

- `big5_creador`: cada rasgo de 0 a 1, **independiente** de los demás (no suman 1). Es `null` si el
  creador no tiene ningún texto (bio y descripciones vacías o solo emojis).
- `advertencia`: aparece si hay menos de 10 textos con contenido (`ANALISIS_TEXTOS_MINIMOS`).
- `sentimiento` y `emociones`: % de comentarios (0–100) cuya etiqueta principal es cada una.
- Desde la app: `POST /api/extracciones` con `{"tipo": "analisis", "usuario": "..."}` (sección 6.3).

### Instalación (shell fish en Linux)

```fish
source venv/bin/activate.fish
pip install torch --index-url https://download.pytorch.org/whl/cpu   # torch SOLO CPU, primero
pip install -r requirements.txt
python main.py
# primera vez: abrir http://localhost:8000/api/analisis/jordifiallos y esperar la descarga
```

**La primera ejecución descarga ~1.6 GB de modelos** a `~/.cache/huggingface` (fuera del proyecto).
Las siguientes los cargan del disco en ~5 s, una sola vez por arranque de la API (carga perezosa:
la API arranca rápido y los modelos se cargan con el primer análisis).

### Limitaciones

- **Precisión modesta**: el modelo de Big Five es un BERT ajustado con un conjunto de datos pequeño
  y sin métricas publicadas. Los valores tienden a quedar cerca de 0.5 y las diferencias entre
  perfiles son pequeñas (en pruebas, un texto "muy social" sube la extraversión de ~0.50 a ~0.55).
  Sirve para comparar rasgos de forma relativa, no como medida absoluta.
- **Traducción**: el análisis de personalidad se hace sobre la traducción automática; modismos,
  sarcasmo y jerga ecuatoriana pueden perderse o cambiar de sentido.
- **Dominio distinto**: los modelos se entrenaron con ensayos/textos largos (Big Five) o tuits
  (pysentimiento), no con descripciones de TikTok, que son cortas y llenas de hashtags. Con pocos
  videos hay muy poco texto (por eso la `advertencia`).
- **Solo el creador**: lo que se mide es la personalidad *proyectada en su contenido público*
  (que puede ser un personaje o una estrategia de marketing), **no un diagnóstico** psicológico.
- **Comentarios**: solo primer nivel y hasta `max_comentarios` por video; con pocos comentarios
  los porcentajes cambian mucho (2 comentarios → solo 0 %, 50 % o 100 %).
- **Privacidad (LOPDP Ecuador)**: nunca se estima la personalidad de los comentaristas ni se devuelve
  el sentimiento de un comentario o una persona concreta: solo porcentajes agregados. Todo se
  procesa en la PC y vive en memoria (caché de 15 min), no se guarda en disco.
- **Recursos**: ~2–3 GB de RAM extra (estimado) con los modelos cargados; se procesa un análisis a la vez.
