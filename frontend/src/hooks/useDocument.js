import { useState, useEffect, useCallback, useRef } from 'react';
import { api, endpoints } from '../api/client';

const DOC_NAMES_KEY = 'scholaros:doc_names';

function loadNameMap() {
  try {
    return JSON.parse(localStorage.getItem(DOC_NAMES_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveNameMap(map) {
  try {
    localStorage.setItem(DOC_NAMES_KEY, JSON.stringify(map));
  } catch { /* ignore quota errors */ }
}

export function useDocuments(setActiveDocId) {
  const [documents, setDocuments]     = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [isFetching, setIsFetching]   = useState(false);
  const hasFetched                    = useRef(false);

  const fetchDocuments = useCallback(async () => {
    setIsFetching(true);
    try {
      const { data } = await api.get(endpoints.documents);
      const nameMap  = loadNameMap();
      // Hydrate display names from localStorage; fall back to id
      const docs = (data.documents || []).map(doc => ({
        ...doc,
        name: nameMap[doc.id] || doc.name || doc.id,
      }));
      setDocuments(docs);
    } catch (err) {
      console.error('fetchDocuments:', err);
      setUploadError('Failed to load library.');
    } finally {
      setIsFetching(false);
    }
  }, []);

  useEffect(() => {
    if (!hasFetched.current) {
      hasFetched.current = true;
      fetchDocuments();
    }
  }, [fetchDocuments]);

  const uploadDocument = async (file) => {
    if (!file) return;
    setIsUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const { data } = await api.post(endpoints.ingest, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      // Persist human-readable name locally
      const nameMap = loadNameMap();
      nameMap[data.document_id] = data.name || file.name;
      saveNameMap(nameMap);

      setActiveDocId(data.document_id);
      await fetchDocuments();
    } catch (err) {
      console.error('uploadDocument:', err);
      setUploadError('Upload failed. Check backend connection.');
    } finally {
      setIsUploading(false);
    }
  };

  const deleteDocument = async (id, currentActiveId) => {
    setDeleteError(null);
    try {
      await api.post(endpoints.deleteDoc, { document_id: id });

      // Remove from local name cache
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