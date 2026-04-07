"use client";

import { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/lib/AuthContext";
import NavigationBar from "@/components/NavigationBar";
import RemindersModal, { Reminder } from "@/components/RemindersModal";
import { fetchWithRetry } from "@/lib/fetchUtils"; 
import { App as CapacitorApp } from '@capacitor/app'; 
import { Capacitor } from '@capacitor/core';
import GlobalSearchModal from "@/components/GlobalSearchModal";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function RemindersPage() {
  const { user, loading: authLoading } = useAuth();
  const userId = user?.uid || null;
  
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingReminder, setEditingReminder] = useState<Reminder | null>(null);

  const [selectedReminderIds, setSelectedReminderIds] = useState<string[]>([]);
  
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [sortBy, setSortBy] = useState<"time_asc" | "time_desc" | "priority_desc">("time_asc");
  const [statusFilter, setStatusFilter] = useState<string>("all"); 
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [dateFilter, setDateFilter] = useState<string>("");

  useEffect(() => {
    if (!authLoading) {
      if (userId) {
        fetchReminders(userId);
      } else {
        setIsLoading(false);
      }
    }
  }, [userId, authLoading]);

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !userId) return;

    const appStateListener = CapacitorApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        fetchReminders(userId); 
      }
    });

    return () => {
      appStateListener.then(listener => listener.remove());
    };
  }, [userId]);

  const fetchReminders = async (uid: string) => {
    setIsLoading(true);
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/reminders/list/${uid}`, {
        method: "GET",
        timeoutMs: 8000 
      });
      if (res.ok) {
        const data = await res.json();
        setReminders(data.reminders || []);
      }
    } catch (error) {
      console.error("Failed to fetch reminders:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleReminderSelection = (id: string) => {
    setSelectedReminderIds(prev => 
      prev.includes(id) ? prev.filter(selectedId => selectedId !== id) : [...prev, id]
    );
  };

  const clearSelection = () => setSelectedReminderIds([]);

  const handleBulkDismiss = async () => {
    if (!userId || selectedReminderIds.length === 0) return;
    setIsLoading(true);
    try {
      await Promise.all(selectedReminderIds.map(async (id) => {
        return fetchWithRetry(`${API_BASE_URL}/api/reminders/update`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id, user_id: userId, status: "dismissed" }),
        });
      }));
      await fetchReminders(userId);
      clearSelection();
    } catch (error) {
      console.error("Bulk dismiss failed", error);
      setIsLoading(false);
    }
  };

  const handleBulkDelete = async () => {
    if (!userId || selectedReminderIds.length === 0) return;
    setIsLoading(true);
    try {
      await Promise.all(selectedReminderIds.map(id => 
        fetchWithRetry(`${API_BASE_URL}/api/reminders/delete`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, reminder_id: id }),
        })
      ));
      await fetchReminders(userId);
      clearSelection();
    } catch (error) {
      console.error("Bulk delete failed", error);
      setIsLoading(false);
    }
  };

  const handleOpenNewReminder = () => {
    setEditingReminder(null);
    setIsModalOpen(true);
  };

  const handleEditReminder = (reminder: Reminder) => {
    if (selectedReminderIds.length > 0) {
      if (reminder.id) toggleReminderSelection(reminder.id);
      return;
    }
    setEditingReminder(reminder);
    setIsModalOpen(true);
  };

  const formatTimeInfo = (isoString?: string | null) => {
    if (!isoString) return { label: "No Time Set", color: "var(--color-text-tertiary)" };
    
    const targetDate = new Date(isoString);
    if (isNaN(targetDate.getTime())) return { label: "Invalid Time", color: "var(--color-danger)" };

    const today = new Date();
    
    const targetDay = new Date(targetDate.getFullYear(), targetDate.getMonth(), targetDate.getDate()).getTime();
    const todayDay = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const diffDays = Math.round((targetDay - todayDay) / (1000 * 60 * 60 * 24));
    
    const timeStr = targetDate.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

    if (diffDays < 0) return { label: `${diffDays * -1}d ago at ${timeStr}`, color: "var(--color-danger)" };
    if (diffDays === 0) return { label: `Today, ${timeStr}`, color: "var(--color-accent-primary)" };
    if (diffDays === 1) return { label: `Tomorrow, ${timeStr}`, color: "var(--color-accent-primary)" };
    
    return { 
      label: `${targetDate.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${timeStr}`, 
      color: "var(--color-text-secondary)" 
    };
  };

  const getTypeBadge = (type: string) => {
    switch (type) {
      case "event": return { label: "EVENT", bg: "var(--color-info-bg)", text: "var(--color-info)", border: "var(--color-info)" };
      case "task": return { label: "TASK", bg: "var(--color-success-bg)", text: "var(--color-success)", border: "var(--color-success)" };
      default: return { label: "STANDALONE", bg: "var(--color-bg-subtle)", text: "var(--color-text-secondary)", border: "var(--color-border)" };
    }
  };

  const processedReminders = useMemo(() => {
    let filtered = reminders.filter(r => {
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      if (typeFilter !== "all" && r.type !== typeFilter) return false;
      if (priorityFilter !== "all" && r.priority !== priorityFilter) return false;
      
      if (dateFilter) {
        if (!r.trigger_time) return false;
        
        const rDateLocal = new Date(r.trigger_time);
        const yyyy = rDateLocal.getFullYear();
        const mm = String(rDateLocal.getMonth() + 1).padStart(2, "0");
        const dd = String(rDateLocal.getDate()).padStart(2, "0");
        const localDateStr = `${yyyy}-${mm}-${dd}`;
        
        if (localDateStr !== dateFilter) return false;
      }
      return true;
    });

    filtered.sort((a, b) => {
      switch (sortBy) {
        case "priority_desc": 
          return (a.priority === "high" ? 0 : 1) - (b.priority === "high" ? 0 : 1);
        case "time_desc":
          if (!a.trigger_time) return 1;
          if (!b.trigger_time) return -1;
          return new Date(b.trigger_time).getTime() - new Date(a.trigger_time).getTime();
        case "time_asc":
        default:
          if (!a.trigger_time) return 1;
          if (!b.trigger_time) return -1;
          return new Date(a.trigger_time).getTime() - new Date(b.trigger_time).getTime();
      }
    });

    const groups: Record<string, Reminder[]> = {
      high_priority: [],
      upcoming_time: [],
      location: [],
      past: [], 
    };

    filtered.forEach(reminder => {
      if (reminder.status === "dismissed" || reminder.status === "delivered" || reminder.status === "missed") {
        groups.past.push(reminder);
      } else if (reminder.priority === "high") {
        groups.high_priority.push(reminder);
      } else if (reminder.trigger_type === "location") {
        groups.location.push(reminder);
      } else {
        groups.upcoming_time.push(reminder);
      }
    });

    return groups;
  }, [reminders, statusFilter, typeFilter, priorityFilter, dateFilter, sortBy]);

  const renderReminderCard = (reminder: Reminder, isPast: boolean) => {
    const timeInfo = formatTimeInfo(reminder.trigger_time);
    const typeBadge = getTypeBadge(reminder.type);
    const isHighPriority = reminder.priority === "high" && !isPast;
    const isLocation = reminder.trigger_type === "location";
    const isSelected = reminder.id ? selectedReminderIds.includes(reminder.id) : false;

    return (
      <div 
        key={reminder.id}
        onClick={() => handleEditReminder(reminder)}
        className={`p-4 sm:p-5 rounded-3xl border transition-all cursor-pointer relative group flex gap-4 items-start duration-300
          ${isPast ? 'opacity-60 grayscale-[0.5]' : ''}
          ${isSelected ? 'scale-[1.02] shadow-md z-10' : 'shadow-sm'}
        `}
        style={{
          background: isHighPriority ? 'var(--color-danger-bg)' : 'var(--color-surface)',
          borderColor: isSelected ? 'var(--color-accent-primary)' : isHighPriority ? 'var(--color-danger)' : 'var(--color-border)',
          boxShadow: isSelected ? '0 0 0 1px var(--color-accent-primary), var(--shadow-md)' : 'var(--shadow-sm)'
        }}
      >
        <button 
          onClick={(e) => {
            e.stopPropagation();
            if (reminder.id) toggleReminderSelection(reminder.id);
          }}
          className={`flex-shrink-0 mt-1 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all duration-200`}
          style={{
            background: isSelected ? 'var(--color-accent-primary)' : 'var(--color-bg-subtle)',
            borderColor: isSelected ? 'var(--color-accent-primary)' : 'var(--color-border-accent)',
          }}
        >
          <svg className={`w-4 h-4 transition-opacity ${isSelected ? 'opacity-100' : 'opacity-0'}`} style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex justify-between items-start gap-2">
            <h3 
              className={`text-base sm:text-lg font-bold truncate transition-colors duration-200 ${isPast ? 'line-through' : ''}`}
              style={{ color: isPast ? 'var(--color-text-muted)' : isHighPriority ? 'var(--color-danger)' : 'var(--color-text-primary)' }}
            >
              {reminder.title}
            </h3>
            {isHighPriority && (
              <span 
                className="flex-shrink-0 flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-md border"
                style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)', borderColor: 'var(--color-danger)' }}
              >
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" /></svg>
                High
              </span>
            )}
          </div>

          {reminder.body && !isPast && (
            <p className="text-sm mt-1 line-clamp-2 leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
              {reminder.body}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2 mt-3.5">
            {isLocation ? (
              <span 
                className="flex items-center gap-1.5 px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border"
                style={{ background: 'var(--color-warning-bg)', color: 'var(--color-warning)', borderColor: 'var(--color-warning)' }}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
                </svg>
                {reminder.location_data?.trigger_on === "entry" ? "When Arriving" : "When Leaving"}
              </span>
            ) : (
              <span 
                className={`flex items-center gap-1.5 px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border shadow-sm transition-colors duration-200`}
                style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: timeInfo.color }}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {timeInfo.label}
              </span>
            )}

            <span 
              className={`px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border transition-colors duration-200`}
              style={{ background: typeBadge.bg, color: typeBadge.text, borderColor: typeBadge.border }}
            >
              {typeBadge.label}
            </span>

            {reminder.repeat !== "none" && !isPast && (
              <span 
                className="flex items-center gap-1 px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border ml-auto transition-colors duration-200"
                style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)' }}
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                {reminder.repeat}
              </span>
            )}
          </div>
        </div>
      </div>
    );
  };

  if ((authLoading || isLoading) && reminders.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center transition-colors duration-500" style={{ background: 'var(--color-bg-base)' }}>
        <div className="flex flex-col items-center gap-4">
          <div 
            className="w-16 h-16 rounded-2xl flex items-center justify-center animate-pulse transition-colors duration-500"
            style={{
              background: 'var(--color-accent-gradient)',
              boxShadow: 'var(--shadow-glow)',
            }}
          >
            <svg className="w-8 h-8" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
            </svg>
          </div>
          <p className="font-medium transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Loading your alerts...</p>
        </div>
      </div>
    );
  }

  const activeCount = reminders.filter(r => r.status === "pending").length;

  return (
    <div 
      className="min-h-screen font-sans pb-40 relative transition-colors duration-500"
      style={{ background: 'var(--color-bg-base)' }}
    >
      {/* Decorative Orbs handled entirely by body::before in global.css */}
      
      <div className="sticky top-0 z-30 transition-all duration-300">
        {selectedReminderIds.length > 0 ? (
          <div 
            className="px-4 sm:px-6 pt-[calc(env(safe-area-inset-top,24px)+20px)] pb-4 flex items-center justify-between transition-colors duration-500"
            style={{
              background: 'var(--color-accent-gradient)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <div className="flex items-center gap-3">
              <button onClick={clearSelection} className="p-2 rounded-full transition-colors opacity-80 hover:opacity-100" style={{ color: 'var(--color-bg-base)', background: 'rgba(255, 255, 255, 0.1)' }}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <span className="font-bold text-lg" style={{ color: 'var(--color-bg-base)' }}>{selectedReminderIds.length}</span>
            </div>
            <div className="flex gap-2">
              <button 
                onClick={handleBulkDelete} 
                className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all hover:opacity-90"
                style={{ background: 'var(--color-danger)', color: 'var(--color-bg-base)' }}
              >
                Delete
              </button>
              <button 
                onClick={handleBulkDismiss} 
                className="px-4 py-1.5 rounded-lg text-xs font-bold shadow-sm transition-all hover:opacity-90"
                style={{ background: 'var(--color-bg-base)', color: 'var(--color-text-primary)' }}
              >
                Dismiss
              </button>
            </div>
          </div>
        ) : (
          <div className="px-6 pt-[calc(env(safe-area-inset-top,24px)+24px)] pb-4 flex justify-between items-end transition-colors duration-500"
            style={{
              background: 'var(--color-bg-glass-strong)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              borderBottom: '1px solid var(--color-border)',
            }}
          >
            <div>
              <h1 className="text-3xl font-bold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Reminders</h1>
              <p className="text-sm font-medium mt-1 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                {activeCount} active {activeCount === 1 ? 'alert' : 'alerts'}
              </p>
            </div>
            
            {/* --- BUTTON GROUP --- */}
            <div className="flex flex-wrap gap-2 justify-end">
              {/* --- SEARCH BUTTON --- */}
              <button 
                onClick={() => setIsSearchOpen(true)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold shadow-sm transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] hover:bg-black/5 dark:hover:bg-white/10"
                style={{
                  background: 'var(--color-bg-glass)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-secondary)',
                }}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                </svg>
                Search
              </button>

              {/* --- FILTER BUTTON --- */}
              <button 
                onClick={() => setIsFilterOpen(!isFilterOpen)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold shadow-sm transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] hover:bg-black/5 dark:hover:bg-white/10"
                style={{
                  background: isFilterOpen ? 'var(--color-surface-hover)' : 'var(--color-bg-glass)',
                  border: isFilterOpen ? '1px solid var(--color-accent-primary)' : '1px solid var(--color-border)',
                  color: isFilterOpen ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)',
                }}
              >
                {/* Fixed SVG viewBox */}
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 01-.659 1.591l-5.432 5.432a2.25 2.25 0 00-.659 1.591v2.927a2.25 2.25 0 01-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 00-.659-1.591L3.659 7.409A2.25 2.25 0 013 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0112 3z" />
                </svg>
                Filter
              </button>
            </div>
          </div>
        )}

        {isFilterOpen && selectedReminderIds.length === 0 && (
          <div 
            className="p-6 shadow-sm animate-fadeIn transition-colors duration-500"
            style={{
              background: 'var(--color-bg-glass)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              borderBottom: '1px solid var(--color-border)',
            }}
          >
            <div className="max-w-3xl mx-auto grid grid-cols-2 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Sort Order</label>
                <select 
                  value={sortBy} 
                  onChange={e => setSortBy(e.target.value as any)} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                >
                  <option value="time_asc">Soonest First</option>
                  <option value="time_desc">Latest First</option>
                  <option value="priority_desc">Highest Priority</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Status</label>
                <select 
                  value={statusFilter} 
                  onChange={e => setStatusFilter(e.target.value)} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                >
                  <option value="all">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="delivered">Delivered</option>
                  <option value="dismissed">Dismissed</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Reminder Type</label>
                <select 
                  value={typeFilter} 
                  onChange={e => setTypeFilter(e.target.value)} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                >
                  <option value="all">All Types</option>
                  <option value="event">Event Links</option>
                  <option value="task">Task Links</option>
                  <option value="standalone">Standalone</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Priority Level</label>
                <select 
                  value={priorityFilter} 
                  onChange={e => setPriorityFilter(e.target.value)} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                >
                  <option value="all">All Priorities</option>
                  <option value="high">High Only</option>
                  <option value="standard">Standard Only</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Specific Date</label>
                <input 
                  type="date" 
                  value={dateFilter} 
                  onChange={e => setDateFilter(e.target.value)} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                />
              </div>
            </div>
            <div className="max-w-3xl mx-auto mt-4 pt-4 flex justify-end" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
              <button 
                onClick={() => {
                  setSortBy("time_asc");
                  setStatusFilter("all");
                  setTypeFilter("all");
                  setPriorityFilter("all");
                  setDateFilter("");
                }} 
                className="text-sm font-semibold transition-colors hover:opacity-80"
                style={{ color: 'var(--color-accent-primary)' }}
              >
                Reset Filters
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="px-4 sm:px-6 pt-6 max-w-3xl mx-auto space-y-8">
        
        {processedReminders.high_priority.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 flex justify-between items-center transition-colors duration-200" style={{ color: 'var(--color-danger)' }}>
              Requires Attention
              <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)' }}>{processedReminders.high_priority.length}</span>
            </h2>
            {processedReminders.high_priority.map(r => renderReminderCard(r, false))}
          </div>
        )}

        {processedReminders.upcoming_time.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Upcoming</h2>
            {processedReminders.upcoming_time.map(r => renderReminderCard(r, false))}
          </div>
        )}

        {processedReminders.location.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 flex items-center gap-1.5 transition-colors duration-200" style={{ color: 'var(--color-warning)' }}>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
              </svg>
              Location Geofences
            </h2>
            {processedReminders.location.map(r => renderReminderCard(r, false))}
          </div>
        )}

        {processedReminders.past.length > 0 && (
          <div className="space-y-4 pt-4 transition-colors duration-500" style={{ borderTop: '1px solid var(--color-border)' }}>
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 flex justify-between transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
              Past & Dismissed
            </h2>
            {processedReminders.past.map(r => renderReminderCard(r, true))}
          </div>
        )}

      </div>

      {selectedReminderIds.length === 0 && (
        <button 
          onClick={handleOpenNewReminder}
          className="fixed bottom-28 right-6 w-14 h-14 rounded-full flex items-center justify-center active:scale-95 transition-all duration-300 z-40 btn-primary"
          style={{ padding: 0 }}
        >
          <svg className="w-7 h-7" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </button>
      )}

      {userId && (
        <RemindersModal 
          isOpen={isModalOpen} 
          onClose={() => setIsModalOpen(false)} 
          userId={userId} 
          editReminder={editingReminder} 
          onSaveSuccess={() => {
            if (userId) fetchReminders(userId);
            setSelectedReminderIds([]);
          }} 
        />
      )}

      {userId && (
        <GlobalSearchModal
          isOpen={isSearchOpen}
          onClose={() => setIsSearchOpen(false)}
          userId={userId}
          searchType="reminders" // Targets only reminders
          placeholder="Search reminders by name..."
          onResultClick={(result) => {
            const foundReminder = reminders.find(r => r.id === result.id);
            if (foundReminder) {
              setEditingReminder(foundReminder);
              setIsModalOpen(true);
            }
          }}
        />
      )}

      {selectedReminderIds.length === 0 && <NavigationBar />}
    </div>
  );
}