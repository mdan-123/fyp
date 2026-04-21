"use client";

import { useState, useEffect } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";
import { auth } from "@/lib/firebase";

type ShowWeekendsSettingsProps = {
    userId: string;
    onBack: () => void;
};

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function ShowWeekendsSettings({
    userId,
    onBack,
}: ShowWeekendsSettingsProps) {
    const [showWeekends, setShowWeekends] = useState<boolean>(true);
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    useEffect(() => {
        const fetchSetting = async () => {
            try {
                const token = await auth.currentUser?.getIdToken();
                const res = await fetchWithRetry(
                    `${API_BASE_URL}/api/users/show-weekends/${userId}`,
                    {
                        method: "GET",
                        headers: { "Authorization": `Bearer ${token}` },
                        timeoutMs: 8000,
                    },
                );
                if (res.ok) {
                    const data = await res.json();
                    setShowWeekends(data.show_weekends ?? true);
                }
            } catch (error) {
                console.error("Error fetching show weekends setting:", error);
            } finally {
                setIsLoading(false);
            }
        };
        fetchSetting();
    }, [userId]);

    const handleToggle = async (value: boolean) => {
        setShowWeekends(value);
        setIsSubmitting(true);
        setSuccessMessage(null);

        try {
            const token = await auth.currentUser?.getIdToken();
            const res = await fetchWithRetry(
                `${API_BASE_URL}/api/users/show-weekends`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                    body: JSON.stringify({ user_id: userId, show_weekends: value }),
                    timeoutMs: 8000,
                },
            );

            if (res.ok) {
                setSuccessMessage(
                    value
                        ? "Weekends will now be shown."
                        : "Weekends hidden — more space for your week.",
                );
                setTimeout(() => setSuccessMessage(null), 3000);
            } else {
                console.error("Failed to update show weekends setting");
            }
        } catch (error) {
            console.error("Network error saving show weekends:", error);
        } finally {
            setIsSubmitting(false);
        }
    };

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
                    Calendar Display
                </span>

                <div className="w-16" />
            </div>

            <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-10 animate-fadeIn">
                <div className="space-y-2 text-center md:text-left">
                    <h2
                        className="text-3xl font-extrabold tracking-tight transition-colors duration-200"
                        style={{ color: "var(--color-text-primary)" }}
                    >
                        Calendar Display
                    </h2>
                    <p
                        className="text-sm max-w-xl transition-colors duration-200"
                        style={{ color: "var(--color-text-secondary)" }}
                    >
                        Control how your week view is laid out. Hiding weekends gives each
                        weekday more space so event titles are never cut off.
                    </p>
                </div>

                {isLoading ? (
                    <div className="flex justify-center py-10">
                        <svg
                            className="w-6 h-6 animate-spin"
                            style={{ color: "var(--color-accent-primary)" }}
                            fill="none"
                            viewBox="0 0 24 24"
                        >
                            <circle
                                className="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                strokeWidth="4"
                            />
                            <path
                                className="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                            />
                        </svg>
                    </div>
                ) : (
                    <div
                        className="rounded-2xl overflow-hidden transition-all duration-200"
                        style={{
                            background: "var(--color-bg-glass-strong)",
                            backdropFilter: "blur(20px)",
                            WebkitBackdropFilter: "blur(20px)",
                            border: "1px solid var(--color-border)",
                            boxShadow: "var(--shadow-lg)",
                        }}
                    >
                        {/* Show Weekends toggle row */}
                        <button
                            onClick={() => handleToggle(true)}
                            disabled={isSubmitting}
                            className="w-full flex items-center justify-between px-6 py-4 transition-all duration-200 active:opacity-70"
                            style={{
                                background: showWeekends
                                    ? "var(--color-surface-hover)"
                                    : "transparent",
                                borderBottom: "1px solid var(--color-border-subtle)",
                            }}
                        >
                            <div className="flex items-center gap-4">
                                <div
                                    className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors duration-200"
                                    style={{
                                        background: showWeekends
                                            ? "var(--color-accent-glow)"
                                            : "var(--color-surface)",
                                        border: "1px solid var(--color-border)",
                                    }}
                                >
                                    <svg
                                        className="w-5 h-5"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={1.5}
                                        style={{
                                            color: showWeekends
                                                ? "var(--color-accent-primary)"
                                                : "var(--color-text-tertiary)",
                                        }}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"
                                        />
                                    </svg>
                                </div>
                                <div className="text-left">
                                    <p
                                        className="text-[15px] font-semibold transition-colors duration-200"
                                        style={{ color: "var(--color-text-primary)" }}
                                    >
                                        Show Weekends
                                    </p>
                                    <p
                                        className="text-[12px] mt-0.5 transition-colors duration-200"
                                        style={{ color: "var(--color-text-secondary)" }}
                                    >
                                        Saturday & Sunday visible in week view
                                    </p>
                                </div>
                            </div>
                            {showWeekends && (
                                <svg
                                    className="w-5 h-5 flex-shrink-0"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    strokeWidth={2.5}
                                    style={{ color: "var(--color-accent-primary)" }}
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d="M4.5 12.75l6 6 9-13.5"
                                    />
                                </svg>
                            )}
                        </button>

                        {/* Hide Weekends row */}
                        <button
                            onClick={() => handleToggle(false)}
                            disabled={isSubmitting}
                            className="w-full flex items-center justify-between px-6 py-4 transition-all duration-200 active:opacity-70"
                            style={{
                                background: !showWeekends
                                    ? "var(--color-surface-hover)"
                                    : "transparent",
                            }}
                        >
                            <div className="flex items-center gap-4">
                                <div
                                    className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors duration-200"
                                    style={{
                                        background: !showWeekends
                                            ? "var(--color-accent-glow)"
                                            : "var(--color-surface)",
                                        border: "1px solid var(--color-border)",
                                    }}
                                >
                                    <svg
                                        className="w-5 h-5"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={1.5}
                                        style={{
                                            color: !showWeekends
                                                ? "var(--color-accent-primary)"
                                                : "var(--color-text-tertiary)",
                                        }}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"
                                        />
                                    </svg>
                                </div>
                                <div className="text-left">
                                    <p
                                        className="text-[15px] font-semibold transition-colors duration-200"
                                        style={{ color: "var(--color-text-primary)" }}
                                    >
                                        Hide Weekends
                                    </p>
                                    <p
                                        className="text-[12px] mt-0.5 transition-colors duration-200"
                                        style={{ color: "var(--color-text-secondary)" }}
                                    >
                                        Mon–Fri only — more room for each day's events
                                    </p>
                                </div>
                            </div>
                            {!showWeekends && (
                                <svg
                                    className="w-5 h-5 flex-shrink-0"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    strokeWidth={2.5}
                                    style={{ color: "var(--color-accent-primary)" }}
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d="M4.5 12.75l6 6 9-13.5"
                                    />
                                </svg>
                            )}
                        </button>
                    </div>
                )}

                {/* Success / saving feedback */}
                {(successMessage || isSubmitting) && (
                    <div
                        className="flex items-center gap-3 px-5 py-3.5 rounded-2xl text-sm font-medium transition-all duration-300"
                        style={{
                            background: isSubmitting
                                ? "var(--color-surface)"
                                : "var(--color-success-bg)",
                            border: `1px solid ${isSubmitting ? "var(--color-border)" : "var(--color-success)"}`,
                            color: isSubmitting
                                ? "var(--color-text-secondary)"
                                : "var(--color-success)",
                        }}
                    >
                        {isSubmitting ? (
                            <>
                                <svg
                                    className="w-4 h-4 animate-spin flex-shrink-0"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                >
                                    <circle
                                        className="opacity-25"
                                        cx="12"
                                        cy="12"
                                        r="10"
                                        stroke="currentColor"
                                        strokeWidth="4"
                                    />
                                    <path
                                        className="opacity-75"
                                        fill="currentColor"
                                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                    />
                                </svg>
                                Saving…
                            </>
                        ) : (
                            <>
                                <svg
                                    className="w-4 h-4 flex-shrink-0"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    strokeWidth={2.5}
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d="M4.5 12.75l6 6 9-13.5"
                                    />
                                </svg>
                                {successMessage}
                            </>
                        )}
                    </div>
                )}

                {/* Informational note */}
                <div
                    className="flex gap-3 p-4 rounded-2xl text-sm transition-colors duration-200"
                    style={{
                        background: "var(--color-surface)",
                        border: "1px solid var(--color-border)",
                        color: "var(--color-text-secondary)",
                    }}
                >
                    <svg
                        className="w-5 h-5 flex-shrink-0 mt-0.5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={1.5}
                        style={{ color: "var(--color-text-tertiary)" }}
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
                        />
                    </svg>
                    <p>
                        This only affects the <strong>week view</strong> timeline. Month and
                        day views are unchanged. Events on hidden days are still saved and
                        searchable.
                    </p>
                </div>
            </div>
        </div>
    );
}
