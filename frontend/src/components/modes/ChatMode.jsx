/**
 * components/modes/ChatMode.jsx
 *
 * Streaming Q&A chat interface. Renders a scrollable message history,
 * streams assistant responses token-by-token via useStreamChat, and
 * provides a text input bar at the bottom.
 */

import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, AlertCircle, Trash2 } from 'lucide-react';
import { useStreamChat } from '../../hooks/useStreamChat';
import MarkdownRenderer from '../common/MarkdownRenderer';

/**
 * @param {object}      props
 * @param {string|null} props.activeDocId - ID of the currently selected document.
 */
export default function ChatMode({ activeDocId }) {
  const [input, setInput] = useState('');
  const { messages, isTyping, error, sendMessage, clearChat } = useStreamChat(activeDocId);

  // Ref attached to an invisible div at the bottom of the message list —
  // calling scrollIntoView on it keeps the latest message visible.
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Reset conversation whenever the user switches to a different document.
  // clearChat is wrapped in useCallback so this effect doesn't re-run unnecessarily.
  useEffect(() => {
    clearChat();
  }, [activeDocId, clearChat]);

  // Auto-scroll on every new message or token. Guard prevents a no-op scroll on first mount.
  useEffect(() => {
    if (messages.length > 0) scrollToBottom();
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;

    // Pass `messages` explicitly so sendMessage has the current history without
    // relying on a closure capture (which would read a stale value if React
    // batches the state update from the previous setMessages call).
    sendMessage(input, messages);
    setInput('');
  };

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* ── Message list ─────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-400 select-none">
            Ask a question about your document.
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => (
              // User messages are right-aligned via flex-row-reverse; assistant left-aligned.
              <div
                key={idx}
                className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                {/* Avatar */}
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-emerald-500 text-white'
                  }`}
                >
                  {msg.role === 'user'
                    ? <User className="w-5 h-5" />
                    : <Bot className="w-5 h-5" />}
                </div>

                {/* Bubble */}
                <div
                  className={`max-w-[80%] p-5 rounded-2xl shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-tr-none'
                      : 'bg-white border border-slate-200 text-slate-800 rounded-tl-none'
                  }`}
                >
                  {/* User text is plain; assistant text may contain markdown. */}
                  {msg.role === 'user' ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <MarkdownRenderer content={msg.content} />
                  )}
                </div>
              </div>
            ))}

            {/* Clear button — only rendered when there is something to clear */}
            <div className="flex justify-center pt-2">
              <button
                onClick={clearChat}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-600 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear conversation
              </button>
            </div>
          </>
        )}

        {/* Invisible anchor used by scrollToBottom */}
        <div ref={messagesEndRef} />

        {error && (
          <div className="flex items-center gap-2 text-red-500 bg-red-50 p-4 rounded-lg mx-auto max-w-md justify-center">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span className="text-sm font-medium">{error}</span>
          </div>
        )}
      </div>

      {/* ── Input bar ────────────────────────────────────────────────── */}
      <div className="p-4 bg-white border-t border-slate-200 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
        <form
          onSubmit={handleSubmit}
          className="flex gap-3 max-w-4xl mx-auto"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!activeDocId || isTyping}
            placeholder={isTyping ? 'ScholarOS is thinking…' : 'Type your question…'}
            className="flex-1 px-5 py-4 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-slate-50 transition-all text-slate-700 shadow-sm"
          />
          <button
            type="submit"
            disabled={!activeDocId || isTyping || !input.trim()}
            className="bg-indigo-600 text-white px-6 py-4 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center gap-2 shadow-sm"
            aria-label="Send message"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
}