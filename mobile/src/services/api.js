// src/services/api.js
import axios from 'axios';

// ⚠️ Cambia esta IP por la IP de tu PC en la red local
// En Windows: corre "ipconfig" en la terminal y busca "IPv4 Address"
const BASE_URL = 'http://192.168.78.172:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

export const initSession = () => api.post('/init');
export const searchTracks = (query) => api.post('/search', { query });
export const setSeeds = (trackIds) => api.post('/seeds', { track_ids: trackIds });
export const getNextBatch = (batchSize = 10) => api.get(`/next?batch_size=${batchSize}`);
export const submitFeedback = (approvedIds, rejectedIds) =>
  api.post('/feedback', { approved_ids: approvedIds, rejected_ids: rejectedIds });
export const createPlaylist = (name, isPublic = false) =>
  api.post('/create-playlist', { name, public: isPublic });
export const getStatus = () => api.get('/status');

export default api;
