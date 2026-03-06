/**
 * hooks/useStreamChat.js
 *
 * Manages a streaming Q&A conversation with the backend.
 *
 * The backend sends responses as Server-Sent Events (SSE). Each event carries
 * a text fragment; we accumulate them into the last assistant message so the
 * UI updates token-by-token without waiting for the full response.
 *
 * Why Fetch instead of axios?
 * axios buffers the entire response before resolving, which defeats streaming.
 * The native Fetch API exposes `response.body` as a ReadableStream, letting us
 * read data incrementally via `getReader()`.
 */

import { useState, useCallback } from 'react';
import { qaUrl } from '../api/client';

/**
 * @param {string|null} documentId - ID of the document to query against.
 * @returns {{ messages, isTyping, error, sendMessage, clearChat }}
 */
export function useStreamChat(documentId) {
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError]       = useState(null);

  /**
   * Sends a user query and streams the assistant's reply into state.
   *
   * The full conversation history is forwarded to the backend on every turn
   * so the model can resolve follow-up questions like "explain that further"
   * correctly. Without this, every message is answered without context.
   *
   * @param {string} query    - The user's question.
   * @param {Array}  history  - Current messages array at call time (passed in
   *                            to avoid a stale-closure read of `messages`).
   */
  const sendMessage = async (query, history) => {
    const trimmed = query.trim();
    if (!trimmed || !documentId) return;

    // Append the user's message immediately for instant UI feedback.
    const userMessage = { role: 'user', content: trimmed };
    setMessages(prev => [...prev, userMessage]);
    setIsTyping(true);
    setError(null);

    // Build the history array to send: all prior turns, NOT including the
    // message we just appended above (the backend adds it via `user_input`).
    const historyPayload = (history || []).map(({ role, content }) => ({ role, content }));

    try {
      const res = await fetch(qaUrl, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          question:    trimmed,
          document_id: documentId,
          top_k:       5,
          history:     historyPayload, // ← multi-turn context
        }),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail || `Server error ${res.status}`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder('utf-8');

      // `buffer` persists across loop iterations so that an SSE event split
      // across multiple TCP packets is reassembled correctly before parsing.
      let buffer = '';

      // Seed an empty assistant bubble so the UI can start showing the cursor
      // before any tokens arrive.
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

      let botMessage = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // `{ stream: true }` tells the decoder not to flush its internal state,
        // handling multi-byte UTF-8 characters that straddle chunk boundaries.
        buffer += decoder.decode(value, { stream: true });

        // SSE events are delimited by double newlines.
        const parts = buffer.split('\n\n');

        // The last element may be an incomplete event — keep it for the next iteration.
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data: ')) continue;

          const payload = line.slice(6); // remove the "data: " prefix
          if (payload === '[DONE]') break;

          botMessage += payload;

          // Update only the last message (the in-progress assistant bubble)
          // without mutating the array — React requires immutable state updates.
          setMessages(prev =>
            prev.map((msg, i) =>
              i === prev.length - 1 ? { ...msg, content: botMessage } : msg
            )
          );
        }
      }

      // Flush the decoder's internal buffer for any trailing multi-byte character.
      const remaining = decoder.decode();
      if (remaining) {
        const line = remaining.trim();
        if (line.startsWith('data: ') && line.slice(6) !== '[DONE]') {
          botMessage += line.slice(6);
          setMessages(prev =>
            prev.map((msg, i) =>
              i === prev.length - 1 ? { ...msg, content: botMessage } : msg
            )
          );
        }
      }
    } catch (err) {
      console.error('sendMessage:', err);
      setError(err.message || 'Connection lost. Please try again.');
      // Remove the empty assistant bubble that was seeded before the stream failed.
      setMessages(prev =>
        prev[prev.length - 1]?.content === ''
          ? prev.slice(0, -1)
          : prev
      );
    } finally {
      setIsTyping(false);
    }
  };

  /**
   * Clears all messages and resets error state.
   * Wrapped in useCallback so ChatMode's useEffect dependency array stays stable
   * and doesn't trigger an infinite re-render loop.
   */
  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isTyping, error, sendMessage, clearChat };
}