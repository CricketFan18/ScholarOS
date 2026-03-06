import { useState, useEffect } from 'react';
import { api, endpoints } from '../api/client';

export function useFlashcards(documentId) {
  const [cards, setCards]       = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]       = useState(null);

  // Reset when the active document changes
  useEffect(() => {
    setCards([]);
    setError(null);
  }, [documentId]);

  const generateCards = async (topic) => {
    if (!documentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const { data } = await api.post(endpoints.flashcards, {
        document_id: documentId,
        topic:       topic.trim() || undefined,
        top_k:       8,
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