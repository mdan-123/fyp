"use client";

import React from "react";
import { CalendarEvent } from "@/types";

interface ConflictResolutionModalProps {
  isOpen: boolean;
  conflictType: "sync" | "overlap";
  event: CalendarEvent | null;
  overlappingEvents?: CalendarEvent[];
  conflictCount: number;
  currentIndex: number;
  onAcceptExternal: (eventId: string) => void;
  onKeepProposed: (eventId: string) => void;
  onRevertToOriginal: (eventId: string) => void;
  onManualEdit: (event: CalendarEvent) => void;
  onDeleteEvent?: (eventId: string) => void;
  onDismiss: () => void;
}

export default function ConflictResolutionModal({
  isOpen,
  conflictType,
  event,
  overlappingEvents = [],
  conflictCount,
  currentIndex,
  onAcceptExternal,
  onKeepProposed,
  onRevertToOriginal,
  onManualEdit,
  onDeleteEvent,
  onDismiss,
}: ConflictResolutionModalProps) {
  if (!isOpen || !event) return null;

  // --- THE FIX: Robust Local Time Formatting ---
  const formatTime = (isoString: string | null) => {
    if (!isoString) return "Not set";
    // Passing the raw ISO string directly to Date automatically assumes 
    // the 'Z' means UTC and converts to local browser time for display.
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return "Invalid Time";
    return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  };

  const formatDate = (isoString: string | null) => {
    if (!isoString) return "Not set";
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return "Invalid Date";
    return date.toLocaleDateString("en-GB", { weekday: "short", month: "short", day: "numeric" });
  };

  const isSync = conflictType === "sync";

  return (
    <div 
      className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-0 sm:p-4 font-sans animate-fadeIn"
      style={{
        background: 'rgba(15, 23, 42, 0.4)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
      }}
    >
      <div 
        className="w-full max-w-lg rounded-t-3xl sm:rounded-2xl flex flex-col overflow-hidden animate-fadeInUp"
        style={{
          background: 'rgba(255, 255, 255, 0.95)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(148, 163, 184, 0.1)',
        }}
      >
        
        {/* Header */}
        <div 
          className="px-6 py-5 flex items-start justify-between"
          style={{
            background: isSync ? 'rgba(255, 251, 235, 0.5)' : 'rgba(254, 242, 242, 0.5)',
            borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
          }}
        >
          <div className="flex gap-3 items-center">
            <div 
              className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
              style={isSync ? {
                background: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)',
                color: 'white',
                boxShadow: '0 4px 12px -2px rgba(245, 158, 11, 0.4)',
              } : {
                background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                color: 'white',
                boxShadow: '0 4px 12px -2px rgba(239, 68, 68, 0.4)',
              }}
            >
              {isSync ? (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              )}
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-800 leading-tight">
                {isSync ? "Resolve Conflict" : "Double Booking Detected"}
              </h2>
              <p className="text-sm font-medium mt-0.5" style={{ color: isSync ? '#d97706' : '#dc2626' }}>
                {conflictCount > 1 ? `Conflict ${currentIndex + 1} of ${conflictCount}` : "Decision Required"}
              </p>
            </div>
          </div>
          <button onClick={onDismiss} className="text-slate-400 hover:text-slate-600 transition-colors p-1">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* BODY: OVERLAP VIEW */}
        {!isSync && (
          <div 
            className="p-6 space-y-4 overflow-y-auto max-h-[60vh]"
            style={{ background: 'rgba(248, 250, 252, 0.5)' }}
          >
            <p className="text-sm text-slate-600 mb-2">These events are competing for the same time slot.</p>
            {[event, ...overlappingEvents].map((ev, idx) => (
              <div 
                key={ev.id} 
                className="p-4 rounded-xl relative overflow-hidden flex flex-col gap-3"
                style={{
                  background: 'rgba(255, 255, 255, 0.9)',
                  border: '1px solid rgba(148, 163, 184, 0.2)',
                  boxShadow: '0 4px 12px -4px rgba(0, 0, 0, 0.05)',
                }}
              >
                <div 
                  className="absolute top-0 left-0 w-1 h-full"
                  style={{ background: 'linear-gradient(180deg, #ef4444 0%, #dc2626 100%)' }}
                />
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Event {idx + 1}</p>
                  <h3 className="text-base font-bold text-slate-800">{ev.title}</h3>
                  <p className="text-sm font-medium text-slate-500 mt-1">{formatTime(ev.start)} — {formatTime(ev.end)}</p>
                </div>
                <div className="flex gap-2">
                  <button 
                    onClick={() => onManualEdit(ev)} 
                    className="flex-1 py-2 font-bold text-xs rounded-lg transition-all"
                    style={{
                      background: 'rgba(238, 242, 255, 0.8)',
                      color: '#6366f1',
                    }}
                  >
                    Edit Time
                  </button>
                  {onDeleteEvent && (
                    <button 
                      onClick={() => { onDeleteEvent(ev.id); onDismiss(); }} 
                      className="flex-1 py-2 font-bold text-xs rounded-lg transition-all"
                      style={{
                        background: 'rgba(254, 242, 242, 0.8)',
                        color: '#ef4444',
                      }}
                    >
                      Delete Event
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* BODY: SYNC DRIFT VIEW (Your Original Code) */}
        {isSync && (
          <>
            <div className="p-6 space-y-6 overflow-y-auto max-h-[60vh]">
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Event Name</p>
                <h3 className="text-xl font-semibold text-slate-800">{event.title}</h3>
              </div>

              <div className="flex flex-col gap-3">
                {/* 1. External Calendar Time (The Drift) */}
                <div 
                  className="p-4 rounded-xl relative overflow-hidden"
                  style={{
                    background: 'rgba(239, 246, 255, 0.6)',
                    border: '1px solid rgba(59, 130, 246, 0.2)',
                  }}
                >
                  <div 
                    className="absolute top-0 left-0 w-1 h-full"
                    style={{ background: 'linear-gradient(180deg, #3b82f6 0%, #2563eb 100%)' }}
                  />
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-bold uppercase tracking-widest flex items-center gap-1.5" style={{ color: '#2563eb' }}>
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
                      </svg>
                      New {event.provider.toUpperCase()} Time
                    </span>
                  </div>
                  <p className="text-slate-800 font-semibold">{formatDate(event.original_start)}</p>
                  <p className="text-slate-600 text-sm">{formatTime(event.original_start)} — {formatTime(event.original_end)}</p>
                </div>

                {/* 2. Previous Original Time (Baseline) */}
                {event.previous_start && (
                  <div 
                    className="p-4 rounded-xl relative overflow-hidden opacity-80"
                    style={{
                      background: 'rgba(248, 250, 252, 0.8)',
                      border: '1px solid rgba(148, 163, 184, 0.2)',
                    }}
                  >
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Previous Baseline
                      </span>
                    </div>
                    <p className="text-slate-700 font-medium">{formatDate(event.previous_start)}</p>
                    <p className="text-slate-500 text-sm">{formatTime(event.previous_start)} — {formatTime(event.previous_end || null)}</p>
                  </div>
                )}

                {/* 3. AI Proposed Time */}
                {event.proposed_start && (
                  <div 
                    className="p-4 rounded-xl relative overflow-hidden"
                    style={{
                      background: 'rgba(238, 242, 255, 0.6)',
                      border: '1px solid rgba(99, 102, 241, 0.2)',
                    }}
                  >
                    <div 
                      className="absolute top-0 left-0 w-1 h-full"
                      style={{ background: 'linear-gradient(180deg, #6366f1 0%, #8b5cf6 100%)' }}
                    />
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs font-bold uppercase tracking-widest flex items-center gap-1.5" style={{ color: '#6366f1' }}>
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                        </svg>
                        Current AI Plan
                      </span>
                    </div>
                    <p className="text-slate-800 font-semibold">{formatDate(event.proposed_start)}</p>
                    <p className="text-slate-600 text-sm">{formatTime(event.proposed_start)} — {formatTime(event.proposed_end)}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Actions Footer */}
            <div className="p-6 pt-0 space-y-2.5">
              <button 
                onClick={() => onAcceptExternal(event.id)}
                className="w-full flex items-center justify-between px-5 py-3 text-white font-semibold rounded-xl transition-all"
                style={{
                  background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                  boxShadow: '0 4px 20px -4px rgba(99, 102, 241, 0.5)',
                }}
              >
                <div className="flex flex-col text-left">
                  <span className="text-sm">Accept New External Time</span>
                  <span className="text-[10px] font-medium" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Syncs your database with the calendar update.</span>
                </div>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
              </button>

              {event.proposed_start && (
                <button 
                  onClick={() => onKeepProposed(event.id)}
                  className="w-full flex items-center justify-between px-5 py-3 text-slate-800 font-semibold rounded-xl transition-all"
                  style={{
                    background: 'rgba(255, 255, 255, 0.9)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                  }}
                >
                  <div className="flex flex-col text-left">
                    <span className="text-sm">Keep AI Plan</span>
                    <span className="text-[10px] font-medium text-slate-500">Requires pushing a change back to your calendar.</span>
                  </div>
                  <svg className="w-5 h-5" style={{ color: '#6366f1' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" /></svg>
                </button>
              )}

              {event.previous_start && (
                <button 
                  onClick={() => onRevertToOriginal(event.id)}
                  className="w-full flex items-center justify-between px-5 py-3 text-slate-800 font-semibold rounded-xl transition-all"
                  style={{
                    background: 'rgba(255, 255, 255, 0.9)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                  }}
                >
                  <div className="flex flex-col text-left">
                    <span className="text-sm">Restore Previous Baseline</span>
                    <span className="text-[10px] font-medium text-slate-500">Ignores the external update and reverts to old time.</span>
                  </div>
                  <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" /></svg>
                </button>
              )}

              <div className="flex gap-2 pt-1">
                <button 
                  onClick={() => onManualEdit(event)}
                  className="flex-1 py-2.5 font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-2"
                  style={{
                    background: 'rgba(248, 250, 252, 0.8)',
                    color: '#64748b',
                  }}
                >
                  Manual Edit
                </button>
                <button 
                  onClick={onDismiss}
                  className="flex-1 py-2.5 font-bold text-xs rounded-lg transition-all flex items-center justify-center gap-2"
                  style={{
                    background: 'rgba(248, 250, 252, 0.8)',
                    color: '#64748b',
                  }}
                >
                  Decide Later
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}