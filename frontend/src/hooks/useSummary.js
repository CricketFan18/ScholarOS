import { useState, useEffect } from 'react';
import { api, endpoints } from '../api/client';

export function useSummary(documentId) {
  const [summary, setSummary]     = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]         = useState(null);

  // Reset when the active document changes
  useEffect(() => {
    setSummary('');
    setError(null);
  }, [documentId]);

  const generateSummary = async () => {
    if (!documentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const { data } = await api.post(endpoints.summary, {
        document_id: documentId,
        top_k:       10,
      });
      setSummary(data.summary);
    } catch (err) {
      console.error('generateSummary:', err);
      setError('Failed to generate summary.');
    } finally {
      setIsLoading(false);
    }
  };

  return { summary, isLoading, error, generateSummary };
}