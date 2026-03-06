/**
 * hooks/useFlashcards.js
 *
 * Fetches AI-generated flashcards for a given document and optional topic.
 * Resets state automatically when the active document changes.
 */

import { useState, useEffect } from 'react';
import { api, endpoints } from '../api/client';

/**
 * @param {string|null} documentId - ID of the currently selected document.
 * @returns {{ cards, isLoading, error, generateCards }}
 */
export function useFlashcards(documentId) {
  const [cards, setCards]         = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]         = useState(null);

  // Clear stale cards and errors when the user switches documents.
  useEffect(() => {
    setCards([]);
    setError(null);
  }, [documentId]);

  /**
   * Calls the flashcards endpoint and stores the returned card objects.
   *
   * @param {string} topic - Optional focus topic; empty string means full-document coverage.
   */
  const generateCards = async (topic) => {
    if (!documentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const { data } = await api.post(endpoints.flashcards, {
        document_id: documentId,
        topic:       topic.trim() || undefined, // omit the field entirely when blank
        top_k:       8,                         // number of source chunks to consider
      });
      setCards(data.flashcards);
    } catch (err) {
      console.error('generateCards:', err);
      setError('Failed to generate flashcards.');
    } finally {
      setIsLoading(false);
    }
  };

  return { cards, isLoading, error, generateCards };
}