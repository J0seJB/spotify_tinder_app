# Spotify AI Playlist Builder

Organiza tus **Me Gusta** de Spotify en playlists con ayuda de IA.

## Características

- **Playlist Inteligente (nuevo)** — añade unas pocas canciones semilla, la IA detecta tu vibe y añade automáticamente canciones similares de tus Me Gusta. Claude AI describe el perfil musical y sugiere un nombre creativo para la playlist.
- Descubrimiento automatico de categorias desde tus Me Gusta con Last.fm.
- Clasificacion fija legacy en 12 categorias personalizadas (multi-label).
- Vistas dinámicas por reglas en JSON.
- Clustering (HDBSCAN / KMeans) para descubrir micro-grupos.
- Export a CSV con features, géneros y categorías.

## Instalación

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copia `.env.example` a `.env` y rellena tus credenciales:

```
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://localhost:8000/callback
FRONTEND_URL=http://localhost:19006
BACKEND_URL=http://localhost:8000
SPOTIFY_USERNAME=tu_usuario

# Para el análisis IA con Claude:
ANTHROPIC_API_KEY=...

# Requerido para categorias dinamicas y similitud:
LASTFM_API_KEY=...
```

## App Web y despliegue

El backend se ejecuta con FastAPI y el frontend es una app Expo Web.

### Ejecutar localmente

1. Inicia el backend:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

2. En otra terminal, instala y arranca el frontend:

```bash
cd frontend
npm install
npm run start
```

3. Abre la web en `http://localhost:19006`.

### Desplegar en Render + Vercel

El backend usa `render.yaml` y `requirements-web.txt` para desplegar únicamente las dependencias necesarias para la API, sin instalar los paquetes pesados usados por los scripts locales de análisis.

1. En Render, crea un **Blueprint** desde este repositorio. Render detectará `render.yaml` y creará el servicio web gratuito `spotify-tinder-api`.
2. En el servicio de Render, configura estas variables de entorno:
  - `SPOTIFY_CLIENT_ID`
  - `SPOTIFY_CLIENT_SECRET`
  - `SPOTIFY_REDIRECT_URI=https://<TU_SERVICIO>.onrender.com/callback`
  - `FRONTEND_URL=https://<TU_DOMINIO_VERCEL>` (incluye `https://`, sin rutas ni fragmentos)
3. Añade exactamente `SPOTIFY_REDIRECT_URI` a la lista **Redirect URIs** de tu aplicación en Spotify Developer Dashboard y guarda los cambios.
4. En Vercel, conserva el frontend y configura `EXPO_PUBLIC_BACKEND_URL=https://<TU_SERVICIO>.onrender.com`; luego vuelve a desplegar el frontend.

En Vercel, el comando de build es:

```bash
npm run build
```

> Nota: el repo está configurado con `vercel.json` para que Vercel use automáticamente la carpeta `frontend` como la aplicación web.

Render comprueba la salud del servicio mediante `/status` y lo inicia con:

```bash
uvicorn api:app --host 0.0.0.0 --port $PORT
```

> El plan gratuito de Render puede suspender el backend tras un periodo sin tráfico; la primera solicitud posterior puede tardar alrededor de un minuto. No uses el sistema de archivos local del servicio para guardar datos permanentes.

En la pantalla de semillas puedes recorrer tu biblioteca guardada o buscar canciones en todo Spotify. El reproductor integrado de Spotify permite escuchar las pistas disponibles mientras eliges; su disponibilidad y duración dependen de Spotify y de tu cuenta.

La biblioteca y el progreso de selección de cada usuario se mantienen separados por su token de sesión. En el plan actual, el estado se guarda en memoria en la instancia del backend y se reinicia cuando Render reinicia o redepliega el servicio.

> ⚠️ **Importante**: Obtén credenciales nuevas de Spotify en https://developer.spotify.com/dashboard
> Las credenciales que tenías en el .env anterior estaban expuestas — debes regenerarlas.

## Uso

### Categorias dinamicas desde tus Me Gusta

Este es el flujo recomendado. Spotify se usa para leer tus Me Gusta, artistas, generos y crear playlists; Last.fm se usa para tags, mood y similitud musical.

```bash
python main.py --discover-categories --limit 1000
```

El programa genera:

- `export/tracks_with_lfm.csv`: canciones enriquecidas con tags y features aproximadas de Last.fm.
- `export/generated_categories.json`: categorias descubiertas desde tu biblioteca.
- `export/tracks_with_features.csv`: alias compatible para `views.py` y `cluster.py`.

Para crear playlists automaticamente:

```bash
python main.py --discover-categories --create --yes --target-categories 12
```

Para usar Genius como senal adicional de letras:

```bash
python main.py --discover-categories --use-genius --max-genius-tracks 100 --target-categories 18
```

### 🎵 Playlist Inteligente (modo IA)

```bash
python main.py --smart-playlist "Mi tarde chill" --limit 500
```

El programa:
1. Descarga tus Me Gusta
2. Te muestra un buscador para elegir canciones semilla
3. Analiza tu perfil musical (tempo, energía, bailabilidad, géneros)
4. Claude AI describe el vibe y sugiere un nombre creativo
5. Añade automáticamente las canciones más similares de tus Me Gusta
6. Crea la playlist en Spotify

Opciones útiles:
```bash
# Sin llamar a Claude (solo Last.fm + generos/artistas)
python main.py --smart-playlist "Viernes noche" --no-ai

# Más sugerencias (por defecto 30)
python main.py --smart-playlist "Workout" --top-n 50

# Solo ver qué sugeriría, sin crear la playlist
python main.py --smart-playlist "Test" --dry-run

# Playlist pública
python main.py --smart-playlist "Mi vibe" --public
```

### 📂 Clasificación por categorías (modo clásico)

```bash
# Solo clasificar y exportar CSV (sin crear playlists)
python main.py --dry-run --limit 200

# Crear/actualizar playlists por categorías
python main.py --create --yes --public
```

### 🔀 Clustering

```bash
python cluster.py --dry-run --limit 3000 --algo hdbscan
python cluster.py --create --algo kmeans --k 15
```

### 📋 Vistas dinámicas

Edita `config/views.json` para definir playlists por reglas:

```bash
python views.py --create --public
```

## Estructura del proyecto

```
spotify_ai/
├── main.py              # Punto de entrada principal
├── dynamic_categories.py # Descubrimiento automatico con Last.fm
├── ai_playlist.py       # Motor IA: similitud + Claude API
├── spotify_client.py    # Cliente Spotify compartido (sin duplicados)
├── utils.py             # Perfiles de categorías y scoring
├── views.py             # Playlists por reglas (corregido)
├── cluster.py           # Clustering HDBSCAN/KMeans
├── config/
│   └── views.json       # Definición de vistas dinámicas
├── export/              # CSVs exportados (generado automáticamente)
├── .env.example         # Plantilla de variables de entorno
└── requirements.txt
```

## Cómo funciona la IA

La deteccion de gustos usa Last.fm como fuente principal porque Spotify no es una fuente confiable para descargar audio features en este flujo:

1. **Perfil semilla**: convierte tags de Last.fm en senales aproximadas como energia, valencia, baile, acustico e instrumental.
2. **Scoring de candidatos**: combina similitud directa de Last.fm, similitud por tags, overlap de generos de Spotify y artistas compartidos.
3. **Categorias dinamicas**: agrupa tus Me Gusta con clustering sobre tags, generos y artistas, y nombra cada grupo automaticamente.
4. **Claude AI opcional**: recibe el perfil y genera nombres/descripciones mas naturales.
