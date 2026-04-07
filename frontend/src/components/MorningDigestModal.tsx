"use client";

import { useState, useEffect } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

interface MorningDigestModalProps {
    isOpen: boolean;
    onClose: () => void;
    userId: string;
    onEventClick: (event: any) => void;
    onTaskClick: (task: any) => void;
}

export default function MorningDigestModal({ isOpen, onClose, userId, onEventClick, onTaskClick }: MorningDigestModalProps) {
    const [isLoading, setIsLoading] = useState(true);
    const [digestData, setDigestData] = useState<any>(null);

    useEffect(() => {
        if (isOpen && userId) {
            fetchDigest();
        }
    }, [isOpen, userId]);

    const fetchDigest = async () => {
        setIsLoading(true);
        try {
            const now = new Date();
            const yyyy = now.getFullYear();
            const mm = String(now.getMonth() + 1).padStart(2, '0');
            const dd = String(now.getDate()).padStart(2, '0');
            const localDateStr = `${yyyy}-${mm}-${dd}`;
            const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

            const res = await fetchWithRetry(`${API_BASE_URL}/api/ai/daily-digest`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: userId,
                    local_date: localDateStr,
                    timezone: userTimezone
                }),
            });

            if (res.ok) {
                const json = await res.json();
                setDigestData(json.data);
            }
        } catch (error) {
            console.error("Failed to fetch digest", error);
        } finally {
            setIsLoading(false);
        }
    };

    if (!isOpen) return null;

    const events = digestData?.events || [];
    const tasks = digestData?.high_priority_tasks || [];
    const textBriefing = digestData?.digest_text || "";

    return (
        <div
            className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 animate-fadeIn transition-colors duration-500"
            style={{ background: 'rgba(0, 0, 0, 0.6)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' }}
        >
            <div
                className="w-full max-w-lg rounded-2xl sm:rounded-3xl flex flex-col overflow-hidden animate-fadeInUp shadow-2xl transition-colors duration-500"
                style={{
                    background: 'var(--color-bg-glass-strong)',
                    backdropFilter: 'blur(24px)',
                    WebkitBackdropFilter: 'blur(24px)',
                    border: '1px solid var(--color-border)',
                    maxHeight: '90vh'
                }}
            >
                {/* Header Icon */}
                <div className="px-6 pt-6 pb-2 text-center">
                    <div className="w-12 h-12 mx-auto rounded-full flex items-center justify-center shadow-md" style={{ background: 'var(--color-accent-gradient)' }}>
                        <svg className="w-6 h-6" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
                        </svg>
                    </div>
                </div>

                {/* Body */}
                <div className="overflow-y-auto px-4 sm:px-6 pb-6 scrollbar-hide flex-1">
                    {isLoading ? (
                        <div className="flex justify-center items-center py-12">
                            <svg className="w-8 h-8 animate-spin" style={{ color: 'var(--color-accent-primary)' }} fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </div>
                    ) : (
                        <div className="space-y-6">

                            {/* Detailed Text Briefing */}
                            <div
                                className="text-sm font-medium leading-relaxed whitespace-pre-wrap p-4 rounded-xl"
                                style={{
                                    color: 'var(--color-text-secondary)',
                                    background: 'var(--color-surface)',
                                    border: '1px solid var(--color-border-subtle)'
                                }}
                            >
                                {textBriefing}
                            </div>

                            {/* Interactive Elements (Only render if there are items) */}
                            {(events.length > 0 || tasks.length > 0) && (
                                <div className="space-y-4 pt-4" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>

                                    {events.length > 0 && (
                                        <div className="space-y-2">
                                            <h3 className="text-xs font-bold uppercase tracking-widest px-1" style={{ color: 'var(--color-text-tertiary)' }}>Interactive Calendar</h3>
                                            <div className="flex flex-col gap-2">
                                                {events.map((ev: any) => (
                                                    <button
                                                        key={ev.id}
                                                        onClick={() => { onClose(); onEventClick(ev); }}
                                                        className="flex items-center text-left w-full p-3 rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] shadow-sm hover:shadow-md"
                                                        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
                                                    >
                                                        <div className="w-10 text-center flex-shrink-0 border-r pr-3 mr-3" style={{ borderColor: 'var(--color-border-subtle)' }}>
                                                            <span className="text-xs font-bold" style={{ color: 'var(--color-accent-primary)' }}>{ev.formatted_time}</span>
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <span className="text-sm font-bold truncate block" style={{ color: 'var(--color-text-primary)' }}>{ev.title}</span>
                                                            {ev.location && <span className="text-[0.65rem] sm:text-xs font-medium truncate block mt-0.5" style={{ color: 'var(--color-text-tertiary)' }}>{ev.location}</span>}
                                                        </div>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {tasks.length > 0 && (
                                        <div className="space-y-2 pt-2">
                                            <h3 className="text-xs font-bold uppercase tracking-widest px-1" style={{ color: 'var(--color-danger)' }}>Interactive Priority Tasks</h3>
                                            <div className="flex flex-col gap-2">
                                                {tasks.map((task: any) => (
                                                    <button
                                                        key={task.id}
                                                        onClick={() => { onClose(); onTaskClick(task); }}
                                                        className="flex justify-between items-center text-left w-full p-3 rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] shadow-sm hover:shadow-md"
                                                        style={{ background: 'var(--color-danger-bg)', border: '1px solid var(--color-danger)' }}
                                                    >
                                                        <span className="text-sm font-bold truncate pr-3" style={{ color: 'var(--color-danger)' }}>{task.title}</span>
                                                        <svg className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--color-danger)' }} fill="currentColor" viewBox="0 0 20 20">
                                                            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                                                        </svg>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4" style={{ borderTop: '1px solid var(--color-border-subtle)', background: 'var(--color-bg-glass-strong)' }}>
                    <button
                        onClick={onClose}
                        className="w-full btn-primary py-3 text-sm uppercase tracking-wider font-bold rounded-xl"
                    >
                        Start Day
                    </button>
                </div>
            </div>
        </div>
    );
}