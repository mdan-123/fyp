"use client";

import { useState, useEffect } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";
import { auth } from "@/lib/firebase";

type SchedulingSettingsProps = {
    readonly userId: string;
    readonly onBack: () => void;
};

type SchedulingSettingsState = {
    optimisation_window_days: number;
    optimise_weekends: boolean;
    schedule_on_weekends: boolean;
    routines_on_weekends: boolean;
    scheduling_start_hour: number;
    scheduling_end_hour: number;
};

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

const WINDOW_OPTIONS = [7, 14, 21, 30] as const;

const CheckIcon = ({ color }: { color?: string }) => (
    <svg
        className="w-5 h-5 flex-shrink-0"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2.5}
        style={{ color: color ?? "var(--color-accent-primary)" }}
    >
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
    </svg>
);

const SpinnerIcon = ({ className }: { className?: string }) => (
    <svg
        className={`animate-spin ${className ?? "w-6 h-6"}`}
        style={{ color: "var(--color-accent-primary)" }}
        fill="none"
        viewBox="0 0 24 24"
    >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
    </svg>
);

const formatHour = (h: number): string => {
    if (h === 0 || h === 24) return "12 am";
    if (h === 12) return "12 pm";
    if (h > 12) return `${h - 12} pm`;
    return `${h} am`;
};

export default function SchedulingSettings({ userId, onBack }: SchedulingSettingsProps) {
    const [settings, setSettings] = useState<SchedulingSettingsState>({
        optimisation_window_days: 7,
        optimise_weekends: false,
        schedule_on_weekends: false,
        routines_on_weekends: false,
        scheduling_start_hour: 8,
        scheduling_end_hour: 22,
    });
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const token = await auth.currentUser?.getIdToken();
                const res = await fetchWithRetry(
                    `${API_BASE_URL}/api/users/scheduling-settings/${userId}`,
                    {
                        method: "GET",
                        headers: { Authorization: `Bearer ${token}` },
                        timeoutMs: 8000,
                    },
                );
                if (res.ok) {
                    const data = await res.json();
                    setSettings({
                        optimisation_window_days: data.optimisation_window_days ?? 7,
                        optimise_weekends: data.optimise_weekends ?? false,
                        schedule_on_weekends: data.schedule_on_weekends ?? false,
                        routines_on_weekends: data.routines_on_weekends ?? false,
                        scheduling_start_hour: data.scheduling_start_hour ?? 8,
                        scheduling_end_hour: data.scheduling_end_hour ?? 22,
                    });
                }
            } catch (error) {
                console.error("Error fetching scheduling settings:", error);
            } finally {
                setIsLoading(false);
            }
        };
        fetchSettings();
    }, [userId]);

    const saveSettings = async (next: SchedulingSettingsState) => {
        setSettings(next);
        setIsSubmitting(true);
        setSuccessMessage(null);

        try {
            const token = await auth.currentUser?.getIdToken();
            const res = await fetchWithRetry(`${API_BASE_URL}/api/users/scheduling-settings`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ user_id: userId, ...next }),
                timeoutMs: 8000,
            });

            if (res.ok) {
                setSuccessMessage("Scheduling settings saved.");
                setTimeout(() => setSuccessMessage(null), 3000);
            } else {
                console.error("Failed to update scheduling settings");
            }
        } catch (error) {
            console.error("Network error saving scheduling settings:", error);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleWindowChange = (days: number) => {
        saveSettings({ ...settings, optimisation_window_days: days });
    };

    const handleToggle = (field: keyof Omit<SchedulingSettingsState, "optimisation_window_days">, value: boolean) => {
        saveSettings({ ...settings, [field]: value });
    };

    const handleStartHourChange = (hour: number) => {
        const clampedEnd = Math.max(settings.scheduling_end_hour, hour + 1);
        saveSettings({ ...settings, scheduling_start_hour: hour, scheduling_end_hour: clampedEnd });
    };

    const handleEndHourChange = (hour: number) => {
        const clampedStart = Math.min(settings.scheduling_start_hour, hour - 1);
        saveSettings({ ...settings, scheduling_end_hour: hour, scheduling_start_hour: clampedStart });
    };

    const cardStyle: React.CSSProperties = {
        background: "var(--color-bg-glass-strong)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid var(--color-border)",
        boxShadow: "var(--shadow-lg)",
    };

    const renderBooleanSection = (
        field: keyof Omit<SchedulingSettingsState, "optimisation_window_days">,
        label: string,
        enabledDescription: string,
        disabledDescription: string,
        Icon: React.ReactNode,
    ) => {
        const value = settings[field];
        return (
            <div className="rounded-2xl overflow-hidden transition-all duration-200" style={cardStyle}>
                {/* Enabled row */}
                <button
                    onClick={() => handleToggle(field, true)}
                    disabled={isSubmitting}
                    className="w-full flex items-center justify-between px-6 py-4 transition-all duration-200 active:opacity-70"
                    style={{
                        background: value ? "var(--color-surface-hover)" : "transparent",
                        borderBottom: "1px solid var(--color-border-subtle)",
                    }}
                >
                    <div className="flex items-center gap-4">
                        <div
                            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors duration-200"
                            style={{
                                background: value ? "var(--color-accent-glow)" : "var(--color-surface)",
                                border: "1px solid var(--color-border)",
                            }}
                        >
                            <span
                                style={{
                                    color: value ? "var(--color-accent-primary)" : "var(--color-text-tertiary)",
                                }}
                            >
                                {Icon}
                            </span>
                        </div>
                        <div className="text-left">
                            <p
                                className="text-[15px] font-semibold transition-colors duration-200"
                                style={{ color: "var(--color-text-primary)" }}
                            >
                                Enabled
                            </p>
                            <p
                                className="text-[12px] mt-0.5 transition-colors duration-200"
                                style={{ color: "var(--color-text-secondary)" }}
                            >
                                {enabledDescription}
                            </p>
                        </div>
                    </div>
                    {value && <CheckIcon />}
                </button>

                {/* Disabled row */}
                <button
                    onClick={() => handleToggle(field, false)}
                    disabled={isSubmitting}
                    className="w-full flex items-center justify-between px-6 py-4 transition-all duration-200 active:opacity-70"
                    style={{
                        background: value ? "transparent" : "var(--color-surface-hover)",
                    }}
                >
                    <div className="flex items-center gap-4">
                        <div
                            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors duration-200"
                            style={{
                                background: value ? "var(--color-surface)" : "var(--color-accent-glow)",
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
                                    color: value ? "var(--color-text-tertiary)" : "var(--color-accent-primary)",
                                }}
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                                />
                            </svg>
                        </div>
                        <div className="text-left">
                            <p
                                className="text-[15px] font-semibold transition-colors duration-200"
                                style={{ color: "var(--color-text-primary)" }}
                            >
                                Disabled
                            </p>
                            <p
                                className="text-[12px] mt-0.5 transition-colors duration-200"
                                style={{ color: "var(--color-text-secondary)" }}
                            >
                                {disabledDescription}
                            </p>
                        </div>
                    </div>
                    {!value && <CheckIcon />}
                </button>
            </div>
        );
    };

    return (
        <div className="min-h-screen font-sans flex flex-col pb-32 bg-transparent transition-colors duration-500">
            {/* Sticky header */}
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
                    Scheduling
                </span>

                <div className="w-16" />
            </div>

            <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-10 animate-fadeIn">
                {/* Page title */}
                <div className="space-y-2 text-center md:text-left">
                    <h2
                        className="text-3xl font-extrabold tracking-tight transition-colors duration-200"
                        style={{ color: "var(--color-text-primary)" }}
                    >
                        Scheduling
                    </h2>
                    <p
                        className="text-sm max-w-xl transition-colors duration-200"
                        style={{ color: "var(--color-text-secondary)" }}
                    >
                        Control the optimiser window and which days are included in scheduling.
                    </p>
                </div>

                {isLoading ? (
                    <div className="flex justify-center py-10">
                        <SpinnerIcon />
                    </div>
                ) : (
                    <>
                        {/* ── Section: Optimisation Window ── */}
                        <section className="space-y-4">
                            <h3
                                className="text-xs font-bold uppercase tracking-widest px-1 transition-colors duration-200"
                                style={{ color: "var(--color-text-tertiary)" }}
                            >
                                Optimisation Window
                            </h3>

                            <div
                                className="rounded-2xl p-5 transition-all duration-200"
                                style={cardStyle}
                            >
                                <p
                                    className="text-[13px] mb-4 transition-colors duration-200"
                                    style={{ color: "var(--color-text-secondary)" }}
                                >
                                    How many days forward the optimiser looks when rescheduling
                                    your calendar.
                                </p>
                                <div className="flex gap-3 flex-wrap">
                                    {WINDOW_OPTIONS.map((days) => {
                                        const isSelected = settings.optimisation_window_days === days;
                                        return (
                                            <button
                                                key={days}
                                                onClick={() => handleWindowChange(days)}
                                                disabled={isSubmitting}
                                                className="px-5 py-2 rounded-full text-[14px] font-semibold transition-all duration-200 active:scale-95 disabled:opacity-50"
                                                style={{
                                                    background: isSelected
                                                        ? "var(--color-accent-primary)"
                                                        : "var(--color-surface)",
                                                    color: isSelected
                                                        ? "#fff"
                                                        : "var(--color-text-secondary)",
                                                    border: `1.5px solid ${isSelected ? "var(--color-accent-primary)" : "var(--color-border)"}`,
                                                    boxShadow: isSelected ? "0 2px 12px var(--color-accent-glow)" : "none",
                                                }}
                                            >
                                                {days}d
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        </section>

                        {/* ── Section: Scheduling Hours ── */}
                        <section className="space-y-4">
                            <h3
                                className="text-xs font-bold uppercase tracking-widest px-1 transition-colors duration-200"
                                style={{ color: "var(--color-text-tertiary)" }}
                            >
                                Scheduling Hours
                            </h3>

                            <div
                                className="rounded-2xl p-5 space-y-5 transition-all duration-200"
                                style={cardStyle}
                            >
                                <p
                                    className="text-[13px] transition-colors duration-200"
                                    style={{ color: "var(--color-text-secondary)" }}
                                >
                                    The daily window in which events, tasks, and routines can be placed. Times are in your local timezone.
                                </p>

                                {/* Start Hour */}
                                <div className="space-y-2">
                                    <p className="text-[13px] font-semibold transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>
                                        Start Time
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {[4, 5, 6, 7, 8, 9, 10, 11, 12].map((h) => {
                                            const isSelected = settings.scheduling_start_hour === h;
                                            const isDisabled = h >= settings.scheduling_end_hour;
                                            const label = formatHour(h);
                                            return (
                                                <button
                                                    key={h}
                                                    onClick={() => !isDisabled && handleStartHourChange(h)}
                                                    disabled={isSubmitting || isDisabled}
                                                    className="px-3.5 py-1.5 rounded-full text-[13px] font-semibold transition-all duration-200 active:scale-95 disabled:opacity-30"
                                                    style={{
                                                        background: isSelected ? "var(--color-accent-primary)" : "var(--color-surface)",
                                                        color: isSelected ? "#fff" : "var(--color-text-secondary)",
                                                        border: `1.5px solid ${isSelected ? "var(--color-accent-primary)" : "var(--color-border)"}`,
                                                        boxShadow: isSelected ? "0 2px 12px var(--color-accent-glow)" : "none",
                                                    }}
                                                >
                                                    {label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* End Hour */}
                                <div className="space-y-2">
                                    <p className="text-[13px] font-semibold transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>
                                        End Time
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {[17, 18, 19, 20, 21, 22, 23, 24].map((h) => {
                                            const isSelected = settings.scheduling_end_hour === h;
                                            const isDisabled = h <= settings.scheduling_start_hour;
                                            const label = formatHour(h);
                                            return (
                                                <button
                                                    key={h}
                                                    onClick={() => !isDisabled && handleEndHourChange(h)}
                                                    disabled={isSubmitting || isDisabled}
                                                    className="px-3.5 py-1.5 rounded-full text-[13px] font-semibold transition-all duration-200 active:scale-95 disabled:opacity-30"
                                                    style={{
                                                        background: isSelected ? "var(--color-accent-primary)" : "var(--color-surface)",
                                                        color: isSelected ? "#fff" : "var(--color-text-secondary)",
                                                        border: `1.5px solid ${isSelected ? "var(--color-accent-primary)" : "var(--color-border)"}`,
                                                        boxShadow: isSelected ? "0 2px 12px var(--color-accent-glow)" : "none",
                                                    }}
                                                >
                                                    {label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>
                        </section>

                        {/* ── Section: Day Selection ── */}
                        <section className="space-y-4">
                            <h3
                                className="text-xs font-bold uppercase tracking-widest px-1 transition-colors duration-200"
                                style={{ color: "var(--color-text-tertiary)" }}
                            >
                                Day Selection
                            </h3>

                            {/* Optimise Weekends */}
                            <div className="space-y-1">
                                <p
                                    className="text-[13px] font-medium px-1 mb-2 transition-colors duration-200"
                                    style={{ color: "var(--color-text-secondary)" }}
                                >
                                    Optimise Weekends
                                </p>
                                {renderBooleanSection(
                                    "optimise_weekends",
                                    "Optimise Weekends",
                                    "The optimiser may move events to Saturday & Sunday",
                                    "Weekends are excluded from calendar optimisation",
                                    <svg
                                        className="w-5 h-5"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={1.5}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z"
                                        />
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                                        />
                                    </svg>,
                                )}
                            </div>

                            {/* Schedule Tasks & Debt on Weekends */}
                            <div className="space-y-1">
                                <p
                                    className="text-[13px] font-medium px-1 mb-2 transition-colors duration-200"
                                    style={{ color: "var(--color-text-secondary)" }}
                                >
                                    Schedule Tasks &amp; Debt on Weekends
                                </p>
                                {renderBooleanSection(
                                    "schedule_on_weekends",
                                    "Schedule Tasks & Debt on Weekends",
                                    "Task blocks and debt slots may land on Saturday & Sunday",
                                    "Task and debt blocks are kept to weekdays only",
                                    <svg
                                        className="w-5 h-5"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={1.5}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5m-9-6h.008v.008H12v-.008zM12 15h.008v.008H12V15zm0 2.25h.008v.008H12v-.008zM9.75 15h.008v.008H9.75V15zm0 2.25h.008v.008H9.75v-.008zM7.5 15h.008v.008H7.5V15zm0 2.25h.008v.008H7.5v-.008zm6.75-4.5h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008V15zm0 2.25h.008v.008h-.008v-.008zm2.25-4.5h.008v.008H16.5v-.008zm0 2.25h.008v.008H16.5V15z"
                                        />
                                    </svg>,
                                )}
                            </div>

                            {/* Include Weekends in Routines */}
                            <div className="space-y-1">
                                <p
                                    className="text-[13px] font-medium px-1 mb-2 transition-colors duration-200"
                                    style={{ color: "var(--color-text-secondary)" }}
                                >
                                    Include Weekends in Routines
                                </p>
                                {renderBooleanSection(
                                    "routines_on_weekends",
                                    "Include Weekends in Routines",
                                    "Routine ghost events are injected on Saturday & Sunday",
                                    "Routine ghost events appear on weekdays only",
                                    <svg
                                        className="w-5 h-5"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={1.5}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
                                        />
                                    </svg>,
                                )}
                            </div>
                        </section>

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
                                        <SpinnerIcon className="w-4 h-4 animate-spin flex-shrink-0" />
                                        Saving…
                                    </>
                                ) : (
                                    <>
                                        <CheckIcon color="var(--color-success)" />
                                        {successMessage}
                                    </>
                                )}
                            </div>
                        )}

                        {/* Info note */}
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
                                Changes take effect on the <strong>next optimiser run</strong>.
                                Existing scheduled blocks are not moved retroactively.
                            </p>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
