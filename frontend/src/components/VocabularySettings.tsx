"use client";

import { useState, useEffect } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";
import { auth } from "@/lib/firebase";

type VocabularySettingsProps = {
  userId: string;
  onBack: () => void;
};

type AliasMap = {
  [alias: string]: string;
};

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function VocabularySettings({ userId, onBack }: VocabularySettingsProps) {
  const [aliases, setAliases] = useState<AliasMap>({});
  const [aliasInput, setAliasInput] = useState("");
  const [fullInput, setFullInput] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchVocabulary();
  }, [userId]);

  const fetchVocabulary = async () => {
    setIsLoading(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/vocabulary/${userId}`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 8000,
      });
      if (res.ok) {
        const data = await res.json();
        setAliases(data.aliases || {});
      }
    } catch (err) {
      console.error("Failed to load vocabulary:", err);
      setError("Could not load your vocabulary.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddAlias = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!aliasInput.trim() || !fullInput.trim()) return;
    
    setIsSubmitting(true);
    setError("");

    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/vocabulary`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({
          user_id: userId,
          alias: aliasInput.trim(),
          full: fullInput.trim(),
        }),
        timeoutMs: 8000,
      });

      if (res.ok) {
        // Optimistically update the UI
        setAliases((prev) => ({
          ...prev,
          [aliasInput.trim().toLowerCase()]: fullInput.trim(),
        }));
        setAliasInput("");
        setFullInput("");
      } else {
        throw new Error("Failed to save alias");
      }
    } catch (err) {
      console.error("Error saving vocabulary:", err);
      setError("Failed to save your new word. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteAlias = async (aliasToDelete: string) => {
    // Optimistic deletion
    const previousAliases = { ...aliases };
    const newAliases = { ...aliases };
    delete newAliases[aliasToDelete];
    setAliases(newAliases);

    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/vocabulary/${userId}/${aliasToDelete}`, {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 5000,
      });
      
      if (!res.ok) {
        throw new Error("Failed to delete alias");
      }
    } catch (err) {
      console.error("Error deleting vocabulary:", err);
      // Revert if network fails
      setAliases(previousAliases);
      setError("Failed to remove the word.");
    }
  };

  return (
    <div className="min-h-screen flex flex-col pb-32 animate-in fade-in" style={{ background: 'transparent' }}>
      
      {/* Header */}
      <div
        className="sticky top-0 z-10 px-4 py-3 flex items-center justify-between"
        style={{ 
          paddingTop: "calc(env(safe-area-inset-top, 20px) + 8px)",
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(var(--blur-lg))',
          WebkitBackdropFilter: 'blur(var(--blur-lg))',
          borderBottom: '1px solid var(--color-border)'
        }}
      >
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[16px] font-semibold transition-colors active:opacity-50"
          style={{ color: 'var(--color-accent-primary)' }}
        >
          <span className="text-2xl leading-none">‹</span> Settings
        </button>
        <span className="text-[15px] font-bold truncate px-4" style={{ color: 'var(--color-text-primary)' }}>
          Vocabulary
        </span>
        <div className="w-16"></div>
      </div>

      <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-10">
        
        {/* Intro */}
        <div className="space-y-2 text-center md:text-left">
          <h2 className="text-3xl font-extrabold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>
            Personal Dictionary
          </h2>
          <p className="text-sm max-w-xl" style={{ color: 'var(--color-text-secondary)' }}>
            Teach the AI your abbreviations, acronyms, and slang. If you ask it to "schedule time for fyp", it will expand it to "final year project".
          </p>
        </div>

        {error && (
          <div className="p-3 rounded-xl flex items-center gap-2 text-sm" style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)', border: '1px solid var(--color-danger)' }}>
            <span className="font-bold">Error:</span> {error}
          </div>
        )}

        {/* Add New Alias Form */}
        <form onSubmit={handleAddAlias} className="p-5 rounded-2xl space-y-4 shadow-sm transition-all" style={{ background: 'var(--color-bg-glass)', border: '1px solid var(--color-border)' }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-widest ml-1" style={{ color: 'var(--color-text-tertiary)' }}>When I say...</label>
              <input
                type="text"
                required
                value={aliasInput}
                onChange={(e) => setAliasInput(e.target.value)}
                placeholder="e.g. fyp"
                className="w-full text-sm rounded-xl px-4 py-3.5 outline-none transition-all"
                style={{ background: 'var(--color-surface)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border-subtle)' }}
                disabled={isSubmitting}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-widest ml-1" style={{ color: 'var(--color-text-tertiary)' }}>It means...</label>
              <input
                type="text"
                required
                value={fullInput}
                onChange={(e) => setFullInput(e.target.value)}
                placeholder="e.g. final year project"
                className="w-full text-sm rounded-xl px-4 py-3.5 outline-none transition-all"
                style={{ background: 'var(--color-surface)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border-subtle)' }}
                disabled={isSubmitting}
              />
            </div>
          </div>
          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={!aliasInput.trim() || !fullInput.trim() || isSubmitting}
              className="px-6 py-2.5 text-white text-sm font-bold rounded-xl transition-all disabled:opacity-50 active:scale-95 shadow-md"
              style={{ background: 'var(--color-accent-gradient)' }}
            >
              {isSubmitting ? "Saving..." : "Add to Dictionary"}
            </button>
          </div>
        </form>

        {/* Existing Aliases List */}
        <div className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[11px] font-black uppercase tracking-[0.15em]" style={{ color: 'var(--color-text-tertiary)' }}>
              Saved Words
            </h3>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ background: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}>
              {Object.keys(aliases).length}
            </span>
          </div>

          {isLoading ? (
             <div className="flex justify-center p-8">
               <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--color-accent-primary)', borderTopColor: 'transparent' }}></div>
             </div>
          ) : Object.keys(aliases).length === 0 ? (
            <div className="p-8 border border-dashed rounded-2xl text-center" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-subtle)' }}>
              <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                Your dictionary is empty. Add a word above to get started.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {Object.entries(aliases).map(([alias, full]) => (
                <div
                  key={alias}
                  className="group p-4 rounded-2xl shadow-sm hover:shadow-md transition-all flex items-center justify-between gap-4"
                  style={{ background: 'var(--color-bg-glass)', border: '1px solid var(--color-border)' }}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 min-w-0 flex-1">
                    <span className="text-sm font-bold px-3 py-1 rounded-lg truncate inline-block w-fit" style={{ background: 'var(--color-surface)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border-subtle)' }}>
                      "{alias}"
                    </span>
                    <svg className="hidden sm:block w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--color-text-tertiary)' }}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                    </svg>
                    <span className="text-[15px] font-medium truncate" style={{ color: 'var(--color-text-secondary)' }}>
                      {full}
                    </span>
                  </div>

                  <button
                    onClick={() => handleDeleteAlias(alias)}
                    className="p-2 rounded-lg transition-colors flex-shrink-0 hover:bg-red-500/10"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    <svg className="w-5 h-5 text-red-400 hover:text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}