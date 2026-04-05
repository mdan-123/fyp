"use client";

import { useState } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";

interface CalendarSafetyProps {
  userId: string;
  onBack: () => void;
}

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function CalendarSafety({ userId, onBack }: CalendarSafetyProps) {
  const [isUndoing, setIsUndoing] = useState(false);
  const [undoMessage, setUndoMessage] = useState("");

  const handleUndo = async () => {
    setIsUndoing(true);
    setUndoMessage("");
    
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/calendar/snapshot/undo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
        timeoutMs: 15000
      });
      
      const data = await res.json();
      
      if (res.ok) {
        setUndoMessage("Success: Your calendar has been restored to its previous state.");
      } else {
        setUndoMessage(data.detail || "Failed to restore calendar.");
      }
    } catch (error) {
      setUndoMessage("Network error. Please try again.");
    } finally {
      setIsUndoing(false);
    }
  };

  return (
    <div className="h-full flex flex-col relative bg-transparent transition-colors duration-500">
      
      {/* Mobile Header with Back Button */}
      <div 
        className="md:hidden flex items-center gap-3 px-4 py-4 sticky top-0 z-10 transition-colors duration-200"
        style={{
          background: 'var(--color-bg-glass-strong)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <button 
          onClick={onBack}
          className="p-2 -ml-2 rounded-xl transition-all duration-200 active:scale-95"
          style={{ color: 'var(--color-accent-primary)' }}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h2 className="text-lg font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
          Safety & Rollback
        </h2>
      </div>

      {/* Desktop Header */}
      <div 
        className="hidden md:block px-8 py-10 transition-colors duration-200"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <h2 className="text-2xl font-bold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
          Calendar Safety & Rollback
        </h2>
        <p className="mt-2 text-sm max-w-2xl leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
          Whenever the AI optimises your schedule, we save a complete snapshot of how your calendar looked right before the changes were applied. If you change your mind, you can instantly revert everything back.
        </p>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 p-4 md:p-8 overflow-y-auto scrollbar-hide">
        <div className="max-w-3xl space-y-6">
          
          <div 
            className="p-5 md:p-6 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5 transition-all duration-200"
            style={{
              background: 'var(--color-bg-glass)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              border: '1px solid var(--color-border)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <div 
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors duration-200"
                  style={{
                    background: 'var(--color-danger-bg)',
                    border: '1px solid var(--color-border-subtle)',
                  }}
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--color-danger)' }}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
                  </svg>
                </div>
                <h3 className="text-base font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
                  Undo Latest Changes
                </h3>
              </div>
              <p className="text-sm pl-[52px] leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                This will revert your calendar to the exact state it was in before your last major AI optimisation.
              </p>
            </div>
            
            <button
              onClick={handleUndo}
              disabled={isUndoing}
              className="w-full sm:w-auto whitespace-nowrap px-5 py-3 text-sm font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none hover:scale-[1.02] active:scale-[0.98] sm:ml-4"
              style={{
                background: 'var(--color-danger-bg)',
                border: '1px solid var(--color-danger)',
                color: 'var(--color-danger)',
              }}
            >
              {isUndoing ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Reverting...
                </span>
              ) : (
                "Undo Last Change"
              )}
            </button>
          </div>
          
          {undoMessage && (
            <div 
              className={`p-4 rounded-xl text-sm font-medium animate-fade-in-up flex items-start gap-3 transition-colors duration-200`}
              style={{
                background: undoMessage.includes("Success") ? 'var(--color-success-bg)' : 'var(--color-danger-bg)',
                border: `1px solid ${undoMessage.includes("Success") ? 'var(--color-success)' : 'var(--color-danger)'}`,
                color: undoMessage.includes("Success") ? 'var(--color-success)' : 'var(--color-danger)',
              }}
            >
              {undoMessage.includes("Success") ? (
                <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
              <p>{undoMessage}</p>
            </div>
          )}

          {/* Additional Info Card */}
          <div 
            className="p-5 rounded-2xl transition-colors duration-200"
            style={{
              background: 'var(--color-bg-subtle)',
              border: '1px solid var(--color-border)',
            }}
          >
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors duration-200" style={{ background: 'var(--color-accent-glow)' }}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--color-accent-primary)' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h4 className="text-sm font-semibold mb-1 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>How it works</h4>
                <p className="text-sm leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                  Each time you optimise your calendar, we create a snapshot. Only the most recent snapshot is stored. 
                  Undoing will restore all events to their previous times and durations.
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}