// api.js — Conexión con el backend Python
// Cambia esta URL por la pública cuando despliegues (p. ej. https://mi-backend.up.railway.app)
const BASE_URL = "http://192.168.78.172:8000";

let ACCESS_TOKEN = null;
export function setAccessToken(token) {
  ACCESS_TOKEN = token;
}

function authHeaders(headers = {}) {
  if (ACCESS_TOKEN) {
    return { ...headers, Authorization: `Bearer ${ACCESS_TOKEN}` };
  }
  return headers;
}

export const API = {
  async load(limit = 3452) {
    const r = await fetch(`${BASE_URL}/load?limit=${limit}`, { method: "POST", headers: authHeaders() });
    return r.json();
  },
  async status() {
    const r = await fetch(`${BASE_URL}/status`, { headers: authHeaders() });
    return r.json();
  },
  async search(q) {
    const r = await fetch(`${BASE_URL}/search?q=${encodeURIComponent(q)}`, { headers: authHeaders() });
    return r.json();
  },
  async setSeeds(trackIds) {
    const r = await fetch(`${BASE_URL}/seeds`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ track_ids: trackIds }),
    });
    return r.json();
  },
  async getNext(count = 1) {
    const r = await fetch(`${BASE_URL}/next?count=${count}`, { headers: authHeaders() });
    return r.json();
  },
  async sendFeedback(approved, rejected) {
    const r = await fetch(`${BASE_URL}/feedback`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ approved, rejected }),
    });
    return r.json();
  },
  async createPlaylist(name, isPublic = false) {
    const r = await fetch(`${BASE_URL}/create-playlist`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name, public: isPublic }),
    });
    return r.json();
  },
  async reset() {
    const r = await fetch(`${BASE_URL}/reset`, { method: "DELETE", headers: authHeaders() });
    return r.json();
  },
};
