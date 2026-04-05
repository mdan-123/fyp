"use client";

import { useState, useEffect, useRef } from "react";
import { useAuth } from "@/lib/AuthContext";
import NavigationBar from "@/components/NavigationBar";
import { fetchWithRetry } from "@/lib/fetchUtils";
import { useSpeech } from "@/lib/useSpeech"; 

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

// ─── Types ───────────────────────────────────────────────────────
type MessageRole = "user" | "assistant";
type MessageStatus = "success" | "error" | "clarification_needed" | "loading";

interface ClarificationPayload {
  clarification_type: "ambiguous_match" | "slot_conflict";
  candidates?:      string[];
  query?:           string;
  entity_key?:      string;
  requested_start?: string;
  requested_end?:   string;
  suggested_start?: string;
  suggested_end?:   string;
  title?:           string;
  original_intent?:   string;
  original_entities?: Record<string, any>;
  original_text?:     string;
}

interface Message {
  id:             string;
  role:           MessageRole;
  content:        string;
  status:         MessageStatus;
  timestamp:      string;
  clarification?: ClarificationPayload;
  resolved?:      boolean;
}

// ─── Helpers ─────────────────────────────────────────────────────
const generateId = () => Math.random().toString(36).slice(2);

const formatTime = (iso: string) => {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
};

const formatSlotTime = (iso?: string) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      weekday: "short", hour: "2-digit", minute: "2-digit"
    });
  } catch {
    return iso;
  }
};

// ─── Typing indicator ─────────────────────────────────────────────
const TypingDots = () => (
  <div className="flex items-center gap-1.5 px-1 py-1">
    {[0, 0.15, 0.3].map((d) => (
      <span 
        key={`dot-${d}`} 
        className="w-2 h-2 rounded-full animate-pulse transition-colors duration-200"
        style={{ 
          background: "var(--color-accent-primary)", 
          animationDelay: `${d}s`,
          opacity: 0.7
        }} 
      />
    ))}
  </div>
);

// ─── Individual message bubble ────────────────────────────────────
function MessageBubble({
  msg,
  onCandidateSelect,
  onSlotConfirm,
  onSlotCancel,
}: Readonly<{
  msg: Message;
  onCandidateSelect: (candidate: string, cl: ClarificationPayload) => void;
  onSlotConfirm:     (cl: ClarificationPayload) => void;
  onSlotCancel:      () => void;
}>) {
  const isUser = msg.role === "user";
  const isLoading = msg.status === "loading";

  return (
    <div className={`animate-fade-in-up flex w-full mb-3 ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[82%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
        
        {/* Avatar for assistant */}
        {!isUser && (
          <div className="flex items-center gap-2 mb-1">
            <div 
              className="w-6 h-6 rounded-lg flex items-center justify-center transition-colors duration-500"
              style={{
                background: "var(--color-accent-gradient)",
                boxShadow: "var(--shadow-sm)"
              }}
            >
              <svg className="w-3.5 h-3.5" style={{ color: "var(--color-bg-base)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-wider transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>Assistant</span>
          </div>
        )}

        {/* bubble */}
        <div
          className="rounded-2xl px-4 py-3 text-sm leading-relaxed transition-all duration-500"
          style={{
            background: isUser ? "var(--color-accent-gradient)" : "var(--color-bg-glass)",
            backdropFilter: isUser ? "none" : "blur(12px)",
            WebkitBackdropFilter: isUser ? "none" : "blur(12px)",
            border: isUser ? "none" : "1px solid var(--color-border)",
            color: isUser ? "var(--color-bg-base)" : "var(--color-text-primary)",
            boxShadow: isUser ? "var(--shadow-md)" : "var(--shadow-sm)",
          }}
        >
          {isLoading ? <TypingDots /> : <p style={{ whiteSpace: "pre-wrap" }}>{msg.content}</p>}
        </div>

        {/* clarification UI */}
        {msg.clarification && !msg.resolved && (
          <div
            className="w-full rounded-2xl p-4 mt-2 transition-all duration-500"
            style={{
              background: "var(--color-bg-subtle)",
              border: "1px solid var(--color-border-accent)",
              borderRadius: "16px 16px 16px 6px",
            }}
          >
            {msg.clarification.clarification_type === "ambiguous_match" && (
              <>
                <p className="text-[10px] tracking-widest uppercase mb-3 font-semibold transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>
                  Select one:
                </p>
                <div className="flex flex-col gap-2">
                  {(msg.clarification.candidates ?? []).map((c) => (
                    <button
                      key={c}
                      onClick={() => onCandidateSelect(c, msg.clarification!)}
                      className="w-full text-left px-4 py-2.5 rounded-xl text-sm font-medium transition-all active:scale-[0.98] hover:scale-[1.01]"
                      style={{
                        background: "var(--color-surface)",
                        border: "1px solid var(--color-border)",
                        color: "var(--color-text-secondary)",
                      }}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              </>
            )}

            {msg.clarification.clarification_type === "slot_conflict" && (
              <>
                {msg.clarification.suggested_start && (
                  <p className="text-sm mb-4 transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>
                    Next available slot:{" "}
                    <span className="font-semibold" style={{ color: "var(--color-accent-primary)" }}>
                      {formatSlotTime(msg.clarification.suggested_start)}
                    </span>
                  </p>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={() => onSlotConfirm(msg.clarification!)}
                    className="flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all active:scale-[0.98] hover:scale-[1.01] btn-primary"
                  >
                    Book this time
                  </button>
                  <button
                    onClick={onSlotCancel}
                    className="px-4 py-2.5 rounded-xl text-sm font-medium transition-all active:scale-[0.98] btn-secondary"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* timestamp */}
        <span className="text-[10px] px-1 font-medium transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>
          {formatTime(msg.timestamp)}
        </span>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────
export default function ChatPage() {
  const { user, loading: authLoading } = useAuth();
  const userId = user?.uid ?? null;

  const [messages,      setMessages]      = useState<Message[]>([]);
  const [input,         setInput]         = useState("");
  const [isSending,     setIsSending]     = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  const bottomRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLTextAreaElement>(null);

  // Speech Recognition
  const { isListening, transcript, startListening, stopListening } = useSpeech();

  // Update input when transcript changes while listening
  useEffect(() => {
    if (isListening && transcript) {
      setInput(prev => {
        return transcript;
      });
    }
  }, [transcript, isListening]);

  // ── Load history on mount ──────────────────────────────────────
  useEffect(() => {
    if (!authLoading && userId) loadHistory(userId);
  }, [userId, authLoading]);

  // ── Auto-scroll on new messages ───────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadHistory = async (uid: string) => {
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/ai/history/${uid}`);
      if (res.ok) {
        const data = await res.json();
        const loaded: Message[] = (data.history ?? []).map((h: any) => ({
          id:        h.id,
          role:      h.role as MessageRole,
          content:   h.content,
          status:    "success" as MessageStatus,
          timestamp: h.timestamp,
          resolved:  true,   
        }));
        setMessages(loaded);
      }
    } catch (e) {
      console.error("Failed to load chat history:", e);
    } finally {
      setHistoryLoaded(true);
    }
  };

  // ── Core send function ─────────────────────────────────────────
  const sendMessage = async (
    text:          string,
    intentOverride?: string,
    entityOverrides?: Record<string, any>,
    resolveMessageId?: string,
  ) => {
    if (!userId || (!text.trim() && !intentOverride)) return;

    const userMsg: Message = {
      id:        generateId(),
      role:      "user",
      content:   text,
      status:    "success",
      timestamp: new Date().toISOString(),
    };

    const loadingId = generateId();
    const loadingMsg: Message = {
      id:        loadingId,
      role:      "assistant",
      content:   "",
      status:    "loading",
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => {
      const updated = prev.map(m =>
        m.id === resolveMessageId ? { ...m, resolved: true } : m
      );
      return [...updated, userMsg, loadingMsg];
    });

    setIsSending(true);
    setInput("");

    try {
      const body: any = { text, user_id: userId };
      if (intentOverride)  body.intent_override  = intentOverride;
      if (entityOverrides) body.entity_overrides = entityOverrides;

      const res  = await fetchWithRetry(`${API_BASE_URL}/api/ai/parse`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(body),
      });

      const data = await res.json();
      const assistantMsg = buildAssistantMessage(data);

      setMessages(prev => prev.map(m => m.id === loadingId ? assistantMsg : m));

    } catch (err) {
      console.error("AI parse error:", err);
      const errMsg: Message = {
        id:        loadingId,
        role:      "assistant",
        content:   "Something went wrong. Please try again.",
        status:    "error",
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => prev.map(m => m.id === loadingId ? errMsg : m));
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  };

  // ── Build assistant message from API response ──────────────────
  const buildAssistantMessage = (data: any): Message => {
    const base = {
      id:        generateId(),
      role:      "assistant" as MessageRole,
      timestamp: new Date().toISOString(),
    };

    if (data.type === "chat") {
      return { ...base, content: data.message, status: "success" };
    }

    if (data.type === "action") {
      const results: any[] = data.results ?? [];
      const lines = results.map((r: any) => {
        if (r.status === "success") return r.result?.message ?? "Done.";
        if (r.status === "error")   return `Error: ${r.error}`;
        return "";
      }).filter(Boolean);
      return { ...base, content: lines.join("\n") || "Done.", status: "success" };
    }

    if (data.status === "clarification_needed") {
      const cl: ClarificationPayload = {
        clarification_type: data.clarification_type,
        candidates:         data.candidates,
        query:              data.query,
        entity_key:         data.entity_key,
        requested_start:    data.requested_start,
        requested_end:      data.requested_end,
        suggested_start:    data.suggested_start,
        suggested_end:      data.suggested_end,
        title:              data.title,
        original_intent:    data.original_intent,
        original_entities:  data.original_entities,
        original_text:      data.original_text,
      };
      return { ...base, content: data.message, status: "clarification_needed", clarification: cl };
    }

    return { ...base, content: data.message ?? "I couldn't process that.", status: "error" };
  };

  // ── Clarification handlers ─────────────────────────────────────

  const handleCandidateSelect = (candidate: string, cl: ClarificationPayload, msgId: string) => {
    if (!cl.original_intent || !cl.original_entities) return;
    const entityKey = cl.entity_key ?? "events";
    const overridden = {
      ...cl.original_entities,
      [entityKey]: [candidate], 
    };
    sendMessage(
      `Selected: ${candidate}`,
      cl.original_intent,
      overridden,
      msgId,
    );
  };

  const handleSlotConfirm = (cl: ClarificationPayload, msgId: string) => {
    if (!cl.original_intent || !cl.original_entities || !cl.suggested_start) return;
    const overridden = {
      ...cl.original_entities,
      start_timestamp: cl.suggested_start,
      end_timestamp:   cl.suggested_end ?? cl.suggested_start,
    };
    sendMessage(
      `Confirmed: ${cl.title ?? "event"} at ${formatSlotTime(cl.suggested_start)}`,
      cl.original_intent,
      overridden,
      msgId,
    );
  };

  const handleSlotCancel = (msgId: string) => {
    setMessages(prev => prev.map(m => m.id === msgId ? { ...m, resolved: true } : m));
    setMessages(prev => [...prev, {
      id:        generateId(),
      role:      "assistant",
      content:   "No problem — the booking has been cancelled.",
      status:    "success",
      timestamp: new Date().toISOString(),
    }]);
  };

  // ── Input handling ─────────────────────────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const toggleListening = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  // ── Render ─────────────────────────────────────────────────────
  return (
    <div className="min-h-[100dvh] flex flex-col relative overflow-hidden transition-colors duration-500" style={{ background: "var(--color-bg-base)" }}>
      {/* Decorative Orbs handled entirely by body::before in global.css */}

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col h-[100dvh] transition-all duration-300 w-full pb-24">
        
        {/* Header - Now spans full width */}
        <header 
          className="sticky top-0 z-30 px-5 pt-[calc(env(safe-area-inset-top,20px)+16px)] pb-4 flex items-center justify-center gap-3 w-full transition-colors duration-500"
          style={{
            background: "var(--color-bg-glass-strong)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            borderBottom: "1px solid var(--color-border)",
          }}
        >
          <div 
            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors duration-500"
            style={{
              background: "var(--color-accent-gradient)",
              boxShadow: "var(--shadow-md)",
            }}
          >
            <svg className="w-5 h-5" style={{ color: "var(--color-bg-base)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <div className="flex flex-col items-center">
            <h1 className="text-base font-bold tracking-tight transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>AI Assistant</h1>
            <p className="text-[9px] font-medium uppercase tracking-widest transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>
              Scheduling · Tasks · Reminders
            </p>
          </div>
        </header>

        {/* Messages Area - Constrained to max-w-4xl for readability */}
        <div 
          className="flex-1 overflow-y-auto scrollbar-hide px-4 md:px-6 py-6 w-full max-w-4xl mx-auto"
        >
          <div className="w-full flex flex-col pb-4">
            {/* History loading skeleton */}
            {!historyLoaded && (
              <div className="flex flex-col gap-4 mb-4">
                {[1, 2, 3].map(i => (
                  <div key={`skeleton-${i}`} className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}>
                    <div 
                      className="h-12 rounded-2xl animate-pulse transition-colors duration-500"
                      style={{ 
                        width: `${160 + i * 40}px`, 
                        background: "var(--color-bg-subtle)" 
                      }} 
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Empty state */}
            {historyLoaded && messages.length === 0 && (
              <div className="flex flex-col items-center justify-center min-h-[60vh] gap-5 text-center px-4">
                <div 
                  className="w-20 h-20 rounded-2xl flex items-center justify-center mb-2 animate-float transition-colors duration-500"
                  style={{
                    background: "var(--color-accent-glow)",
                    border: "1px solid var(--color-border-accent)",
                    boxShadow: "var(--shadow-glow)",
                  }}
                >
                  <svg className="w-10 h-10 transition-colors duration-200" style={{ color: "var(--color-accent-primary)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0021 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0021 11.25v7.5" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-2xl font-bold mb-2 transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>What&apos;s on the agenda?</h2>
                  <p className="text-sm max-w-xs mx-auto transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>
                    Schedule events, manage tasks, set reminders — just say it naturally.
                  </p>
                </div>
                <div className="flex flex-col gap-2 w-full max-w-sm mt-4">
                  {[
                    "Schedule gym tomorrow at 7am",
                    "What do I have on Friday?",
                    "Remind me to review notes at 9pm",
                  ].map(s => (
                    <button 
                      key={s} 
                      onClick={() => { setInput(s); inputRef.current?.focus(); }}
                      className="px-4 py-3.5 rounded-xl text-sm text-left transition-all hover:scale-[1.01] active:scale-[0.99]"
                      style={{
                        background: "var(--color-bg-glass)",
                        backdropFilter: "blur(8px)",
                        border: "1px solid var(--color-border)",
                        color: "var(--color-text-secondary)",
                        boxShadow: "var(--shadow-sm)",
                      }}
                    >
                      <span className="mr-2 transition-colors duration-200" style={{ color: "var(--color-accent-primary)" }}>→</span>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map(msg => (
              <MessageBubble
                key={msg.id}
                msg={msg}
                onCandidateSelect={(c, cl) => handleCandidateSelect(c, cl, msg.id)}
                onSlotConfirm={cl => handleSlotConfirm(cl, msg.id)}
                onSlotCancel={() => handleSlotCancel(msg.id)}
              />
            ))}

            <div ref={bottomRef} className="h-4" />
          </div>
        </div>

        {/* Input Bar */}
        <div 
          className="fixed bottom-[calc(env(safe-area-inset-bottom,16px)+100px)] left-0 right-0 z-40 px-4 pt-4 pb-2 transition-all duration-300 pointer-events-none"
        >
          <div className="max-w-3xl mx-auto w-full pointer-events-auto rounded-2xl transition-colors duration-500" style={{ boxShadow: "var(--shadow-lg)" }}>
            <div 
              className="flex items-center gap-2 rounded-2xl p-2 relative transition-colors duration-500"
              style={{
                background: "var(--color-bg-glass-strong)",
                backdropFilter: "blur(20px)",
                WebkitBackdropFilter: "blur(20px)",
                border: "1px solid var(--color-border)",
              }}
            >
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about your schedule…"
                disabled={isSending}
                className="flex-1 bg-transparent resize-none text-sm outline-none scrollbar-hide min-h-[40px] overflow-hidden py-2.5 px-3 flex items-center justify-center self-center transition-colors duration-200"
                style={{
                  color: "var(--color-text-primary)",
                }}
              />
              
              <button
                onClick={toggleListening}
                className={`p-2.5 rounded-xl transition-all duration-200 flex-shrink-0`}
                style={isListening 
                  ? { background: "var(--color-danger-bg)", color: "var(--color-danger)", animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite" }
                  : { background: "var(--color-surface)", color: "var(--color-text-secondary)", border: "1px solid var(--color-border)" }
                }
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {isListening ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  )}
                </svg>
              </button>

              <button
                onClick={() => sendMessage(input)}
                disabled={isSending || (!input.trim() && !isListening)}
                className="p-2.5 rounded-xl transition-all duration-200 flex-shrink-0 disabled:opacity-50"
                style={(!isSending && input.trim()) 
                  ? { background: "var(--color-accent-gradient)", color: "var(--color-bg-base)", boxShadow: "var(--shadow-sm)" }
                  : { background: "var(--color-surface)", color: "var(--color-text-muted)", border: "1px solid var(--color-border)" }
                }
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <NavigationBar />
      </main>
    </div>
  );
}