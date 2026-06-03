# Roadmap

## Proximas mejoras

### 1. Autocompletar playlist desde señales aprendidas

Agregar un flujo para completar automaticamente la playlist cuando el usuario ya dio suficientes señales.

Criterios:
- Mostrar `Completar playlist` solo cuando haya suficiente señal.
- Usar semillas, canciones aprobadas y ranking restante.
- Exponer un endpoint tipo `POST /complete` con tamaño objetivo.
- Mostrar una vista de resumen antes de crear la playlist.

### 2. Autoplay al pasar a la siguiente sugerencia

Agregar un modo para reproducir automaticamente la siguiente carta despues de cada swipe.

Criterios:
- Control visible para activar/desactivar autoplay.
- Si el usuario pausa manualmente, autoplay se apaga o queda pausado.
- Manejar errores de Spotify Connect sin reintentos infinitos.

### 3. Barra interactiva de progreso

Agregar barra para ver y cambiar la posicion de la cancion actual.

Criterios:
- Backend con `GET /player/current`.
- Backend con `POST /player/seek`.
- Frontend muestra tiempo actual y duracion.
- El usuario puede adelantar o retroceder desde la tarjeta.

### 4. Modo descubrir musica nueva

Permitir recomendar canciones fuera de los Me gusta del usuario.

Criterios:
- Selector entre `Mis Me gusta` y `Descubrir musica nueva`.
- Busqueda global de semillas en Spotify.
- Recomendaciones con Last.fm/Spotify Search.
- Excluir semillas y opcionalmente canciones ya guardadas.

### 5. Base de datos y cache persistente

Reemplazar progresivamente el cache en memoria por persistencia real.

Criterios:
- Guardar tracks, artistas, imagenes, tags Last.fm y analisis reusable.
- Separar datos globales de datos por usuario/sesion.
- Reutilizar datos cacheados para acelerar cargas.
- Reducir dependencia de `_cache` como fuente principal.

### 6. OAuth multiusuario y sesiones por usuario

Convertir el backend de sesion unica local a multiusuario.

Criterios:
- Endpoints de login/callback/logout.
- Tokens OAuth por usuario.
- Flujos `/load`, `/search`, `/seeds`, `/next`, `/feedback` y `/create-playlist` por sesion.
- Evitar una sola variable global `_cache` para todos los usuarios.

### 7. Motor IA de recomendacion y aprendizaje continuo

Crear un motor de recomendacion mas robusto que combine metadata musical, letras, artistas, generos, tags, idioma, mood y feedback por swipe.

Criterios:
- Analizar canciones con senales persistentes: artistas, generos, tags Last.fm, temas de letras, idioma, mood y energia aproximada.
- Guardar embeddings o vectores de descripcion musical para comparar canciones por significado, no solo por artista/genero.
- Construir un perfil vivo por sesion con likes y rechazos.
- Recalcular el ranking despues de cada swipe usando similitud a likes, distancia a rechazos, balance por semillas y diversidad de artistas.
- Penalizar repeticion excesiva de artistas o estilos dominantes.
- Reutilizar analisis guardado en base de datos para acelerar futuras sesiones y testers.
