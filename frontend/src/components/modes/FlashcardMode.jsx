import { useState } from 'react';
import { Layers, Loader2, AlertCircle } from 'lucide-react';
import { useFlashcards } from '../../hooks/useFlashcards';

export default function FlashcardMode({ activeDocId }) {
  const [topic, setTopic] = useState("");
  const { cards, isLoading, error, generateCards } = useFlashcards(activeDocId);

  return (
    <div className="h-full flex flex-col p-6 bg-slate-50">
      <div className="max-w-5xl mx-auto w-full mb-6">
        <h2 className="text-2xl font-bold text-slate-800 tracking-tight mb-4">Active Recall</h2>
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 items-end">
          <div className="flex-1 w-full">
            <label className="block text-sm font-medium text-slate-700 mb-2">Focus Topic (Optional)</label>
            <input 
              type="text" 
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g., 'Neural Networks' or leave blank for full document coverage"
              className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm"
              onKeyDown={(e) => e.key === 'Enter' && generateCards(topic)}
            />
          </div>
          <button 
            onClick={() => generateCards(topic)}
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
          <AlertCircle className="w-5 h-5" /> {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto max-w-6xl mx-auto w-full pb-6">
        {cards.length === 0 && !isLoading && !error ? (
           <div className="h-full flex flex-col items-center justify-center text-slate-400 space-y-4 pt-12">
             <Layers className="w-16 h-16 opacity-20" />
             <p>Set a topic and generate a deck to start studying.</p>
           </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {cards.map((card, idx) => (
              <div key={idx} className="group perspective h-72">
                <div className="relative preserve-3d group-hover:my-rotate-y-180 w-full h-full duration-700">
                  <div className="absolute backface-hidden border border-slate-200 bg-white w-full h-full rounded-2xl p-6 flex items-center justify-center text-center shadow-sm cursor-pointer hover:border-indigo-300 transition-colors">
                    <h3 className="text-xl font-semibold text-slate-800 leading-relaxed">{card.front}</h3>
                    <div className="absolute bottom-4 text-xs font-semibold text-slate-400 uppercase tracking-widest">Question</div>
                  </div>
                  <div className="absolute my-rotate-y-180 backface-hidden border-2 border-indigo-100 bg-indigo-50/50 w-full h-full rounded-2xl p-6 flex items-center justify-center text-center shadow-sm cursor-pointer overflow-y-auto custom-scrollbar">
                    <p className="text-slate-700 font-medium leading-relaxed">{card.back}</p>
                    <div className="absolute bottom-4 text-xs font-semibold text-indigo-400 uppercase tracking-widest">Answer</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}