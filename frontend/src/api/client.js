/**
 * api/client.js
 *
 * Central HTTP client configuration and endpoint registry.
 * All modules import `api` (axios instance) or `endpoints` from here
 * so base URL and future auth headers only need to change in one place.
 */

import axios from 'axios';

// Falls back to localhost when VITE_API_URL is not set (e.g. local dev without a .env file).
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/** Pre-configured axios instance — use this for all JSON requests. */
export const api = axios.create({
  baseURL: BASE_URL,
});

/**
 * Relative path registry for every backend route.
 * Resolved against BASE_URL by the axios instance above (or manually via qaUrl below).
 */
export const endpoints = {
  ingest:     '/ingest',       // POST: upload + embed a PDF
  documents:  '/documents',    // GET:  list all ingested documents
  deleteDoc:  '/documents/delete',
  flashcards: '/flashcards',   // POST: generate flashcard deck
  summary:    '/summary',      // POST: generate executive summary
  qa:         '/qa',           // POST (SSE): streaming Q&A
};

/**
 * Absolute URL for the QA streaming endpoint.
 *
 * The Q&A route uses the Fetch API (not axios) because axios does not natively
 * support SSE/ReadableStream responses — we need `res.body.getReader()`.
 */
export const qaUrl = `${BASE_URL}${endpoints.qa}`;