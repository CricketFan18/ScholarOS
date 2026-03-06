/**
 * hooks/useSummary.js
 *
 * Fetches an AI-generated executive summary for the selected document.
 * Resets state automatically when the active document changes.
 */

import { useState, useEffect } from 'react';
import { api, endpoints } from '../api/client';

/**
 * @param {string|null} documentId - ID of the currently selected document.
 * @returns {{ summary, isLoading, error, generateSummary }}
 */
export function useSummary(documentId) {
  const [summary, setSummary]     = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]         = useState(null);

  // Clear stale summary and errors when the user switches documents.
  useEffect(() => {
    setSummary('');
    setError(null);
  }, [documentId]);

  /** Calls the summary endpoint and stores the returned markdown string. */
  const generateSummary = async () => {
    if (!documentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const { data } = await api.post(endpoints.summary, {
        document_id: documentId,
        top_k:       10, // number of document chunks to include as context
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