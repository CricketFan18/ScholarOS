import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: BASE_URL,
});

// No timeout — ingest can take several minutes on first load while embeddings initialise

export const endpoints = {
  ingest:     '/ingest',
  documents:  '/documents',
  deleteDoc:  '/documents/delete',
  flashcards: '/flashcards',
  summary:    '/summary',
  qa:         '/qa',
};

export const qaUrl = `${BASE_URL}${endpoints.qa}`;