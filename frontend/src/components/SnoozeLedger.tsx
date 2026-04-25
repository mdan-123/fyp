"use client";

import { useState, useEffect, useCallback } from "react";
import { auth } from "@/lib/firebase";
import { fetchWithRetry } from "@/lib/fetchUtils";

type SnoozeLedgerProps = {
    userId: string;
    onBack: () => void;
};

type SnoozedTask = {
    id: string;
    type: "task";
    title: string;
    description: string;
    snooze_count: number;
    due_date: string | null;
    start_date: string | null;
    estimated_duration: number | null;
    category: string | null;
    tags: string[];
    priority: number | null;
    energy_level: string | null;
    status: string;
};

type SnoozedEvent = {
    id: string;
    type: "event";
    title: string;
    description: string;
    snooze_count: number;
    start: string | null;
    end: string | null;
    duration_mins: number | null;
    category: string | null;
    location: string;
    completion_status: string;
};

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

function formatDate(iso: string | null): string {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return "—";
    }
}

function formatDuration(mins: number | null): string {
    if (!mins || mins <= 0) return "—";
    if (mins < 60) return `${mins} min`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

const PRIORITY_LABELS: Record<number, string> = { 1: "Critical", 2: "High", 3: "Medium", 4: "Low", 5: "Optional" };
const ENERGY_LABELS: Record<string, string> = { low: "Low energy", medium: "Medium energy", high: "High energy" };

export default function SnoozeLedger({ userId, onBack }: SnoozeLedgerProps) {
    const [tasks, setTasks] = useState<SnoozedTask[]>([]);
    const [events, setEvents] = useState<SnoozedEvent[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [clearingId, setClearingId] = useState<string | null>(null);
    const [isResetting, setIsResetting] = useState(false);
    const [successMsg, setSuccessMsg] = useState<string | null>(null);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    const showSuccess = (msg: string) => {
        setSuccessMsg(msg);
        setTimeout(() => setSuccessMsg(null), 3000);
    };

    const showError = (msg: string) => {
        setErrorMsg(msg);
        setTimeout(() => setErrorMsg(null), 4000);
    };

    const fetchSnoozed = useCallback(async () => {
        setIsLoading(true);
        try {
            const token = await auth.currentUser?.getIdToken();
            const res = await fetchWithRetry(
                `${API_BASE_URL}/api/analytics/snoozed/${userId}`,
                {
                    method: "GET",
                    headers: { Authorization: `Bearer ${token}` },
                    timeoutMs: 10000,
                },
            );
            if (res.ok) {
                const data = await res.json();
                setTasks(data.tasks ?? []);
                setEvents(data.events ?? []);
            } else {
                showError("Failed to load snoozed items.");
            }
        } catch {
            showError("Network error loading snoozed items.");
        } finally {
            setIsLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        fetchSnoozed();
    }, [fetchSnoozed]);

    const handleClearSnooze = async (id: string, type: "task" | "event") => {
        setClearingId(id);
        try {
            const token = await auth.currentUser?.getIdToken();
            const res = await fetchWithRetry(`${API_BASE_URL}/api/analytics/clear-snooze`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ user_id: userId, item_id: id, item_type: type }),
                timeoutMs: 8000,
            });
            if (res.ok) {
                if (type === "task") {
                    setTasks((prev) => prev.filter((t) => t.id !== id));
                } else {
                    setEvents((prev) => prev.filter((e) => e.id !== id));
                }
                showSuccess("Snooze count cleared.");
            } else {
                showError("Failed to clear snooze.");
            }
        } catch {
            showError("Network error clearing snooze.");
        } finally {
            setClearingId(null);
        }
    };

    const handleResetRefunded = async () => {
        setIsResetting(true);
        try {
            const token = await auth.currentUser?.getIdToken();
            const res = await fetchWithRetry(
                `${API_BASE_URL}/api/analytics/reset-refunded/${userId}`,
                {
                    method: "POST",
                    headers: { Authorization: `Bearer ${token}` },
                    timeoutMs: 10000,
                },
            );
            if (res.ok) {
                showSuccess("Time refunded counter has been reset to zero.");
            } else {
                showError("Failed to reset counter.");
            }
        } catch {
            showError("Network error resetting counter.");
        } finally {
            setIsResetting(false);
        }
    };

    const isEmpty = tasks.length === 0 && events.length === 0;

    return (
        <div className="min-h-screen font-sans flex flex-col pb-32 bg-transparent transition-colors duration-500">
            {/* Header */}
            <div
                className="sticky top-0 z-10 px-4 py-3 flex items-center justify-between"
                style={{
                    paddingTop: "calc(env(safe-area-inset-top, 20px) + 8px)",
                    background: "var(--color-bg-glass)",
                    backdropFilter: "blur(var(--blur-lg))",
                    WebkitBackdropFilter: "blur(var(--blur-lg))",
                    borderBottom: "1px solid var(--color-border)",
                }}
            >
                <button
                    onClick={onBack}
                    className="flex items-center gap-1 text-[16px] font-semibold transition-colors active:opacity-50"
                    style={{ color: "var(--color-accent-primary)" }}
                >
                    <span className="text-2xl leading-none">‹</span> Settings
                </button>
                <span
                    className="text-[15px] font-bold truncate px-4 transition-colors duration-200"
                    style={{ color: "var(--color-text-primary)" }}
                >
                    Snooze Ledger
                </span>
                <div className="w-16" />
            </div>

            <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-10 animate-fadeIn">
                {/* Title */}
                <div className="space-y-2 text-center md:text-left">
                    <h2
                        className="text-3xl font-extrabold tracking-tight transition-colors duration-200"
                        style={{ color: "var(--color-text-primary)" }}
                    >
                        Snooze Ledger
                    </h2>
                    <p
                        className="text-sm max-w-xl transition-colors duration-200"
                        style={{ color: "var(--color-text-secondary)" }}
                    >
                        View everything that has been rescheduled. Remove the snooze marker
                        from items that were moved for legitimate reasons, not procrastination.
                    </p>
                </div>

                {/* Toast messages */}
                {successMsg && (
                    <div
                        className="p-3 rounded-xl flex items-center gap-2 text-sm font-medium"
                        style={{
                            background: "var(--color-success-bg)",
                            color: "var(--color-success)",
                            border: "1px solid var(--color-success)",
                        }}
                    >
                        <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        {successMsg}
                    </div>
                )}
                {errorMsg && (
                    <div
                        className="p-3 rounded-xl flex items-center gap-2 text-sm font-medium"
                        style={{
                            background: "var(--color-danger-bg)",
                            color: "var(--color-danger)",
                            border: "1px solid var(--color-danger)",
                        }}
                    >
                        <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        {errorMsg}
                    </div>
                )}

                {isLoading ? (
                    <div className="flex justify-center py-10">
                        <svg
                            className="w-6 h-6 animate-spin"
                            style={{ color: "var(--color-accent-primary)" }}
                            fill="none"
                            viewBox="0 0 24 24"
                        >
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                    </div>
                ) : isEmpty ? (
                    <div
                        className="rounded-2xl p-8 flex flex-col items-center gap-3 transition-all duration-200"
                        style={{
                            background: "var(--color-bg-glass)",
                            border: "1px solid var(--color-border)",
                        }}
                    >
                        <div
                            className="w-12 h-12 rounded-xl flex items-center justify-center"
                            style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)" }}
                        >
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} style={{ color: "var(--color-text-tertiary)" }}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <p className="text-sm font-medium" style={{ color: "var(--color-text-secondary)" }}>
                            No snoozed items — you&apos;re right on track.
                        </p>
                    </div>
                ) : (
                    <>
                        {/* Snoozed Tasks */}
                        {tasks.length > 0 && (
                            <div className="space-y-3">
                                <h3
                                    className="text-[11px] uppercase tracking-[0.15em] font-semibold px-1"
                                    style={{ color: "var(--color-text-tertiary)" }}
                                >
                                    Tasks ({tasks.length})
                                </h3>
                                <div className="space-y-3">
                                    {tasks.map((task) => (
                                        <div
                                            key={task.id}
                                            className="rounded-2xl p-5 transition-all duration-200"
                                            style={{
                                                background: "var(--color-bg-glass-strong)",
                                                backdropFilter: "blur(20px)",
                                                WebkitBackdropFilter: "blur(20px)",
                                                border: "1px solid var(--color-border)",
                                                boxShadow: "var(--shadow-lg)",
                                            }}
                                        >
                                            {/* Title row */}
                                            <div className="flex items-start justify-between gap-3 mb-3">
                                                <p className="text-[15px] font-bold leading-snug" style={{ color: "var(--color-text-primary)" }}>
                                                    {task.title}
                                                </p>
                                                <span
                                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold flex-shrink-0"
                                                    style={{
                                                        background: "var(--color-warning-bg, rgba(245,158,11,0.1))",
                                                        color: "var(--color-warning, #f59e0b)",
                                                        border: "1px solid var(--color-warning, #f59e0b)",
                                                    }}
                                                >
                                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                    </svg>
                                                    Snoozed {task.snooze_count}×
                                                </span>
                                            </div>

                                            {/* Description */}
                                            {task.description && (
                                                <p className="text-xs leading-relaxed mb-3" style={{ color: "var(--color-text-secondary)" }}>
                                                    {task.description}
                                                </p>
                                            )}

                                            {/* Detail chips */}
                                            <div className="flex flex-wrap gap-2 mb-4">
                                                {task.start_date && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                                                        Start: {formatDate(task.start_date)}
                                                    </span>
                                                )}
                                                {task.due_date && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                                        Due: {formatDate(task.due_date)}
                                                    </span>
                                                )}
                                                {task.estimated_duration != null && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                                        {formatDuration(task.estimated_duration)}
                                                    </span>
                                                )}
                                                {task.category && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
                                                        {task.category}
                                                    </span>
                                                )}
                                                {task.priority != null && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        {PRIORITY_LABELS[task.priority] ?? `P${task.priority}`}
                                                    </span>
                                                )}
                                                {task.energy_level && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        ⚡ {ENERGY_LABELS[task.energy_level.toLowerCase()] ?? task.energy_level}
                                                    </span>
                                                )}
                                            </div>

                                            <div className="pt-3" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
                                                <button
                                                    disabled={clearingId === task.id}
                                                    onClick={() => handleClearSnooze(task.id, "task")}
                                                    className="px-4 py-2 rounded-xl text-xs font-semibold transition-all duration-150 active:scale-95 disabled:opacity-50 hover:scale-[1.01]"
                                                    style={{
                                                        background: "var(--color-surface)",
                                                        border: "1px solid var(--color-border)",
                                                        color: "var(--color-text-secondary)",
                                                    }}
                                                >
                                                    {clearingId === task.id ? "Clearing…" : "Clear Snooze"}
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Snoozed Events */}
                        {events.length > 0 && (
                            <div className="space-y-3">
                                <h3
                                    className="text-[11px] uppercase tracking-[0.15em] font-semibold px-1"
                                    style={{ color: "var(--color-text-tertiary)" }}
                                >
                                    Events ({events.length})
                                </h3>
                                <div className="space-y-3">
                                    {events.map((event) => (
                                        <div
                                            key={event.id}
                                            className="rounded-2xl p-5 transition-all duration-200"
                                            style={{
                                                background: "var(--color-bg-glass-strong)",
                                                backdropFilter: "blur(20px)",
                                                WebkitBackdropFilter: "blur(20px)",
                                                border: "1px solid var(--color-border)",
                                                boxShadow: "var(--shadow-lg)",
                                            }}
                                        >
                                            {/* Title row */}
                                            <div className="flex items-start justify-between gap-3 mb-3">
                                                <p className="text-[15px] font-bold leading-snug" style={{ color: "var(--color-text-primary)" }}>
                                                    {event.title}
                                                </p>
                                                <span
                                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold flex-shrink-0"
                                                    style={{
                                                        background: "var(--color-warning-bg, rgba(245,158,11,0.1))",
                                                        color: "var(--color-warning, #f59e0b)",
                                                        border: "1px solid var(--color-warning, #f59e0b)",
                                                    }}
                                                >
                                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                    </svg>
                                                    Snoozed {event.snooze_count}×
                                                </span>
                                            </div>

                                            {/* Description */}
                                            {event.description && (
                                                <p className="text-xs leading-relaxed mb-3" style={{ color: "var(--color-text-secondary)" }}>
                                                    {event.description}
                                                </p>
                                            )}

                                            {/* Detail chips */}
                                            <div className="flex flex-wrap gap-2 mb-4">
                                                {event.start && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                                                        {formatDate(event.start)}
                                                    </span>
                                                )}
                                                {event.end && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                                        Ends {formatDate(event.end)}
                                                    </span>
                                                )}
                                                {event.duration_mins != null && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                                        {formatDuration(event.duration_mins)}
                                                    </span>
                                                )}
                                                {event.category && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
                                                        {event.category}
                                                    </span>
                                                )}
                                                {event.location && (
                                                    <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg" style={{ background: "var(--color-surface)", color: "var(--color-text-tertiary)", border: "1px solid var(--color-border-subtle)" }}>
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                                                        {event.location}
                                                    </span>
                                                )}
                                            </div>

                                            <div className="pt-3" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
                                                <button
                                                    disabled={clearingId === event.id}
                                                    onClick={() => handleClearSnooze(event.id, "event")}
                                                    className="px-4 py-2 rounded-xl text-xs font-semibold transition-all duration-150 active:scale-95 disabled:opacity-50 hover:scale-[1.01]"
                                                    style={{
                                                        background: "var(--color-surface)",
                                                        border: "1px solid var(--color-border)",
                                                        color: "var(--color-text-secondary)",
                                                    }}
                                                >
                                                    {clearingId === event.id ? "Clearing…" : "Clear Snooze"}
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </>
                )}

                {/* Time Refunded Reset */}
                <div className="space-y-3">
                    <h3
                        className="text-[11px] uppercase tracking-[0.15em] font-semibold px-1"
                        style={{ color: "var(--color-text-tertiary)" }}
                    >
                        Time Refunded Counter
                    </h3>
                    <div
                        className="rounded-2xl p-5 transition-all duration-200"
                        style={{
                            background: "var(--color-bg-glass-strong)",
                            backdropFilter: "blur(20px)",
                            WebkitBackdropFilter: "blur(20px)",
                            border: "1px solid var(--color-border)",
                            boxShadow: "var(--shadow-lg)",
                        }}
                    >
                        <div className="flex items-start gap-4">
                            <div
                                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
                                style={{
                                    background: "var(--color-surface)",
                                    border: "1px solid var(--color-border-subtle)",
                                }}
                            >
                                <svg
                                    className="w-5 h-5"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    strokeWidth={1.5}
                                    style={{ color: "var(--color-accent-primary)" }}
                                >
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                                </svg>
                            </div>
                            <div className="flex-1">
                                <p
                                    className="text-[15px] font-semibold"
                                    style={{ color: "var(--color-text-primary)" }}
                                >
                                    Reset Refunded Counter
                                </p>
                                <p
                                    className="text-xs mt-1 leading-relaxed"
                                    style={{ color: "var(--color-text-tertiary)" }}
                                >
                                    Resets the &quot;time refunded&quot; value shown in your analytics back
                                    to zero. Future refunds will accumulate from this point.
                                </p>
                                <button
                                    onClick={handleResetRefunded}
                                    disabled={isResetting}
                                    className="mt-4 px-5 py-2.5 rounded-xl text-sm font-bold transition-all duration-150 active:scale-95 disabled:opacity-50 hover:scale-[1.01]"
                                    style={{
                                        background: "var(--color-danger-bg)",
                                        color: "var(--color-danger)",
                                        border: "1px solid var(--color-danger)",
                                    }}
                                >
                                    {isResetting ? "Resetting…" : "Reset to Zero"}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
