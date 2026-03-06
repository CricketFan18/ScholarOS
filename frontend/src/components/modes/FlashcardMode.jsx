/**
 * components/modes/FlashcardMode.jsx
 *
 * Active-recall study interface. Generates a grid of flip cards from the
 * selected document; each card reveals its answer on click (or tap on touch
 * devices) via a CSS 3-D rotation.
 *
 * See index.css for the perspective / preserve-3d / backface-hidden utilities.
 */

import { useState } from 'react';
import { Layers, Loader2, AlertCircle } from 'lucide-react';
import { useFlashcards } from '../../hooks/useFlashcards';

/**
 * @param {object}      props
 * @param {string|null} props.activeDocId - ID of the currently selected document.
 */
export default function FlashcardMode({ activeDocId }) {
  const [topic, setTopic] = useState('');
  const { cards, isLoading, error, generateCards } = useFlashcards(activeDocId);

  // Track which cards have been flipped via click/tap.
  // Using a Set stored in state lets us flip individual cards independently.
  const [flippedCards, setFlippedCards] = useState(new Set());

  const toggleCard = (idx) => {
    setFlippedCards(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  // Reset flipped state whenever a new deck is generated.
  const handleGenerate = () => {
    setFlippedCards(new Set());
    generateCards(topic);
  };

  return (
    <div className="h-full flex flex-col p-6 bg-slate-50">
      {/* ── Controls ─────────────────────────────────────────────────── */}
      <div className="max-w-5xl mx-auto w-full mb-6">
        <h2 className="text-2xl font-bold text-slate-800 tracking-tight mb-4">Active Recall</h2>
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 items-end">
          <div className="flex-1 w-full">
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Focus Topic <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. 'Neural Networks' or leave blank for full document coverage"
              className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm"
              // Allow keyboard-only users to trigger generation without reaching for the button.
              onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
            />
          </div>
          <button
            onClick={handleGenerate}
            disabled={isLoading || !activeDocId}
            className="w-full md:w-auto bg-indigo-600 text-white px-8 py-3 rounded-xl hover:bg-indigo-700 disabled:opacity-50 flex items-center justify-center gap-2 font-medium shadow-sm transition-all"
          >
            {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Layers className="w-5 h-5" />}
            Generate Deck
          </button>
        </div>
      </div>

      {error && (
        <div className="max-w-5xl mx-auto w-full mb-6 flex items-center gap-2 text-red-600 bg-red-50 p-4 rounded-lg">
          <AlertCircle className="w-5 h-5 shrink-0" /> {error}
        </div>
      )}

      {/* ── Card grid ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto max-w-6xl mx-auto w-full pb-6">
        {cards.length === 0 && !isLoading && !error ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 space-y-4 pt-12">
            <Layers className="w-16 h-16 opacity-20" />
            <p>Generate a deck to start studying.</p>
          </div>
        ) : (
          <>
            {/* Hint shown once cards are loaded */}
            {cards.length > 0 && (
              <p className="text-xs text-slate-400 text-center mb-4">
                Click a card to reveal the answer
              </p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {cards.map((card, idx) => {
                const isFlipped = flippedCards.has(idx);
                return (
                  /*
                   * Flip-card structure (three nested divs):
                   *   1. `.perspective`   — establishes the 3-D perspective frustum.
                   *   2. `.preserve-3d`   — keeps front and back in the same 3-D space
                   *                         so the rotation animates both together.
                   *   3. Two `.backface-hidden` children — the front (question) and
                   *      back (answer) faces, stacked in the same position.
                   *      `.my-rotate-y-180` pre-rotates the back face 180° so it starts
                   *      hidden; the same class is conditionally applied to the wrapper
                   *      on click/tap, bringing the back face into view.
                   *
                   * Click-to-flip replaces hover-to-flip so the interaction works on
                   * touch devices (tablets, phones) where hover doesn't exist.
                   */
                  <div
                    key={idx}
                    className="perspective h-72 cursor-pointer"
                    onClick={() => toggleCard(idx)}
                    // Keyboard accessibility: Enter/Space flip the card.
                    onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleCard(idx)}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isFlipped}
                    aria-label={isFlipped ? `Card ${idx + 1} answer: ${card.back}` : `Card ${idx + 1} question: ${card.front}`}
                  >
                    <div
                      className={`relative preserve-3d w-full h-full duration-700 ${
                        isFlipped ? 'my-rotate-y-180' : ''
                      }`}
                    >
                      {/* Front face — question */}
                      <div className="absolute backface-hidden border border-slate-200 bg-white w-full h-full rounded-2xl p-6 flex items-center justify-center text-center shadow-sm hover:border-indigo-300 transition-colors">
                        <h3 className="text-xl font-semibold text-slate-800 leading-relaxed">
                          {card.front}
                        </h3>
                        <div className="absolute bottom-4 text-xs font-semibold text-slate-400 uppercase tracking-widest">
                          Question — click to flip
                        </div>
                      </div>
                      {/* Back face — answer (pre-rotated 180° so it starts hidden) */}
                      <div className="absolute my-rotate-y-180 backface-hidden border-2 border-indigo-100 bg-indigo-50/50 w-full h-full rounded-2xl p-6 flex items-center justify-center text-center shadow-sm overflow-y-auto">
                        <p className="text-slate-700 font-medium leading-relaxed">{card.back}</p>
                        <div className="absolute bottom-4 text-xs font-semibold text-indigo-400 uppercase tracking-widest">
                          Answer — click to flip back
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}