/**
 * components/common/MarkdownRenderer.jsx
 *
 * Thin wrapper around react-markdown that applies consistent Tailwind
 * Typography styles across every surface that renders AI-generated text
 * (chat bubbles, summaries, etc.).
 */

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders a markdown string as styled HTML.
 *
 * @param {object} props
 * @param {string} props.content - Raw markdown text to render.
 */
export default function MarkdownRenderer({ content }) {
  return (
    // `prose` activates Tailwind Typography; overrides keep code blocks
    // readable with a dark background and relaxed line-height for body text.
    <div className="prose prose-slate max-w-none prose-p:leading-relaxed prose-pre:bg-slate-800 prose-pre:text-slate-50">
      {/* remarkGfm adds GitHub-Flavoured Markdown: tables, strikethrough, task lists, etc. */}
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}