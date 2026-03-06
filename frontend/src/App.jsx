import { useState, useRef } from 'react';

export default function App() {
  const [documentId, setDocumentId] = useState(null);
  const [docName, setDocName] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  
  const fileInputRef = useRef(null);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/api/ingest", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setDocumentId(data.document_id);
      setDocName(data.name);
      setMessages([{ role: "system", content: `Document "${data.name}" loaded successfully. What would you like to know?` }]);
    } catch (error) {
      console.error("Upload failed", error);
      alert("Failed to upload document.");
    }
    setIsUploading(false);
  };

  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || !documentId) return;

    const userQuery = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userQuery }]);
    setIsTyping(true);

    try {
      const res = await fetch("http://localhost:8000/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: userQuery, document_id: documentId, top_k: 5 }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let botMessage = "";

      // Add a placeholder bot message
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n\n");
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.replace("data: ", "");
            if (data === "[DONE]") break;
            
            botMessage += data;
            // Update the last message in state with the new token
            setMessages(prev => {
              const newMsgs = [...prev];
              newMsgs[newMsgs.length - 1].content = botMessage;
              return newMsgs;
            });
          }
        }
      }
    } catch (error) {
      console.error("Chat failed", error);
    }
    setIsTyping(false);
  };

  return (
    <div className="min-h-screen flex flex-col items-center p-6 font-sans text-slate-800">
      <header className="w-full max-w-3xl flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-indigo-600">ScholarOS</h1>
        <div>
          <input 
            type="file" 
            accept="application/pdf" 
            className="hidden" 
            ref={fileInputRef} 
            onChange={handleFileUpload} 
          />
          <button 
            onClick={() => fileInputRef.current.click()}
            disabled={isUploading}
            className="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50 transition"
          >
            {isUploading ? "Processing PDF..." : "Upload PDF"}
          </button>
        </div>
      </header>

      <main className="flex-1 w-full max-w-3xl bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col overflow-hidden">
        {/* Chat History */}
        <div className="flex-1 p-6 overflow-y-auto space-y-4 max-h-[60vh]">
          {!documentId ? (
            <div className="h-full flex items-center justify-center text-slate-400">
              Upload a PDF to start studying.
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] p-3 rounded-lg ${msg.role === "user" ? "bg-indigo-600 text-white rounded-br-none" : msg.role === "system" ? "bg-emerald-100 text-emerald-800 text-sm w-full text-center" : "bg-slate-100 text-slate-800 rounded-bl-none"}`}>
                  {msg.content}
                </div>
              </div>
            ))
          )}
          {isTyping && (
            <div className="flex justify-start">
              <div className="bg-slate-100 text-slate-500 p-3 rounded-lg rounded-bl-none animate-pulse">
                ScholarOS is typing...
              </div>
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-slate-100 bg-slate-50">
          <form onSubmit={handleChatSubmit} className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={!documentId || isTyping}
              placeholder={documentId ? "Ask a question about your document..." : "Upload a document first"}
              className="flex-1 px-4 py-2 rounded-md border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-100"
            />
            <button 
              type="submit" 
              disabled={!documentId || isTyping || !input.trim()}
              className="bg-indigo-600 text-white px-6 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50 font-medium transition"
            >
              Send
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}