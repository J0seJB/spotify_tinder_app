import { Platform } from "react-native";

// Backend Python. Override with EXPO_PUBLIC_API_URL when using a physical phone.
const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  (Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000");

async function parseResponse(response, fallbackMessage) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || fallbackMessage);
  }
  return data;
}

export const API = {
  async load(limit) {
    const suffix = limit ? `?limit=${limit}` : "";
    const r = await fetch(`${BASE_URL}/load${suffix}`, { method: "POST" });
    return parseResponse(r, "No se pudo cargar la biblioteca");
  },
  async status() {
    const r = await fetch(`${BASE_URL}/status`);
    return parseResponse(r, "No se pudo leer el estado");
  },
  async search(q) {
    const r = await fetch(`${BASE_URL}/search?q=${encodeURIComponent(q)}`);
    return parseResponse(r, "No se pudo buscar");
  },
  async setSeeds(trackIds) {
    const r = await fetch(`${BASE_URL}/seeds`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_ids: trackIds }),
    });
    return parseResponse(r, "No se pudieron guardar las canciones semilla");
  },
  async getNext(count = 1) {
    const r = await fetch(`${BASE_URL}/next?count=${count}`);
    return parseResponse(r, "No se pudieron cargar sugerencias");
  },
  async getDevices() {
    const r = await fetch(`${BASE_URL}/player/devices`);
    return parseResponse(r, "No se pudieron leer los dispositivos");
  },
  async playTrack({ trackId, uri, deviceId } = {}) {
    const r = await fetch(`${BASE_URL}/player/play`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        track_id: trackId,
        uri,
        device_id: deviceId,
        transfer: true,
      }),
    });
    return parseResponse(r, "No se pudo reproducir en Spotify");
  },
  async pausePlayback(deviceId) {
    const r = await fetch(`${BASE_URL}/player/pause`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId }),
    });
    return parseResponse(r, "No se pudo pausar Spotify");
  },
  async sendFeedback(approved, rejected) {
    const r = await fetch(`${BASE_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved, rejected }),
    });
    return parseResponse(r, "No se pudo enviar tu seleccion");
  },
  async createPlaylist(name, isPublic = false) {
    const r = await fetch(`${BASE_URL}/create-playlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, public: isPublic }),
    });
    return parseResponse(r, "No se pudo crear la playlist");
  },
  async completePlaylist(targetTotal = 25) {
    const r = await fetch(`${BASE_URL}/complete-playlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_total: targetTotal }),
    });
    return parseResponse(r, "No se pudo completar la playlist");
  },
  async reset() {
    const r = await fetch(`${BASE_URL}/reset`, { method: "DELETE" });
    return parseResponse(r, "No se pudo reiniciar la sesion");
  },
};
