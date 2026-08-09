// api.js - Connection with backend Python
// Change this URL to the public backend when deployed (e.g. https://my-backend.up.railway.app)
const env = typeof process !== "undefined" ? process.env : {};
const BASE_URL = env.BACKEND_URL || env.REACT_APP_BACKEND_URL || env.EXPO_PUBLIC_BACKEND_URL || "http://localhost:8000";
const TOKEN_STORAGE_KEY = "spotify_tinder_access_token";

let ACCESS_TOKEN = null;

function loadStoredToken() {
  if (ACCESS_TOKEN || typeof window === "undefined") return;
  try {
    ACCESS_TOKEN = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    ACCESS_TOKEN = null;
  }
}

loadStoredToken();

export function setAccessToken(token) {
  ACCESS_TOKEN = token;
  if (typeof window !== "undefined") {
    try {
      if (token) {
        window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
      } else {
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      }
    } catch {
      // ignore storage errors
    }
  }
}

function authHeaders(headers = {}) {
  if (!ACCESS_TOKEN) {
    loadStoredToken();
  }
  if (ACCESS_TOKEN) {
    return { ...headers, Authorization: 'Bearer ' + ACCESS_TOKEN };
  }
  return headers;
}

export function login() {
  if (typeof window !== "undefined") {
    window.location.href = BASE_URL + "/login";
  } else {
    throw new Error("Login only supported from a browser.");
  }
}

export const API = {
  async load(limit = 3452) {
    const r = await fetch(`${BASE_URL}/load?limit=${limit}`, {
      method: "POST",
      headers: authHeaders(),
    });
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
