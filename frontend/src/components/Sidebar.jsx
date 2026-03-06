/**
 * components/Sidebar.jsx
 *
 * Left-hand navigation panel. Handles PDF uploads and lists ingested
 * documents; clicking a document makes it active across all study modes.
 */

import { useRef } from 'react';
import { Upload, FileText, Trash2, Loader2, AlertCircle } from 'lucide-react';
import { useDocuments } from '../hooks/useDocuments';

/**
 * @param {object}   props
 * @param {string|null}  props.activeDocId    - ID of the selected document.
 * @param {Function}     props.setActiveDocId - Setter lifted from App state.
 */
export default function Sidebar({ activeDocId, setActiveDocId }) {
  const {
    documents,
    isUploading,
    isFetching,
    uploadError,
    deleteError,
    uploadDocument,
    deleteDocument,
  } = useDocuments(setActiveDocId);

  // Hidden <input type="file"> — triggered programmatically by the upload button
  // so we can style the button freely without wrestling with native file-input styling.
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    uploadDocument(e.target.files[0]);
    // Reset the input so the same file can be re-uploaded if needed.
    e.target.value = null;
  };

  return (
    <div className="w-72 bg-slate-900 text-slate-300 flex flex-col h-full border-r border-slate-800 shadow-xl z-20">
      {/* ── Branding ─────────────────────────────────────────────────── */}
      <div className="p-6 border-b border-slate-800">
        <h1 className="text-2xl font-bold text-white tracking-tight">ScholarOS</h1>
        <p className="text-sm text-slate-400 mt-1 font-medium">Local AI Engine</p>
      </div>

      {/* ── Upload button ────────────────────────────────────────────── */}
      <div className="p-5">
        {/* Accepts PDFs only; the backend's ingest endpoint handles chunking + embedding. */}
        <input
          type="file"
          accept=".pdf"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileInputRef.current.click()}
          disabled={isUploading}
          className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-3 rounded-xl transition-all shadow-md disabled:opacity-50 font-medium"
        >
          {isUploading
            ? <Loader2 className="w-5 h-5 animate-spin" />
            : <Upload className="w-5 h-5" />}
          {isUploading ? 'Processing PDF…' : 'Upload New PDF'}
        </button>

        {uploadError && (
          <div className="mt-3 text-xs text-red-400 flex items-center gap-1 bg-red-400/10 p-2 rounded">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {uploadError}
          </div>
        )}
        {deleteError && (
          <div className="mt-3 text-xs text-red-400 flex items-center gap-1 bg-red-400/10 p-2 rounded">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {deleteError}
          </div>
        )}
      </div>

      {/* ── Document list ────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 px-3">
          Your Library
        </h2>

        {/* Skeleton placeholders while the first fetch is in-flight */}
        {isFetching && documents.length === 0 && (
          <div className="space-y-2 px-3">
            {[...Array(3)].map((_, i) => (
              <div
                key={i}
                className="h-10 rounded-xl bg-slate-800 animate-pulse"
                // Fade skeletons so they feel like they're receding into the background.
                style={{ opacity: 1 - i * 0.25 }}
              />
            ))}
          </div>
        )}

        {documents.map((doc) => {
          const isActive = activeDocId === doc.id;
          return (
            <div
              key={doc.id}
              role="button"
              tabIndex={0}
              onClick={() => setActiveDocId(doc.id)}
              // Keyboard accessibility: Enter and Space mimic a click.
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setActiveDocId(doc.id)}
              aria-pressed={isActive}
              className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                isActive
                  ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
                  : 'hover:bg-slate-800 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3 overflow-hidden min-w-0">
                <FileText
                  className={`w-4 h-4 shrink-0 ${isActive ? 'text-indigo-400' : 'text-slate-500'}`}
                />
                {/* truncate prevents long filenames from overflowing the sidebar */}
                <span className="truncate text-sm font-medium">{doc.name}</span>
              </div>

              <button
                onClick={(e) => {
                  // Stop propagation so clicking delete doesn't also select the document.
                  e.stopPropagation();
                  deleteDocument(doc.id, activeDocId);
                }}
                onKeyDown={(e) => e.stopPropagation()}
                aria-label={`Delete ${doc.name}`}
                // Hidden by default; revealed on row hover to keep the list uncluttered.
                className="p-1.5 hover:bg-red-500/20 hover:text-red-400 rounded-md transition-colors shrink-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-red-400 outline-none"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          );
        })}

        {!isFetching && documents.length === 0 && (
          <div className="text-sm text-center text-slate-500 mt-10 px-4">
            <FileText className="w-8 h-8 mx-auto mb-3 opacity-20" />
            Your library is empty.
          </div>
        )}
      </div>
    </div>
  );
}