import { useState, useCallback } from 'react';
import { qaUrl } from '../api/client';

export function useStreamChat(documentId) {
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError]       = useState(null);

  const sendMessage = async (query) => {
    const trimmed = query.trim();
    if (!trimmed || !documentId) return;

    setMessages(prev => [...prev, { role: 'user', content: trimmed }]);
    setIsTyping(true);
    setError(null);

    try {
      const res = await fetch(qaUrl, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          question:    trimmed,
          document_id: documentId,
          top_k:       5,
        }),
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer    = '';  // ← maintains state across TCP chunk boundaries

      // Seed an empty assistant bubble so the UI can stream into it
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

      let botMessage = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Append new bytes to the buffer; decode incrementally
        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double newlines
        const parts = buffer.split('\n\n');

        // The last element may be an incomplete event — keep it in the buffer
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data: ')) continue;

          const payload = line.slice(6); // strip "data: "
          if (payload === '[DONE]') break;

          botMessage += payload;

          // Immutable update — no direct mutation
          setMessages(prev =>
            prev.map((msg, i) =>
              i === prev.length - 1 ? { ...msg, content: botMessage } : msg
            )
          );
        }
      }

      // Flush any remaining buffered bytes
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
      setError('Connection lost. Please try again.');
      // Remove the empty assistant bubble on failure
      setMessages(prev =>
        prev[prev.length - 1]?.content === ''
          ? prev.slice(0, -1)
          : prev
      );
    } finally {
      setIsTyping(false);
    }
  };

  // useCallback so ChatMode's useEffect dep array is stable
  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isTyping, error, sendMessage, clearChat };
}