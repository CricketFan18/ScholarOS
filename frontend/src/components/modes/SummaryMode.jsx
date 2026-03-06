/**
 * components/modes/SummaryMode.jsx
 *
 * On-demand document summarisation panel. Renders an AI-generated executive
 * summary as formatted markdown, with a button to generate or regenerate it.
 */

import { FileText, Loader2, AlertCircle } from 'lucide-react';
import { useSummary } from '../../hooks/useSummary';
import MarkdownRenderer from '../common/MarkdownRenderer';

/**
 * @param {object}      props
 * @param {string|null} props.activeDocId - ID of the currently selected document.
 */
export default function SummaryMode({ activeDocId }) {
  const { summary, isLoading, error, generateSummary } = useSummary(activeDocId);

  return (
    <div className="h-full flex flex-col p-6 bg-slate-50">
      {/* ── Header row ───────────────────────────────────────────────── */}
      <div className="flex justify-between items-center mb-6 max-w-5xl mx-auto w-full">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 tracking-tight">Executive Summary</h2>
          <p className="text-slate-500 text-sm mt-1">AI-generated overview of the document's key points.</p>
        </div>
        <button
          onClick={generateSummary}
          disabled={isLoading || !activeDocId}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 font-medium shadow-sm transition-all"
        >
          {isLoading
            ? <Loader2 className="w-5 h-5 animate-spin" />
            : <FileText className="w-5 h-5" />}
          {/* Label reflects whether a summary already exists. */}
          {summary ? 'Regenerate Summary' : 'Generate Summary'}
        </button>
      </div>

      {/* ── Content area ─────────────────────────────────────────────── */}
      <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm p-8 overflow-y-auto max-w-5xl mx-auto w-full">
        {error && (
          <div className="mb-6 flex items-center gap-2 text-red-600 bg-red-50 p-4 rounded-lg">
            <AlertCircle className="w-5 h-5 shrink-0" />
            {error}
          </div>
        )}

        {summary ? (
          <MarkdownRenderer content={summary} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 space-y-4">
            <FileText className="w-16 h-16 opacity-20" />
            <p>Click generate to create a high-level summary of the selected document.</p>
          </div>
        )}
      </div>
    </div>
  );
}