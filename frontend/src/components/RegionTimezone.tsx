"use client";

import { useState, useEffect } from "react";
import { fetchWithRetry } from "@/lib/fetchUtils";

type RegionTimezoneProps = {
  userId: string;
  onBack: () => void;
};

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function RegionTimezone({ userId, onBack }: RegionTimezoneProps) {
  const [timezones, setTimezones] = useState<string[]>([]);
  const [selectedZone, setSelectedZone] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [currentTimePreview, setCurrentTimePreview] = useState<string>("");

  // Load valid timezones and default to browser's current zone
  useEffect(() => {
    try {
      // Intl.supportedValuesOf is widely supported in modern browsers
      const zones = Intl.supportedValuesOf("timeZone");
      setTimezones(zones);
      
      const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      setSelectedZone(browserZone);
    } catch (error) {
      console.error("Timezone API not supported", error);
      // Safe fallback
      setTimezones(["Europe/London", "America/New_York", "UTC"]);
      setSelectedZone("UTC");
    }
  }, []);

  // Live clock preview for the selected timezone
  useEffect(() => {
    if (!selectedZone) return;

    const updatePreview = () => {
      try {
        const timeString = new Intl.DateTimeFormat("en-GB", {
          timeZone: selectedZone,
          timeStyle: "medium",
          dateStyle: "full",
        }).format(new Date());
        setCurrentTimePreview(timeString);
      } catch (e) {
        setCurrentTimePreview("Invalid Timezone");
      }
    };

    updatePreview();
    const interval = setInterval(updatePreview, 1000);
    return () => clearInterval(interval);
  }, [selectedZone]);

  const handleSave = async () => {
    if (!selectedZone) return;
    setIsSubmitting(true);
    setSuccessMessage(null);

    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/users/timezone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          timezone: selectedZone,
        }),
        timeoutMs: 8000,
      });

      if (res.ok) {
        setSuccessMessage("Timezone successfully updated.");
        setTimeout(() => setSuccessMessage(null), 3000);
      } else {
        console.error("Failed to update timezone");
      }
    } catch (error) {
      console.error("Network error saving timezone:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAutoDetect = () => {
    const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    setSelectedZone(browserZone);
  };

  return (
    <div className="min-h-screen font-sans flex flex-col pb-32 bg-transparent transition-colors duration-500">
      {/* Header */}
      <div
        className="sticky top-0 z-10 px-4 py-3 flex items-center justify-between"
        style={{ 
          paddingTop: "calc(env(safe-area-inset-top, 20px) + 8px)",
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(var(--blur-lg))',
          WebkitBackdropFilter: 'blur(var(--blur-lg))',
          borderBottom: '1px solid var(--color-border)'
        }}
      >
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[16px] font-semibold transition-colors active:opacity-50"
          style={{ color: 'var(--color-accent-primary)' }}
        >
          <span className="text-2xl leading-none">‹</span> Settings
        </button>

        <span className="text-[15px] font-bold truncate px-4 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
          Region & Time
        </span>

        <div className="w-16"></div>
      </div>

      <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-10 animate-fadeIn">
        <div className="space-y-2 text-center md:text-left">
          <h2 className="text-3xl font-extrabold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
            Timezone Setup
          </h2>
          <p className="text-sm max-w-xl transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
            Ensure your calendar and AI scheduling engine are perfectly synced with your current location.
          </p>
        </div>

        <div 
          className="rounded-2xl overflow-hidden transition-all duration-200"
          style={{
            background: 'var(--color-bg-glass-strong)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <div className="p-6 space-y-6">
            
            <div className="space-y-3">
              <label htmlFor="timezone-select" className="block text-[13px] font-bold uppercase tracking-widest transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
                Select Timezone
              </label>
              <select
                id="timezone-select"
                value={selectedZone}
                onChange={(e) => setSelectedZone(e.target.value)}
                className="w-full text-[15px] p-4 rounded-xl outline-none appearance-none cursor-pointer transition-colors duration-200"
                style={{ 
                  background: 'var(--color-surface)', 
                  color: 'var(--color-text-primary)',
                  border: '1px solid var(--color-border)',
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394a3b8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, 
                  backgroundPosition: `right 1rem center`, 
                  backgroundRepeat: `no-repeat`, 
                  backgroundSize: `1.5em 1.5em` 
                }}
              >
                {timezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>

            {/* Live Preview Card */}
            <div 
              className="rounded-xl p-5 flex items-center justify-between transition-colors duration-200"
              style={{
                background: 'var(--color-bg-subtle)',
                border: '1px solid var(--color-border-accent)',
              }}
            >
              <div>
                <p className="text-[11px] font-bold uppercase tracking-widest mb-1 transition-colors duration-200" style={{ color: 'var(--color-accent-primary)' }}>
                  Local Time Preview
                </p>
                <p className="font-medium text-[15px] transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
                  {currentTimePreview || "Loading..."}
                </p>
              </div>
              <div 
                className="w-10 h-10 rounded-full flex items-center justify-center transition-all duration-200"
                style={{
                  background: 'var(--color-accent-gradient)',
                  boxShadow: 'var(--shadow-glow)',
                }}
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: 'var(--color-bg-base)' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <button
                onClick={handleAutoDetect}
                className="text-[13px] font-semibold transition-colors duration-200 hover:opacity-80"
                style={{ color: 'var(--color-accent-primary)' }}
              >
                Auto-detect my location
              </button>
            </div>

          </div>

          <div 
            className="flex items-center justify-between px-6 py-4 transition-colors duration-200"
            style={{
              background: 'var(--color-bg-subtle)',
              borderTop: '1px solid var(--color-border)',
            }}
          >
            <div>
              {successMessage && (
                <span className="text-sm font-semibold animate-fadeIn transition-colors duration-200" style={{ color: 'var(--color-success)' }}>
                  {successMessage}
                </span>
              )}
            </div>
            <button
              onClick={handleSave}
              disabled={isSubmitting || !selectedZone}
              className="px-8 py-2.5 text-[15px] font-semibold rounded-xl transition-all disabled:opacity-50 active:scale-[0.98] btn-primary"
            >
              {isSubmitting ? "Saving..." : "Save Timezone"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}