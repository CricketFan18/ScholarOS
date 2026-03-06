/**
 * hooks/useDocuments.js
 *
 * Manages the user's document library: fetching the list from the backend,
 * uploading new PDFs, and deleting existing ones.
 * 
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { api, endpoints } from '../api/client';

const DOC_NAMES_KEY = 'scholaros:doc_names';

/** Loads the { [docId]: displayName } map from localStorage. Returns {} on parse failure. */
function loadNameMap() {
  try {
    return JSON.parse(localStorage.getItem(DOC_NAMES_KEY) || '{}');
  } catch {
    return {};
  }
}

/** Persists the name map back to localStorage, silently ignoring quota errors. */
function saveNameMap(map) {
  try {
    localStorage.setItem(DOC_NAMES_KEY, JSON.stringify(map));
  } catch { /* ignore quota errors */ }
}

/**
 * @param {Function} setActiveDocId - App-level setter; called here when the
 *   active document is deleted so the main panel resets to the empty state.
 */
export function useDocuments(setActiveDocId) {
  const [documents, setDocuments]     = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [isFetching, setIsFetching]   = useState(false);

  // Prevents a double-fetch in React StrictMode (which mounts effects twice in dev).
  const hasFetched = useRef(false);

  /** Fetches the document list and hydrates display names from localStorage. */
  const fetchDocuments = useCallback(async () => {
    setIsFetching(true);
    try {
      const { data } = await api.get(endpoints.documents);
      const nameMap  = loadNameMap();
      // Prefer the backend-provided name (stored at ingest time); fall back to
      // the locally cached name, then the raw ID. The local cache exists as a
      // belt-and-suspenders guard in case the backend loses the display_name.
      const docs = (data.documents || []).map(doc => ({
        ...doc,
        name: doc.name || nameMap[doc.id] || doc.id,
      }));
      setDocuments(docs);
    } catch (err) {
      console.error('fetchDocuments:', err);
      setUploadError('Failed to load library. Is the backend running?');
    } finally {
      setIsFetching(false);
    }
  }, []);

  // Fetch once on mount.
  useEffect(() => {
    if (!hasFetched.current) {
      hasFetched.current = true;
      fetchDocuments();
    }
  }, [fetchDocuments]);

  /**
   * Uploads a PDF file to the ingest endpoint, stores its display name
   * locally, then refreshes the document list.
   *
   * @param {File} file - The PDF file selected by the user.
   */
  const uploadDocument = async (file) => {
    if (!file) return;
    setIsUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const { data } = await api.post(endpoints.ingest, formData, {
        // Let the browser set the Content-Type boundary automatically.
        // Manually setting 'multipart/form-data' omits the boundary string
        // and causes the backend to reject the request with a 422.
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      // Cache the human-readable filename locally as a fallback.
      const nameMap = loadNameMap();
      nameMap[data.document_id] = data.name || file.name;
      saveNameMap(nameMap);

      // Auto-select the newly uploaded document so the main panel activates immediately.
      setActiveDocId(data.document_id);
      await fetchDocuments();
    } catch (err) {
      console.error('uploadDocument:', err);
      const status = err.response?.status;
      if (status === 413) {
        setUploadError('File too large (max 50 MB).');
      } else if (status === 422) {
        setUploadError('No text found in PDF — is it a scanned image?');
      } else if (status === 400) {
        setUploadError('Only PDF files are supported.');
      } else {
        setUploadError('Upload failed. Check the backend connection.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  /**
   * Deletes a document from the backend and removes its name from localStorage.
   * If the deleted document was active, resets the selection to null.
   *
   * @param {string} id              - ID of the document to delete.
   * @param {string} currentActiveId - The currently active document ID.
   */
  const deleteDocument = async (id, currentActiveId) => {
    setDeleteError(null);
    try {
      await api.post(endpoints.deleteDoc, { document_id: id });

      const nameMap = loadNameMap();
      delete nameMap[id];
      saveNameMap(nameMap);

      if (currentActiveId === id) setActiveDocId(null);
      await fetchDocuments();
    } catch (err) {
      console.error('deleteDocument:', err);
      setDeleteError('Failed to delete document.');
    }
  };

  return {
    documents,
    isUploading,
    isFetching,
    uploadError,
    deleteError,
    uploadDocument,
    deleteDocument,
  };
}