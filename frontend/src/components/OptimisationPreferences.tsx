"use client";

import { useState, useEffect, useRef } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils"; 
import { auth } from "@/lib/firebase";

/* =========================
   TYPE DEFINITIONS
========================= */

type Preference = {
  id: string;
  raw_input?: string;
  category: string;
  rule_type?: string;
  is_hard_constraint?: boolean;
  is_hard: boolean; 
  reasoning: string;
  type: string;
  weight: number;
};

type PreferencesListResponse = {
  preferences: Preference[];
};

type ParsePreferenceResponse = {
  status: string;
  saved_preferences: {
    id: string;
    data: Omit<Preference, "id">;
  }[];
};

type OptimisationPreferencesProps = {
  userId: string;
  onBack: () => void;
};

/* =========================
   SPEECH RECOGNITION TYPES
========================= */

interface SpeechRecognitionResult {
  transcript: string;
}

interface SpeechRecognitionResultList {
  [index: number]: {
    [index: number]: SpeechRecognitionResult;
  };
  length: number;
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;

  start(): void;
  stop(): void;

  onresult: (event: SpeechRecognitionEvent) => void;
  onerror: (event: any) => void;
  onend: () => void;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognition;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

/* =========================
   COMPONENT
========================= */

export default function OptimisationPreferences({
  userId,
  onBack,
}: OptimisationPreferencesProps) {
  const [inputText, setInputText] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [speechSupported, setSpeechSupported] = useState<boolean>(true);

  const recognitionRef = useRef<SpeechRecognition | null>(null);

  useEffect(() => {
    fetchPreferences();

    if (typeof window !== "undefined") {
      const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

      if (SpeechRecognition) {
        recognitionRef.current = new SpeechRecognition();
        recognitionRef.current.continuous = true;
        recognitionRef.current.interimResults = true;
        recognitionRef.current.lang = "en-GB";

        recognitionRef.current.onresult = (event: SpeechRecognitionEvent) => {
          let currentTranscript = "";

          for (let i = event.resultIndex; i < event.results.length; i++) {
            currentTranscript += event.results[i][0].transcript;
          }

          setInputText((prev) => prev + " " + currentTranscript.trim());
        };

        recognitionRef.current.onerror = (event: any) => {
          console.error("Speech recognition error", event.error);
          setIsRecording(false);
        };

        recognitionRef.current.onend = () => {
          setIsRecording(false);
        };
      } else {
        setSpeechSupported(false);
      }
    }
  }, [userId]);

  const fetchPreferences = async (): Promise<void> => {
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/preferences/list?userId=${userId}`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 8000
      });
      if (res.ok) {
        const data: PreferencesListResponse = await res.json();
        console.log("Fetched preferences:", data);
        setPreferences(data.preferences || []);
      }
    } catch (err) {
      console.error("Failed to load preferences", err);
    }
  };

  const handleSubmit = async (): Promise<void> => {
    if (!inputText.trim()) return;
    setIsSubmitting(true);

    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/preferences/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({
          user_id: userId,
          raw_text: inputText,
          timezone: tz
        }),
        timeoutMs: 12000 
      });

      if (res.ok) {
        const result: ParsePreferenceResponse = await res.json();
        
        if (result.status === "success" && result.saved_preferences) {
          const newPrefs = result.saved_preferences.map(item => ({
            ...item.data,
            id: item.id
          }));
          
          setPreferences((prev) => [...newPrefs, ...prev]);
          setInputText("");
        } else {
          console.error("Failed to parse preference payload:", result);
        }
      }
    } catch (err) {
      console.error("Error submitting preference:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (prefId: string): Promise<void> => {
    if (!prefId || prefId === "undefined") {
      console.error("Attempted to delete a preference with an undefined ID");
      return;
    }

    const previousPrefs = [...preferences];
    setPreferences(preferences.filter((p) => p.id !== prefId));

    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/preferences/${prefId}?userId=${userId}`, {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 5000
      });
      if (!res.ok) throw new Error("Deletion failed");
    } catch (err) {
      console.error("Error deleting preference:", err);
      setPreferences(previousPrefs);
    }
  };

  const toggleRecording = (): void => {
    if (!recognitionRef.current) return;

    if (isRecording) {
      recognitionRef.current.stop();
      setIsRecording(false);
    } else {
      setInputText("");
      recognitionRef.current.start();
      setIsRecording(true);
    }
  };

  return (
    <div className="min-h-screen font-sans flex flex-col pb-32 bg-transparent transition-colors duration-500">
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

        <span className="text-[15px] font-bold truncate px-4 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
          Optimisation
        </span>

        <div className="w-16"></div>
      </div>

      <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-10 animate-fadeIn">
        <div className="space-y-2 text-center md:text-left">
          <h2 className="text-3xl font-extrabold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
            Rules & Preferences
          </h2>

          <p className="text-sm max-w-xl transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
            Tell the AI how you like to structure your days. You can type your
            boundaries or tap the microphone to dictate them.
          </p>
        </div>

        {/* INPUT */}
        <div 
          className="rounded-2xl overflow-hidden transition-all duration-200"
          style={{
            background: 'var(--color-bg-glass-strong)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="e.g., I need a 15 minute break after any meeting..."
            rows={4}
            className="w-full text-[15px] p-5 border-0 focus:ring-0 resize-none bg-transparent outline-none leading-relaxed transition-colors duration-200"
            style={{ color: 'var(--color-text-primary)' }}
            disabled={isSubmitting}
          />

          <div 
            className="flex items-center justify-between px-5 py-3 transition-colors duration-200"
            style={{ 
              background: 'var(--color-bg-subtle)',
              borderTop: '1px solid var(--color-border)',
            }}
          >
            {speechSupported ? (
              <button
                onClick={toggleRecording}
                className="p-2.5 rounded-full flex items-center justify-center transition-all duration-200 hover:scale-105 active:scale-95"
                style={isRecording ? {
                  background: 'var(--color-danger-bg)',
                  color: 'var(--color-danger)',
                  animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                } : {
                  background: 'var(--color-surface)',
                  color: 'var(--color-text-tertiary)',
                  border: '1px solid var(--color-border)',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
                </svg>
              </button>
            ) : (
              <span className="text-xs transition-colors duration-200" style={{ color: 'var(--color-text-muted)' }}>
                Voice not supported in this browser
              </span>
            )}

            <button
              onClick={handleSubmit}
              disabled={!inputText.trim() || isSubmitting}
              className="px-6 py-2.5 text-sm font-bold rounded-xl transition-all disabled:opacity-50 active:scale-95 btn-primary"
            >
              {isSubmitting ? "Saving..." : "Add Rule"}
            </button>
          </div>
        </div>

        {/* LIST SECTION */}
        <div className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[11px] font-black uppercase tracking-[0.15em] transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
              Active Rules
            </h3>
            <span 
              className="text-xs font-semibold px-2.5 py-0.5 rounded-full transition-colors duration-200"
              style={{
                background: 'var(--color-bg-subtle)',
                color: 'var(--color-text-secondary)',
                border: '1px solid var(--color-border-subtle)'
              }}
            >
              {preferences.length}
            </span>
          </div>

          {preferences.length === 0 ? (
            <div 
              className="p-8 rounded-2xl text-center transition-all duration-200"
              style={{
                background: 'var(--color-bg-glass)',
                border: '2px dashed var(--color-border-accent)',
              }}
            >
              <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                No active rules. Add one above to get started.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {preferences.map((pref, index) => (
                <div
                  key={pref.id || index}
                  className="group p-5 rounded-2xl transition-all flex items-start gap-4 justify-between"
                  style={{
                    background: 'var(--color-bg-glass)',
                    backdropFilter: 'blur(12px)',
                    WebkitBackdropFilter: 'blur(12px)',
                    border: '1px solid var(--color-border)',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  <div className="flex items-start gap-4">
                    <div className="mt-1 flex-shrink-0">
                      {pref.is_hard ? (
                        <div 
                          className="flex items-center justify-center w-8 h-8 rounded-full transition-colors duration-200" 
                          title="Hard Constraint"
                          style={{
                            background: 'var(--color-danger-bg)',
                            color: 'var(--color-danger)',
                            border: '1px solid var(--color-danger)',
                          }}
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                          </svg>
                        </div>
                      ) : (
                        <div 
                          className="flex items-center justify-center w-8 h-8 rounded-full transition-colors duration-200" 
                          title="Soft Preference"
                          style={{
                            background: 'var(--color-accent-glow)',
                            color: 'var(--color-accent-primary)',
                            border: '1px solid var(--color-border-accent)',
                          }}
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                          </svg>
                        </div>
                      )}
                    </div>

                    <div className="space-y-2">
                      <p className="text-[15px] font-semibold leading-snug transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
                        {pref.reasoning}
                      </p>
                      
                      <div className="flex flex-wrap gap-2">
                        <span 
                          className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-md transition-colors duration-200"
                          style={{
                            background: 'var(--color-bg-subtle)',
                            color: 'var(--color-text-secondary)',
                            border: '1px solid var(--color-border-subtle)'
                          }}
                        >
                          {pref.category}
                        </span>
                        <span 
                          className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-md transition-colors duration-200"
                          style={{
                            background: 'var(--color-bg-subtle)',
                            color: 'var(--color-text-secondary)',
                            border: '1px solid var(--color-border-subtle)'
                          }}
                        >
                          {pref.type}
                        </span>
                        {!pref.is_hard && (
                          <span 
                            className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-md transition-colors duration-200"
                            style={{
                              background: 'var(--color-accent-glow)',
                              color: 'var(--color-accent-primary)',
                              border: '1px solid var(--color-border-subtle)'
                            }}
                          >
                            Weight: {pref.weight}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => handleDelete(pref.id)}
                    className="p-2 rounded-lg transition-all flex-shrink-0 hover:bg-red-500/10"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
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