# Spotify AI Playlist Builder

Organiza tus Me Gusta de Spotify en playlists con ayuda de IA.

## Caracteristicas

- Playlist inteligente: eliges unas canciones semilla y la app sugiere canciones similares de tus Me Gusta.
- Descubrimiento automatico de categorias con Last.fm.
- Clasificacion fija legacy en categorias personalizadas.
- Vistas dinamicas por reglas en JSON.
- Clustering con HDBSCAN o KMeans.
- Exportacion a CSV con features, generos y categorias.
- App movil Expo/React Native con flujo tipo swipe y control por Spotify Connect.

## Instalacion backend

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copia `.env.example` a `.env` y rellena tus credenciales:

```env
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://127.0.0.1:9090/callback
SPOTIFY_USERNAME=tu_usuario
ANTHROPIC_API_KEY=...
LASTFM_API_KEY=...
GENIUS_TOKEN=...
```

Importante: si tus credenciales de Spotify fueron compartidas o subidas por error, regenerarlas en el dashboard de Spotify.

## Ejecutar backend

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Verificacion rapida:

```bash
curl http://localhost:8000/
```

Debe responder:

```json
{"status":"ok"}
```

## Verificar proyecto

Compilacion rapida de los modulos Python principales:

```bash
python -m compileall -q api.py ai_playlist.py spotify_client.py main.py dynamic_categories.py genius_client.py lastfm_client.py cluster.py views.py utils.py
```

Pruebas de humo del backend, sin llamar a Spotify:

```bash
python -m pytest
```

## Ejecutar app movil

```bash
cd frontend
npm install
npm start
```

Por defecto, Android Emulator usa `http://10.0.2.2:8000` para llegar al backend del PC. Para un telefono fisico en la misma red, usa la IP local de tu PC:

```bash
$env:EXPO_PUBLIC_API_URL="http://TU_IP_LOCAL:8000"
npm start
```

## Ejecutar app web

La misma app Expo tambien corre en navegador con React Native Web.

```bash
cd frontend
npm install
npm run web
```

Para generar una build estatica web:

```bash
cd frontend
npm run build:web
```

La salida queda en:

```text
frontend/dist-web
```

Para servirla localmente:

```bash
cd frontend/dist-web
python -m http.server 8088
```

Luego abre:

```text
http://localhost:8088/
```

## Compilar APK debug

El proyecto nativo Android usa `frontend/android/local.properties` para ubicar el SDK local.

```bash
cd frontend/android
$env:NODE_ENV="production"
.\gradlew.bat app:assembleDebug -x lint -x test --configure-on-demand --build-cache
```

APK generado:

```text
frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

## Uso CLI

Categorias dinamicas desde tus Me Gusta:

```bash
python main.py --discover-categories --limit 1000
```

Crear playlists automaticamente:

```bash
python main.py --discover-categories --create --yes --target-categories 12
```

Playlist inteligente:

```bash
python main.py --smart-playlist "Mi tarde chill" --limit 500
```

Clustering:

```bash
python cluster.py --dry-run --limit 3000 --algo hdbscan
python cluster.py --create --algo kmeans --k 15
```

Vistas dinamicas:

```bash
python views.py --create --public
```

## Estructura

```text
spotify_tinder_app/
  api.py                  Backend FastAPI
  main.py                 Punto de entrada CLI
  ai_playlist.py          Motor de similitud e IA
  spotify_client.py       Cliente Spotify compartido
  dynamic_categories.py   Descubrimiento automatico
  views.py                Playlists por reglas
  cluster.py              Clustering
  config/views.json       Definicion de vistas
  frontend/               App Expo/React Native
  export/                 CSV y JSON generados
  tests/                  Pruebas de humo
```
