"use client";

import { useState, useEffect, useRef } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";
import { auth } from "@/lib/firebase";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

type SearchType = "events" | "tasks" | "reminders" | "all";

interface SearchResult {
    id: string;
    type: "event" | "task" | "reminder";
    title: string;
    status: string;
    start?: string;
    end?: string;
    location?: string;
    category?: string;
    due_date?: string;
    trigger_time?: string;
    trigger_type?: string;
    priority?: number | string;
    estimated_duration?: number | string;
    energy_level?: string;
    repeat?: string;
}

interface GlobalSearchModalProps {
    isOpen: boolean;
    onClose: () => void;
    userId: string;
    searchType: SearchType;
    onResultClick: (result: SearchResult) => void;
    placeholder?: string;
}

export default function GlobalSearchModal({
    isOpen,
    onClose,
    userId,
    searchType,
    onResultClick,
    placeholder = "Search...",
}: GlobalSearchModalProps) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    // Clear state and auto-focus when modal opens
    useEffect(() => {
        if (isOpen) {
            setQuery("");
            setResults([]);
            // Small timeout ensures the modal is fully rendered before focusing
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [isOpen]);

    // Close on Escape key
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape" && isOpen) onClose();
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, onClose]);

    // Debounced API Call
    useEffect(() => {
        const timer = setTimeout(async () => {
            if (!query.trim()) {
                setResults([]);
                setIsSearching(false);
                return;
            }

            setIsSearching(true);
            try {
                const token = await auth.currentUser?.getIdToken();
                const res = await fetchWithRetry(`${API_BASE_URL}/api/search`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                    body: JSON.stringify({ user_id: userId, query, search_type: searchType }),
                    timeoutMs: 5000,
                });

                if (res.ok) {
                    const data = await res.json();
                    setResults(data.results || []);
                }
            } catch (error) {
                console.error("Search failed:", error);
            } finally {
                setIsSearching(false);
            }
        }, 300);

        return () => clearTimeout(timer);
    }, [query, userId, searchType]);

    const formatTime = (iso?: string) => {
        if (!iso) return "";
        try {
            const d = new Date(iso);
            return d.toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
        } catch {
            return "";
        }
    };

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] px-4 sm:px-6 animate-fadeIn transition-colors duration-500"
            style={{
                background: 'rgba(0, 0, 0, 0.6)',
                backdropFilter: 'blur(8px)',
                WebkitBackdropFilter: 'blur(8px)',
            }}
            onClick={onClose}
        >
            <div
                className="w-full max-w-3xl rounded-2xl sm:rounded-3xl flex flex-col overflow-hidden animate-fadeInUp transition-colors duration-500 shadow-2xl"
                style={{
                    background: 'var(--color-bg-glass-strong)',
                    backdropFilter: 'blur(20px)',
                    WebkitBackdropFilter: 'blur(20px)',
                    border: '1px solid var(--color-border)',
                    maxHeight: '75vh'
                }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* --- SEARCH HEADER --- */}
                <div
                    className="flex items-center px-4 py-3 sm:px-6 sm:py-4 transition-colors duration-500"
                    style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                >
                    <svg className="w-6 h-6 sm:w-7 sm:h-7 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--color-text-tertiary)' }}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                    </svg>

                    <input
                        ref={inputRef}
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder={placeholder}
                        // THE FIX: Total annihilation of browser defaults and form plugin rings
                        className="flex-1 bg-transparent appearance-none border-0 outline-none focus:outline-none focus:ring-0 focus:ring-offset-0 focus:border-0 shadow-none focus:shadow-none text-base sm:text-lg px-4 transition-colors m-0"
                        style={{
                            color: 'var(--color-text-primary)',
                            boxShadow: 'none'
                        }}
                    />

                    {isSearching && (
                        <svg className="w-5 h-5 animate-spin mr-3 flex-shrink-0" style={{ color: 'var(--color-accent-primary)' }} fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    )}

                    <button
                        onClick={onClose}
                        className="p-2 rounded-xl transition-colors hover:bg-black/5 dark:hover:bg-white/10 flex-shrink-0"
                        style={{ color: 'var(--color-text-secondary)' }}
                    >
                        <svg className="w-5 h-5 sm:w-6 sm:h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* --- RESULTS BODY --- */}
                {query.trim() !== "" && (
                    <div className="overflow-y-auto overflow-x-hidden scrollbar-hide flex-1">
                        {results.length > 0 ? (
                            <div className="flex flex-col">
                                {results.map((result) => {
                                    const timeStr = formatTime(result.start || result.due_date || result.trigger_time);
                                    const isHighRisk = result.priority === 1 || result.priority === "high";
                                    const isCompleted = result.status === "completed" || result.status === "delivered" || result.status === "dismissed";

                                    return (
                                        <button
                                            key={result.id}
                                            onClick={() => {
                                                onClose();
                                                onResultClick(result);
                                            }}
                                            className="flex flex-col items-start px-4 py-4 sm:px-6 sm:py-5 w-full text-left transition-colors hover:bg-black/5 dark:hover:bg-white/5 active:scale-[0.99]"
                                            style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                                        >
                                            <div className="flex w-full justify-between items-start gap-3">
                                                <span
                                                    className={`text-base sm:text-lg font-bold truncate ${isCompleted ? 'line-through' : ''}`}
                                                    style={{ color: isCompleted ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}
                                                >
                                                    {result.title || "Untitled"}
                                                </span>

                                                <div className="flex items-center gap-1.5 flex-shrink-0">
                                                    {isCompleted && (
                                                        <span className="px-2 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-widest rounded-md border" style={{ background: 'var(--color-success-bg)', color: 'var(--color-success)', borderColor: 'var(--color-success)' }}>
                                                            Done
                                                        </span>
                                                    )}
                                                    {isHighRisk && !isCompleted && (
                                                        <span className="px-2 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-widest rounded-md border" style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)', borderColor: 'var(--color-danger)' }}>
                                                            High
                                                        </span>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Rich Metadata Row with SVGs */}
                                            <div className="flex flex-wrap items-center gap-2 mt-2.5 sm:mt-3">
                                                {timeStr && (
                                                    <span className="text-xs sm:text-sm font-semibold" style={{ color: 'var(--color-accent-primary)' }}>
                                                        {timeStr}
                                                    </span>
                                                )}

                                                {/* --- TASK BADGES --- */}
                                                {result.type === 'task' && result.estimated_duration && (
                                                    <span className="flex items-center gap-1 px-1.5 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-wider rounded border" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                        </svg>
                                                        {result.estimated_duration} mins
                                                    </span>
                                                )}
                                                {result.type === 'task' && result.energy_level && (
                                                    <span className="flex items-center gap-1 px-1.5 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-wider rounded border" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                        </svg>
                                                        {result.energy_level}
                                                    </span>
                                                )}

                                                {/* --- EVENT BADGES --- */}
                                                {result.type === 'event' && result.category && (
                                                    <span className="flex items-center gap-1 px-1.5 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-wider rounded border" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                                                        </svg>
                                                        {result.category.replace('_', ' ')}
                                                    </span>
                                                )}
                                                {result.type === 'event' && result.location && (
                                                    <span className="flex items-center gap-1 px-1.5 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-wider rounded border max-w-[12rem] truncate" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}>
                                                        <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
                                                        </svg>
                                                        <span className="truncate">{result.location}</span>
                                                    </span>
                                                )}

                                                {/* --- REMINDER BADGES --- */}
                                                {result.type === 'reminder' && result.trigger_type === 'location' ? (
                                                    <span className="flex items-center gap-1 px-1.5 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-wider rounded border" style={{ background: 'var(--color-warning-bg)', borderColor: 'var(--color-warning)', color: 'var(--color-warning)' }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
                                                        </svg>
                                                        Location
                                                    </span>
                                                ) : result.type === 'reminder' && result.trigger_type === 'time' ? (
                                                    <span className="flex items-center gap-1 px-1.5 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-wider rounded border" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                        </svg>
                                                        Time
                                                    </span>
                                                ) : null}
                                                {result.type === 'reminder' && result.repeat && result.repeat !== 'none' && (
                                                    <span className="flex items-center gap-1 px-1.5 py-0.5 text-[0.6rem] sm:text-xs font-bold uppercase tracking-wider rounded border" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                                                        </svg>
                                                        {result.repeat}
                                                    </span>
                                                )}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        ) : !isSearching ? (
                            <div className="py-12 text-center flex flex-col items-center gap-3">
                                <svg className="w-8 h-8 opacity-50" style={{ color: 'var(--color-text-tertiary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                                </svg>
                                <span className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                                    No results found for "{query}"
                                </span>
                            </div>
                        ) : null}
                    </div>
                )}
            </div>
        </div>
    );
}