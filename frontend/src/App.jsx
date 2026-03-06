/**
 * App.jsx
 *
 * Root component. Owns the two pieces of top-level state shared across the
 * whole application: which document is active and which study mode is open.
 * Everything else is handled by Sidebar and the three mode components.
 */

import { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatMode from './components/modes/ChatMode';
import FlashcardMode from './components/modes/FlashcardMode';
import SummaryMode from './components/modes/SummaryMode';
import { MessageSquare, Layers, FileText } from 'lucide-react';

const TABS = [
  { id: 'chat',       label: 'Q&A Chat',   icon: MessageSquare },
  { id: 'flashcards', label: 'Flashcards', icon: Layers },
  { id: 'summary',    label: 'Summary',    icon: FileText },
];

export default function App() {
  const [activeDocId, setActiveDocId] = useState(null);
  const [activeTab, setActiveTab]     = useState('chat');

  return (
    <div className="flex h-screen w-full bg-slate-50 overflow-hidden font-sans">
      <Sidebar activeDocId={activeDocId} setActiveDocId={setActiveDocId} />

      <main className="flex-1 flex flex-col h-full relative overflow-hidden">
        {/* Overlay rendered on top of everything when no document is selected.
            backdrop-blur gives a frosted-glass effect over the tab content beneath. */}
        {!activeDocId && (
          <div className="absolute inset-0 z-10 bg-slate-50/80 backdrop-blur-sm flex items-center justify-center">
            <div className="bg-white p-8 rounded-2xl shadow-lg text-center max-w-md border border-slate-200">
              <h2 className="text-2xl font-bold text-slate-800 mb-2">Welcome to ScholarOS</h2>
              <p className="text-slate-600">
                Upload or select a document from the sidebar to begin studying.
              </p>
            </div>
          </div>
        )}

        {/* ── Tab bar ──────────────────────────────────────────────────── */}
        <div className="bg-white border-b border-slate-200 px-6 py-4 flex gap-4 shrink-0">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTab === id
                  ? 'bg-indigo-50 text-indigo-700'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <Icon className="w-5 h-5" />
              {label}
            </button>
          ))}
        </div>

        {/*
          key={activeDocId} forces a full unmount+remount of the active mode
          whenever the document changes. This is a deliberate escape hatch: it
          clears all local state (messages, cards, summary) in a single operation
          rather than threading reset logic through every child hook.
        */}
        <div key={activeDocId} className="flex-1 overflow-hidden">
          {activeTab === 'chat'       && <ChatMode      activeDocId={activeDocId} />}
          {activeTab === 'flashcards' && <FlashcardMode activeDocId={activeDocId} />}
          {activeTab === 'summary'    && <SummaryMode   activeDocId={activeDocId} />}
        </div>
      </main>
    </div>
  );
}