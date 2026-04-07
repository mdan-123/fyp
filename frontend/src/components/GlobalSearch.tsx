"use client";

import { useState, useEffect, useRef } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

type SearchType = "events" | "tasks" | "reminders" | "all";

interface SearchResult {
    id: string;
    type: "event" | "task" | "reminder";
    title: string;
    status: string;
    start?: string;
    due_date?: string;
    trigger_time?: string;
    priority?: number | string;
}

interface GlobalSearchProps {
    userId: string;
    searchType: SearchType;
    onResultClick: (result: SearchResult) => void;
    placeholder?: string;
}

export default function GlobalSearch({ userId, searchType, onResultClick, placeholder = "Search..." }: GlobalSearchProps) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [isExpanded, setIsExpanded] = useState(false);
    const [isOpen, setIsOpen] = useState(false); // Controls the dropdown

    const wrapperRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Handle clicking outside to close dropdown and collapse search
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
                setIsOpen(false);
                if (!query.trim()) {
                    setIsExpanded(false);
                }
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [query]);

    // Auto-focus when expanded
    useEffect(() => {
        if (isExpanded && inputRef.current) {
            inputRef.current.focus();
        }
    }, [isExpanded]);

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
                const res = await fetchWithRetry(`${API_BASE_URL}/api/search`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
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

    return (
        <div className="relative z-50 flex justify-end" ref={wrapperRef}>
            {/* Search Bar Container */}
            <div
                className={`flex items-center h-10 sm:h-11 rounded-full transition-all duration-300 ease-in-out overflow-hidden`}
                style={{
                    width: isExpanded ? '240px' : '40px', // or '44px' for sm screens
                    background: isExpanded ? 'var(--color-bg-glass)' : 'transparent',
                    border: isExpanded ? '1px solid var(--color-border)' : '1px solid transparent',
                    boxShadow: isExpanded ? 'var(--shadow-sm)' : 'none',
                }}
            >
                {/* Search Icon Button */}
                <button
                    onClick={() => setIsExpanded(true)}
                    className={`flex items-center justify-center h-full aspect-square transition-colors duration-200 rounded-full ${!isExpanded ? 'hover:bg-white/10 dark:hover:bg-black/10' : ''}`}
                    style={{ color: isExpanded ? 'var(--color-text-secondary)' : 'var(--color-text-primary)' }}
                >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                    </svg>
                </button>

                {/* Input Field (Fades in/out) */}
                <div className={`flex-1 flex items-center h-full transition-opacity duration-300 ${isExpanded ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
                    <input
                        ref={inputRef}
                        type="text"
                        value={query}
                        onChange={(e) => {
                            setQuery(e.target.value);
                            setIsOpen(true);
                        }}
                        placeholder={placeholder}
                        className="w-full h-full bg-transparent border-none outline-none text-sm px-1"
                        style={{ color: 'var(--color-text-primary)' }}
                    />

                    {/* Right-side action (Loading spinner or Clear button) */}
                    <div className="flex items-center justify-center w-10 h-full flex-shrink-0">
                        {isSearching ? (
                            <svg className="w-4 h-4 animate-spin" style={{ color: 'var(--color-accent-primary)' }} fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        ) : query && (
                            <button
                                onClick={() => {
                                    setQuery("");
                                    inputRef.current?.focus();
                                }}
                                className="p-1 rounded-full hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                                style={{ color: 'var(--color-text-tertiary)' }}
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Dropdown Results */}
            {isOpen && query.trim() !== "" && isExpanded && (
                <div
                    className="absolute top-[calc(100%+8px)] right-0 w-[280px] sm:w-[320px] rounded-xl overflow-hidden animate-fade-in-down"
                    style={{
                        background: 'var(--color-bg-glass-strong)',
                        backdropFilter: 'blur(20px)',
                        WebkitBackdropFilter: 'blur(20px)',
                        border: '1px solid var(--color-border)',
                        boxShadow: 'var(--shadow-xl)',
                        maxHeight: '350px',
                        overflowY: 'auto'
                    }}
                >
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
                                            setIsOpen(false);
                                            setIsExpanded(false);
                                            setQuery("");
                                            onResultClick(result);
                                        }}
                                        className="flex flex-col items-start px-4 py-3.5 text-left transition-colors hover:bg-black/5 dark:hover:bg-white/5 active:scale-[0.99]"
                                        style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                                    >
                                        <div className="flex w-full justify-between items-start gap-2">
                                            <span
                                                className={`text-sm font-bold truncate ${isCompleted ? 'line-through' : ''}`}
                                                style={{ color: isCompleted ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}
                                            >
                                                {result.title || "Untitled"}
                                            </span>
                                            {isHighRisk && !isCompleted && (
                                                <span className="flex-shrink-0 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded-md" style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)' }}>
                                                    High
                                                </span>
                                            )}
                                        </div>

                                        {timeStr && (
                                            <span className="text-xs font-semibold mt-1" style={{ color: 'var(--color-accent-primary)' }}>
                                                {timeStr}
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    ) : !isSearching ? (
                        <div className="p-5 text-center text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                            No results found for "{query}"
                        </div>
                    ) : null}
                </div>
            )}
        </div>
    );
}