"use client";

import { useState, useEffect, useMemo } from "react";
import { collection, doc, getDoc, getDocs } from "firebase/firestore";
import { db } from "../lib/firebase";
import { useAuth } from "@/lib/AuthContext"; 
import CustomCalendar from "@/components/CustomCalendar";
import EventModal from "@/components/EventModal";
import NavigationBar from "@/components/NavigationBar";
import ConflictResolutionModal from "@/components/ConflictResolutionModal";
import OptimisationPrepModal from "@/components/OptimisationPrepModal";
import { LinkedAccount, CalendarEvent } from "../types";
import { fetchWithRetry } from "@/lib/fetchUtils";
import { App as CapacitorApp } from '@capacitor/app'; 
import { Capacitor } from '@capacitor/core';

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

type ConflictQueueItem = {
  type: "sync" | "overlap";
  event: CalendarEvent;
  overlaps?: CalendarEvent[];
};

export default function Dashboard() {
  const { user: authUser, loading: authLoading } = useAuth();
    
    const user = authUser ? { uid: authUser.uid, email: authUser.email || "" } : null;

    const [linkedAccounts, setLinkedAccounts] = useState<LinkedAccount[]>([]);
    const [preferences, setPreferences] = useState<string[]>([]);
    const [events, setEvents] = useState<CalendarEvent[]>([]);
    
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [isSyncing, setIsSyncing] = useState<boolean>(false);
    const [isOptimising, setIsOptimising] = useState<boolean>(false);
    const [errorOptimising, setErrorOptimising] = useState<boolean>(false);

    const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
    const [isAiModalOpen, setIsAiModalOpen] = useState<boolean>(false);
    const [isOptimisePrepModalOpen, setIsOptimisePrepModalOpen] = useState<boolean>(false);

    const [selectedEditEvent, setSelectedEditEvent] = useState<CalendarEvent | null>(null);
    const [selectedInstanceDate, setSelectedInstanceDate] = useState<Date | undefined>(undefined);

    const [conflictQueue, setConflictQueue] = useState<ConflictQueueItem[]>([]);
    const [currentConflictIndex, setCurrentConflictIndex] = useState(0);

    const [previewEvents, setPreviewEvents] = useState<CalendarEvent[]>([]);
    const [isPreviewMode, setIsPreviewMode] = useState<boolean>(false);
    const [previewToggle, setPreviewToggle] = useState<"original" | "optimised">("optimised");
    const [optimiseTargetDate, setOptimiseTargetDate] = useState<Date>(new Date());

    // Auto-detect Sync Drifts on load
    useEffect(() => {
      const drifts = events.filter((e) => e.requires_review || e.has_drifted);
      if (drifts.length > 0) {
        const formattedDrifts = drifts.map(e => ({ type: "sync" as const, event: e }));
        setConflictQueue(formattedDrifts);
        setCurrentConflictIndex(0);
      }
    }, [events]);

    // --- SILENT BACKGROUND SWEEPER ---
    const runBackgroundSweep = async (uid: string) => {
      try {
        fetchWithRetry(`${API_BASE_URL}/api/analytics/sweep/${uid}`, {
          method: "POST",
          timeoutMs: 5000 
        }).catch(e => console.error("Silent sweeper failed:", e));
      } catch (e) {
        console.error("Background sweeper failed:", e);
      }
    };

    // 1. Initial Load Hook & Page Reload Sweeper
    useEffect(() => {
      if (!authLoading) {
        if (authUser) {
          runBackgroundSweep(authUser.uid);
          fetchUserData(authUser.uid);
        } else {
          setIsLoading(false);
        }
      }
    }, [authUser, authLoading]);

    // 2. Mobile App Wake-Up Hook
    useEffect(() => {
      if (!Capacitor.isNativePlatform() || !user?.uid) return;

      const appStateListener = CapacitorApp.addListener('appStateChange', async ({ isActive }) => {
        if (isActive) {
          console.log("App woke up! Running sweeper and fetching fresh calendar data...");
          runBackgroundSweep(user.uid);
          fetchUserData(user.uid); 
        }
      });

      return () => {
        appStateListener.then(listener => listener.remove());
      };
    }, [user?.uid]);

    const fetchUserData = async (uid: string) => {
      setIsLoading(true);
      try {
        const userRef = doc(db, "users", uid);
        const userSnap = await getDoc(userRef);
        if (userSnap.exists()) {
          const userData = userSnap.data();
          setLinkedAccounts(userData.linked_accounts || []);
          setPreferences(userData.preferences || []);
        }
        await fetchEvents(uid);
      } catch (error) {
        console.error("Failed to load user data:", error);
      } finally {
        setIsLoading(false);
      }
    };

  const fetchEvents = async (uidOverride?: string) => {
    const targetUid = uidOverride || user?.uid;
    if (!targetUid) return;

    try {
      const eventsRef = collection(db, "users", targetUid, "raw_events");
      const eventsSnap = await getDocs(eventsRef);

      const loadedEvents: CalendarEvent[] = [];
      eventsSnap.forEach((docSnap) => {
        const data = docSnap.data();
        loadedEvents.push({
          id: docSnap.id,
          title: data.title || "Untitled",

          start: data.start,
          end: data.end,
          original_start: data.original_start || data.start || "",
          original_end: data.original_end || data.end || "",
          previous_start: data.previous_start ?? null,
          previous_end: data.previous_end ?? null,
          proposed_start: data.proposed_start ?? null,
          proposed_end: data.proposed_end ?? null,

          provider: data.provider || "custom",
          has_drifted: data.has_drifted || false,
          requires_review: data.requires_review || false,
          status: data.status || "synced",
          category: data.category || null,

          is_locked: data.is_locked ?? true,

          travel_time: data.travel_time || 0,
          travel_origin: data.travel_origin || null,
          travel_mode: data.travel_mode || "driving",

          recurrence: data.recurrence || "none",
          recurrence_days: data.recurrence_days || [],
          exception_dates: data.exception_dates || [],
          parent_event_id: data.parent_event_id || null,

          meeting_link: data.meeting_link || null,
          location: data.location || null,
          description: data.description || null,
          email: data.email || "",
          attachments: data.attachments || [],

          // --- TELEMETRY MAPPING ---
          completion_status: data.completion_status || "pending",
          snooze_count: data.snooze_count || 0,
          completed_at: data.completed_at || null,
          debt_applied: data.debt_applied || false,
          is_perishable: data.is_perishable || false,
          
        } as CalendarEvent);
      });

      setEvents(loadedEvents);
    } catch (error) {
      console.error("Failed to fetch events:", error);
    }
  };

  const handleSync = async () => {
    if (!user) return;
    setIsSyncing(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/calendar/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.uid }),
      });

      if (res.ok) {
        await fetchEvents();
      } else {
        console.error("Sync returned an error status:", res.status);
      }
    } catch (error) {
      console.error("Sync failed:", error);
    } finally {
      setIsSyncing(false);
    }
  };

  const deleteEvent = async (eventId: string) => {
    if (!user) return;
    try {
      await fetch(`${API_BASE_URL}/api/calendar/delete-event`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.uid, event_id: eventId }),
      });
      await fetchEvents();
    } catch (error) {
      console.error("Failed to delete event:", error);
    }
  };

  const resolveConflict = async (
    eventId: string,
    resolutionType: "external" | "proposed" | "revert"
  ) => {
    setEvents((prevEvents) =>
      prevEvents.map((e) => {
        if (e.id === eventId) {
          const updatedEvent = {
            ...e,
            has_drifted: false,
            requires_review: false,
          };

          if (resolutionType === "external") {
            updatedEvent.proposed_start = null;
            updatedEvent.proposed_end = null;
          } else if (resolutionType === "revert") {
            updatedEvent.proposed_start = e.previous_start || null;
            updatedEvent.proposed_end = e.previous_end || null;
          }

          return updatedEvent;
        }
        return e;
      })
    );

    if (currentConflictIndex < conflictQueue.length - 1) {
      setCurrentConflictIndex((prev) => prev + 1);
    } else {
      setConflictQueue([]);
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/calendar/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: user?.uid,
          event_id: eventId,
          resolution: resolutionType,
        }),
      });

      if (!res.ok) {
        console.error("Failed to resolve on backend, reverting UI");
        await fetchEvents();
      }
    } catch (err) {
      console.error("Network error during resolution", err);
      await fetchEvents();
    }
  };

  const executeOptimisationPreview = async (targetDate: Date) => {
    if (!user) return;
    setIsOptimising(true);
    try {
      const dateStr = targetDate.toISOString().split("T")[0];
      const res = await fetch(`${API_BASE_URL}/api/calendar/optimise/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.uid, target_date: dateStr }),
      });

      if (res.ok) {
        const data = await res.json();
        setPreviewEvents(data.preview_events);
        setIsPreviewMode(true);
        setPreviewToggle("optimised");
      }
    } catch (error) {
      console.error("Optimisation preview failed:", error);
    } finally {
      setIsOptimising(false);
    }
  };

  const handleOptimiseClick = (date: Date) => {
    setOptimiseTargetDate(date);
    if (preferences.length >= 3) {
      executeOptimisationPreview(date);
    } else {
      setIsOptimisePrepModalOpen(true);
    }
  };

  const handleContinueOptimisation = async (useGenerics?: boolean) => {
    setIsOptimisePrepModalOpen(false);
    if (!user) return;

    if (useGenerics) {
      setIsOptimising(true);
      const genericRules = [
        "Protect 1 hour for lunch daily",
        "Keep a 15-min buffer between meetings",
        "Schedule Deep Work in the mornings",
      ];
      
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

      try {
        await Promise.all(
          genericRules.map((rule) =>
            fetch(`${API_BASE_URL}/api/preferences/parse`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ 
                user_id: user.uid, 
                raw_text: rule,
                timezone: tz
              }),
            })
          )
        );

        await fetchUserData(user.uid);
        await executeOptimisationPreview(optimiseTargetDate);
      } catch (error) {
        console.error("Failed to parse generic preferences:", error);
        setIsOptimising(false);
      }
    } else {
      await executeOptimisationPreview(optimiseTargetDate);
    }
  };

  const acceptOptimisation = async () => {
    setIsOptimising(true);
    setErrorOptimising(false);
    try {
      const res = await fetch(`${API_BASE_URL}/api/calendar/optimise/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: user?.uid,
          events: previewEvents,
        }),
      });

      if (res.ok) {
        setIsPreviewMode(false);
        setPreviewEvents([]);
        await fetchEvents(); 
      } else {
        console.error("Commit returned an error status:", res.status);
        setErrorOptimising(true); 
      }
    } catch (error) {
      console.error("Commit failed:", error);
      setErrorOptimising(true); 
    } finally {
      setIsOptimising(false);
    }
  };

  const discardOptimisation = () => {
    setPreviewEvents([]);
    setIsPreviewMode(false);
  };

  if (authLoading || isLoading) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center font-sans transition-colors duration-500" style={{ background: "var(--color-bg-base)" }}>
        <div className="relative">
          {/* Animated gradient orb managed by global CSS variables */}
          <div className="absolute -inset-8 rounded-full blur-2xl animate-pulse opacity-50" style={{ background: "var(--color-accent-glow)" }} />
          <div 
            className="relative w-16 h-16 rounded-2xl flex items-center justify-center shadow-xl transition-colors duration-500"
            style={{ background: "var(--color-accent-gradient)", boxShadow: "var(--shadow-glow)" }}
          >
            <svg className="w-8 h-8 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} style={{ color: "var(--color-bg-base)" }}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
            </svg>
          </div>
        </div>
        <p className="mt-6 text-sm font-medium tracking-wide transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>Loading your schedule...</p>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden relative transition-colors duration-500 bg-transparent">
      {/* Decorative Orbs handled entirely by body::before in global.css */}

      {errorOptimising && (
        <div 
          className="fixed top-0 left-0 w-full z-[100] animate-fade-in-down"
          style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}
        >
          <div className="mx-4 mt-4 p-4 rounded-2xl flex items-start gap-3 shadow-lg transition-colors duration-500"
            style={{
              background: 'var(--color-bg-glass-strong)',
              backdropFilter: 'blur(12px)',
              border: '1px solid var(--color-danger)',
            }}
          >
            <div 
              className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-colors duration-500"
              style={{ background: 'var(--color-danger-bg)' }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--color-danger)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold transition-colors duration-200" style={{ color: 'var(--color-danger)' }}>Optimisation Failed</p>
              <p className="text-xs mt-0.5 transition-colors duration-200" style={{ color: 'var(--color-danger)' }}>Changes couldn't be saved. You can retry or discard.</p>
            </div>
            <button 
              onClick={() => setErrorOptimising(false)} 
              className="p-1.5 rounded-lg transition-colors duration-200"
              style={{ color: 'var(--color-danger)' }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {isPreviewMode && (
        <div 
          className="absolute top-4 left-1/2 -translate-x-1/2 z-[60] animate-fade-in-down"
          style={{ top: 'calc(env(safe-area-inset-top, 16px) + 16px)' }}
        >
          <div 
            className="p-1 flex items-center gap-1 rounded-xl transition-colors duration-500"
            style={{
              background: 'var(--color-bg-glass)',
              backdropFilter: 'blur(20px)',
              border: '1px solid var(--color-border)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <button
              onClick={() => setPreviewToggle("original")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200`}
              style={previewToggle === "original" ? { background: "var(--color-surface)", color: "var(--color-text-primary)", boxShadow: "var(--shadow-sm)" } : { color: "var(--color-text-secondary)" }}
            >
              Original
            </button>
            <button
              onClick={() => setPreviewToggle("optimised")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200`}
              style={previewToggle === "optimised" ? { background: "var(--color-accent-glow)", color: "var(--color-accent-primary)", boxShadow: "var(--shadow-sm)" } : { color: "var(--color-text-secondary)" }}
            >
              Optimised
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-hidden relative">
        <CustomCalendar
          events={
            isPreviewMode && previewToggle === "optimised"
              ? previewEvents
              : events
          }
          onEventClick={(event: CalendarEvent, date?: Date, overlaps?: CalendarEvent[]) => {
            // NEW INTERCEPTOR: Handle Overlaps first, then Drifts, then Normal Edit
            if (overlaps && overlaps.length > 0) {
              setConflictQueue([{ type: "overlap", event, overlaps }]);
              setCurrentConflictIndex(0);
            } else if (event.requires_review || event.has_drifted) {
              setConflictQueue([{ type: "sync", event }]);
              setCurrentConflictIndex(0);
            } else {
              setSelectedEditEvent(event);
              setSelectedInstanceDate(date);
              setIsModalOpen(true);
            }
          }}
          onSync={handleSync}
          isSyncing={isSyncing || isOptimising}
          onOptimise={handleOptimiseClick}
          isPreviewMode={isPreviewMode}
        />
      </div>
      {/* --- FLOATING ACTION BUTTON (ADD EVENT) --- */}
      {!isPreviewMode && (
        <button
          onClick={() => {
            setSelectedEditEvent(null);
            setSelectedInstanceDate(undefined);
            setIsModalOpen(true);
          }}
          className="fixed bottom-28 right-6 w-14 h-14 rounded-full flex items-center justify-center active:scale-95 transition-all duration-300 z-40 btn-primary"
          style={{ padding: 0 }}
        >
          <svg 
            className="w-7 h-7" 
            style={{ color: 'var(--color-bg-base)' }} 
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor" 
            strokeWidth={2.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </button>
      )}

      {isPreviewMode ? (
        <div 
          className="fixed bottom-0 left-0 w-full z-[60] animate-slide-in-bottom"
          style={{ paddingBottom: 'env(safe-area-inset-bottom, 16px)' }}
        >
          <div 
            className="mx-4 mb-4 p-4 sm:p-5 rounded-2xl transition-colors duration-500"
            style={{
              background: 'var(--color-bg-glass-strong)',
              backdropFilter: 'blur(20px)',
              border: '1px solid var(--color-border)',
              boxShadow: 'var(--shadow-lg), var(--shadow-inner-glow)',
            }}
          >
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="text-center sm:text-left">
                <h3 className="text-base font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
                  Review Optimisation
                </h3>
                <p className="text-sm mt-0.5 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                  Compare original and optimised schedules above.
                </p>
              </div>
              <div className="flex items-center justify-center gap-3 w-full sm:w-auto">
                <button
                  onClick={discardOptimisation}
                  className="flex-1 sm:flex-none px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 btn-secondary"
                >
                  Discard
                </button>
                <button
                  onClick={acceptOptimisation}
                  disabled={isOptimising}
                  className="flex-1 sm:flex-none px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 disabled:opacity-50 disabled:hover:scale-100 btn-primary"
                >
                  {isOptimising ? (
                    <span className="flex items-center gap-2">
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Applying...
                    </span>
                  ) : (
                    "Accept Changes"
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <NavigationBar />
      )}

      <EventModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedEditEvent(null);
          setSelectedInstanceDate(undefined);
        }}
        linkedAccounts={linkedAccounts}
        onSaveSuccess={() => fetchEvents()}
        userId={user?.uid || ""}
        editEvent={selectedEditEvent}
        instanceDate={selectedInstanceDate}
      />


      <OptimisationPrepModal
        isOpen={isOptimisePrepModalOpen}
        onClose={() => setIsOptimisePrepModalOpen(false)}
        preferencesCount={preferences.length}
        onContinue={handleContinueOptimisation}
      />

      <ConflictResolutionModal
        isOpen={
          conflictQueue.length > 0 && currentConflictIndex < conflictQueue.length
        }
        conflictType={conflictQueue[currentConflictIndex]?.type || "sync"}
        event={conflictQueue[currentConflictIndex]?.event || null}
        overlappingEvents={conflictQueue[currentConflictIndex]?.overlaps}
        conflictCount={conflictQueue.length}
        currentIndex={currentConflictIndex}
        onAcceptExternal={(id) => resolveConflict(id, "external")}
        onKeepProposed={(id) => resolveConflict(id, "proposed")}
        onRevertToOriginal={(id) => resolveConflict(id, "revert")}
        onManualEdit={(event) => {
          setConflictQueue([]);
          setSelectedEditEvent(event);
          setSelectedInstanceDate(undefined);
          setIsModalOpen(true);
        }}
        onDeleteEvent={deleteEvent}
        onDismiss={() => setConflictQueue([])}
      />
    </div>
  );
}