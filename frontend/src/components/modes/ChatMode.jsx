import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, AlertCircle, Trash2 } from 'lucide-react';
import { useStreamChat } from '../../hooks/useStreamChat';
import MarkdownRenderer from '../common/MarkdownRenderer';

export default function ChatMode({ activeDocId }) {
  const [input, setInput] = useState('');
  const { messages, isTyping, error, sendMessage, clearChat } = useStreamChat(activeDocId);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Clear chat whenever the document changes; clearChat is stable (useCallback)
  useEffect(() => {
    clearChat();
  }, [activeDocId, clearChat]);

  // Only scroll when there are messages — avoids no-op on mount
  useEffect(() => {
    if (messages.length > 0) scrollToBottom();
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    sendMessage(input);
    setInput('');
  };

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-400 select-none">
            Ask a complex question about your document.
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
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

                <div
                  className={`max-w-[80%] p-5 rounded-2xl shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-tr-none'
                      : 'bg-white border border-slate-200 text-slate-800 rounded-tl-none'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <MarkdownRenderer content={msg.content} />
                  )}
                </div>
              </div>
            ))}

            {/* Clear chat button — only visible when there are messages */}
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

        <div ref={messagesEndRef} />

        {error && (
          <div className="flex items-center gap-2 text-red-500 bg-red-50 p-4 rounded-lg mx-auto max-w-md justify-center">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span className="text-sm font-medium">{error}</span>
          </div>
        )}
      </div>

      {/* Input bar */}
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