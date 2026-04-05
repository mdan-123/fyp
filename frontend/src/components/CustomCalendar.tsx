"use client";

import { useState, useRef, useEffect, TouchEvent } from "react";
import { CalendarEvent } from "@/types";

interface CustomCalendarProps {
  events: CalendarEvent[];
  onEventClick: (event: CalendarEvent, instanceDate?: Date, overlaps?: CalendarEvent[]) => void;
  onSync: () => void;
  isSyncing: boolean;
  onOptimise: (date: Date) => void;
  isPreviewMode?: boolean;
}

type ViewType = "day" | "week" | "month";
type WeekLayout = "timeline" | "stacked";

// --- Reading UTC to Local Format ---
const isEventOnDay = (event: CalendarEvent & { exception_dates?: string[], proposed_start?: string, start: string, recurrence?: string, recurrence_days?: string[] }, targetDay: Date) => {
  const dateStr = `${targetDay.getFullYear()}-${String(targetDay.getMonth() + 1).padStart(2, '0')}-${String(targetDay.getDate()).padStart(2, '0')}`;
  
  if (event.exception_dates && event.exception_dates.includes(dateStr)) {
    return false;
  }

  const activeStartStr = event.proposed_start || event.start;
  const start = new Date(activeStartStr);
  const startDayTime = new Date(start.getFullYear(), start.getMonth(), start.getDate()).getTime();
  const targetDayTime = new Date(targetDay.getFullYear(), targetDay.getMonth(), targetDay.getDate()).getTime();

  if (targetDayTime < startDayTime) return false;
  if (targetDayTime === startDayTime) return true;

  if (event.recurrence === 'daily' || event.recurrence === 'custom') {
    if (event.recurrence_days && event.recurrence_days.length > 0) {
      return event.recurrence_days.includes(targetDay.getDay().toString());
    }
    return true; 
  }
  
  if (event.recurrence === 'weekly') {
    return start.getDay() === targetDay.getDay();
  }
  
  if (event.recurrence === 'monthly') {
    return start.getDate() === targetDay.getDate();
  }

  return false;
};

// --- Reading UTC to Local Format ---
const getRenderTimeForDay = (event: any, targetDay: Date) => {
  const baseStart = new Date(event.proposed_start || event.start);
  const baseEnd = new Date(event.proposed_end || event.end);

  const renderStart = new Date(targetDay);
  renderStart.setHours(baseStart.getHours(), baseStart.getMinutes(), 0, 0);

  const renderEnd = new Date(targetDay);
  renderEnd.setHours(baseEnd.getHours(), baseEnd.getMinutes(), 0, 0);

  if (renderEnd.getTime() < renderStart.getTime()) {
    renderEnd.setDate(renderEnd.getDate() + 1);
  }

  return { start: renderStart, end: renderEnd };
};

const groupOverlappingEvents = (eventsForDay: any[], day: Date) => {
  const withTimes = eventsForDay.map(e => ({ ...e, renderTime: getRenderTimeForDay(e, day) }));
  withTimes.sort((a, b) => a.renderTime.start.getTime() - b.renderTime.start.getTime());

  const clusters: any[][] = [];
  let currentCluster: any[] = [];
  let clusterEnd = 0;

  withTimes.forEach(ev => {
    const start = ev.renderTime.start.getTime();
    const end = ev.renderTime.end.getTime();
    if (currentCluster.length === 0) {
      currentCluster.push(ev);
      clusterEnd = end;
    } else if (start < clusterEnd) {
      currentCluster.push(ev);
      clusterEnd = Math.max(clusterEnd, end);
    } else {
      clusters.push(currentCluster);
      currentCluster = [ev];
      clusterEnd = end;
    }
  });
  if (currentCluster.length > 0) clusters.push(currentCluster);

  clusters.forEach(cluster => {
    const columns: any[][] = [];
    cluster.forEach(ev => {
      let placed = false;
      for (let i = 0; i < columns.length; i++) {
        const lastEv = columns[i][columns[i].length - 1];
        if (ev.renderTime.start.getTime() >= lastEv.renderTime.end.getTime()) {
          columns[i].push(ev);
          ev.colIdx = i;
          placed = true;
          break;
        }
      }
      if (!placed) {
        ev.colIdx = columns.length;
        columns.push([ev]);
      }
    });
    const totalCols = columns.length;
    cluster.forEach(ev => {
      ev.totalCols = totalCols;
      ev.isOverlapping = totalCols > 1;
    });
  });

  return withTimes;
};

// Map backend categories to our dual-theme CSS variables
const getCategoryClass = (category?: string) => {
  switch (category) {
    case "DEEP_WORK": return "category-deep-work";
    case "SHALLOW_WORK": return "category-shallow-work";
    case "MEETING": return "category-meeting";
    case "WORKOUT": return "category-workout";
    case "SOCIAL": return "category-social";
    case "LEISURE": return "category-leisure";
    case "TRAVEL": return "category-travel";
    case "MEAL": return "category-meal";
    default: return "category-default";
  }
};

export default function CustomCalendar({ events, onEventClick, onSync, isSyncing, onOptimise, isPreviewMode = false }: CustomCalendarProps) {
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [view, setView] = useState<ViewType>("week");
  const [weekLayout, setWeekLayout] = useState<WeekLayout>("timeline");
  
  const [touchStartX, setTouchStartX] = useState<number | null>(null);
  const [pinchStartDist, setPinchStartDist] = useState<number | null>(null);
  const [pinchCurrentDist, setPinchCurrentDist] = useState<number | null>(null);
  
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const PIXELS_PER_MINUTE = 1;
  const hours: number[] = Array.from({ length: 24 }, (_, i) => i);

  useEffect(() => {
    if (view !== "month" && weekLayout === "timeline" && scrollRef.current) {
      scrollRef.current.scrollTop = 8 * 60 * PIXELS_PER_MINUTE;
    }
  }, [view, weekLayout, currentDate]);

  const handleTouchStart = (e: TouchEvent<HTMLDivElement>) => {
    if (e.touches.length === 1) setTouchStartX(e.targetTouches[0].clientX);
    else if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      setPinchStartDist(Math.sqrt(dx * dx + dy * dy));
    }
  };

  const handleTouchMove = (e: TouchEvent<HTMLDivElement>) => {
    if (e.touches.length === 2 && pinchStartDist !== null) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      setPinchCurrentDist(Math.sqrt(dx * dx + dy * dy));
    }
  };
  
  const handleTouchEnd = (e: TouchEvent<HTMLDivElement>) => {
    if (e.changedTouches.length === 1 && touchStartX !== null) {
      const touchEndX = e.changedTouches[0].clientX;
      const distance = touchStartX - touchEndX;
      
      if (Math.abs(distance) > 50) {
        const daysToAdd = view === "day" ? 1 : view === "week" ? 7 : 30;
        const multiplier = distance > 50 ? 1 : -1;
        const newDate = new Date(currentDate);
        if (view === "month") newDate.setMonth(newDate.getMonth() + multiplier);
        else newDate.setDate(newDate.getDate() + (daysToAdd * multiplier));
        setCurrentDate(newDate);
      }
      setTouchStartX(null);
    }

    if (pinchStartDist !== null && pinchCurrentDist !== null) {
      const difference = pinchCurrentDist - pinchStartDist;
      if (difference > 60) {
        if (view === "month") setView("week");
        else if (view === "week") setView("day");
      } else if (difference < -60) {
        if (view === "day") setView("week");
        else if (view === "week") setView("month");
      }
      setPinchStartDist(null);
      setPinchCurrentDist(null);
    }
  };

  const navigateDate = (direction: number) => {
    const newDate = new Date(currentDate);
    if (view === "month") newDate.setMonth(newDate.getMonth() + direction);
    else {
      const daysToAdd = view === "day" ? 1 : 7;
      newDate.setDate(newDate.getDate() + (daysToAdd * direction));
    }
    setCurrentDate(newDate);
  };

  const getDaysInView = (): Date[] => {
    if (view === "day") return [currentDate];
    if (view === "week") {
      const startOfWeek = new Date(currentDate);
      let day = startOfWeek.getDay();
      if (day === 0) day = 7; 
      const diff = startOfWeek.getDate() - day + 1;
      startOfWeek.setDate(diff);
      return Array.from({ length: 7 }, (_, i) => {
        const d = new Date(startOfWeek);
        d.setDate(d.getDate() + i);
        return d;
      });
    }
    return [];
  };

  const getMonthDays = (): Date[] => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    
    const days: Date[] = [];
    let startOffset = firstDay.getDay() - 1;
    if (startOffset === -1) startOffset = 6; 
    
    for (let i = startOffset; i > 0; i--) days.push(new Date(year, month, 1 - i));
    for (let i = 1; i <= lastDay.getDate(); i++) days.push(new Date(year, month, i));
    
    const remaining = (7 - (days.length % 7)) % 7;
    for (let i = 1; i <= remaining; i++) days.push(new Date(year, month + 1, i));
    return days;
  };

  const daysToRender = getDaysInView();
  const monthDays = view === "month" ? getMonthDays() : [];
  const weekDayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  return (
    <div className="flex flex-col h-full relative transition-colors duration-500 bg-transparent">
      {/* Header */}
      <div 
        className="px-4 pb-4 flex justify-between items-end z-20 transition-colors duration-500"
        style={{ 
          paddingTop: 'calc(env(safe-area-inset-top, 40px) + 16px)',
          background: 'var(--color-bg-glass-strong)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <div className="flex items-center justify-between w-full sm:w-auto">
          <div className="relative group cursor-pointer">
            <input 
              type="month" 
              className="absolute inset-0 opacity-0 cursor-pointer"
              onChange={(e) => e.target.value && setCurrentDate(new Date(e.target.value))}
            />
            <h1 
              className="text-xl sm:text-2xl font-bold transition-colors duration-200 tracking-tight flex items-center gap-2"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {currentDate.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })}
              <svg className="w-4 h-4 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </h1>
          </div>

          {!isPreviewMode && (
            <div className="sm:hidden ml-auto flex items-center gap-2">
              <button 
                onClick={() => onOptimise(currentDate)}
                className="p-2.5 rounded-xl transition-all duration-200 active:scale-95"
                style={{
                  background: 'var(--color-accent-glow)',
                  border: '1px solid var(--color-border-accent)',
                  color: 'var(--color-accent-primary)',
                }}
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                </svg>
              </button>

              <button 
                onClick={onSync}
                disabled={isSyncing}
                className="p-2.5 rounded-xl transition-all duration-200 disabled:opacity-50 active:scale-95"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: isSyncing ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)',
                }}
              >
                <svg className={`w-5 h-5 ${isSyncing ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
              </button>
            </div>
          )}
        </div>

        <div className="hidden sm:flex items-center gap-3">
          {!isPreviewMode && (
            <div className="flex items-center gap-2">
              <button 
                onClick={() => onOptimise(currentDate)}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] btn-primary"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                </svg>
                Optimise
              </button>

              <button 
                onClick={onSync}
                disabled={isSyncing}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl transition-all duration-200 disabled:opacity-50 hover:scale-[1.01] active:scale-[0.99] btn-secondary"
              >
                <svg className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={isSyncing ? { color: 'var(--color-accent-primary)' } : {}}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                {isSyncing ? "Syncing..." : "Sync"}
              </button>
            </div>
          )}

          <div 
            className="flex p-1 rounded-xl transition-colors duration-500"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
            }}
          >
            {(['day', 'week', 'month'] as ViewType[]).map((v) => (
              <button 
                key={v}
                onClick={() => setView(v)}
                className={`px-4 py-1.5 text-sm font-medium rounded-lg capitalize transition-all duration-200`}
                style={view === v ? { background: 'var(--color-surface-hover)', color: 'var(--color-text-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}
              >
                {v}
              </button>
            ))}
          </div>
          
          <div className="flex gap-1">
            <button 
              onClick={() => navigateDate(-1)} 
              className="p-2 rounded-lg transition-all duration-200 active:scale-95"
              style={{ color: 'var(--color-text-secondary)', background: 'var(--color-surface)' }}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button 
              onClick={() => navigateDate(1)} 
              className="p-2 rounded-lg transition-all duration-200 active:scale-95"
              style={{ color: 'var(--color-text-secondary)', background: 'var(--color-surface)' }}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {view === "week" && (
        <div 
          className="flex justify-center py-2 transition-colors duration-500"
          style={{
            background: 'var(--color-bg-glass)',
            borderBottom: '1px solid var(--color-border)',
          }}
        >
          <div 
            className="flex p-0.5 rounded-lg text-xs transition-colors duration-500"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
            }}
          >
            <button 
              onClick={() => setWeekLayout("timeline")}
              className={`px-3 py-1.5 rounded-md transition-all duration-200 font-medium`}
              style={weekLayout === "timeline" ? { background: 'var(--color-surface-hover)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}
            >
              Timeline
            </button>
            <button 
              onClick={() => setWeekLayout("stacked")}
              className={`px-3 py-1.5 rounded-md transition-all duration-200 font-medium`}
              style={weekLayout === "stacked" ? { background: 'var(--color-surface-hover)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}
            >
              Stacked List
            </button>
          </div>
        </div>
      )}

      <div 
        className="flex-1 flex flex-col overflow-hidden transition-colors duration-500"
        style={{ background: 'var(--color-bg-base)' }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        
        {view === "month" ? (
          <div className="flex-1 flex flex-col h-full transition-colors duration-500" style={{ background: 'var(--color-bg-base)' }}>
            <div 
              className="grid grid-cols-7 z-10 transition-colors duration-500"
              style={{
                background: 'var(--color-bg-glass-strong)',
                borderBottom: '1px solid var(--color-border)',
              }}
            >
              {weekDayNames.map(d => (
                <div key={d} className="py-2 text-center text-[10px] uppercase font-semibold tracking-wide transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>{d}</div>
              ))}
            </div>
            <div className="flex-1 grid grid-cols-7 auto-rows-fr gap-[1px] transition-colors duration-500" style={{ background: 'var(--color-border-subtle)' }}>
              {monthDays.map((day, i) => {
                const dayEvents = events.filter(e => isEventOnDay(e as any, day));
                const isCurrentMonth = day.getMonth() === currentDate.getMonth();
                const isToday = day.toDateString() === new Date().toDateString();

                return (
                  <div 
                    key={i} 
                    onClick={() => {
                      setCurrentDate(day);
                      setView("week"); 
                    }}
                    className={`p-1 sm:p-2 flex flex-col cursor-pointer transition-colors overflow-hidden ${!isCurrentMonth ? 'opacity-40' : ''}`}
                    style={{ background: 'var(--color-surface)' }}
                  >
                    <div className="flex justify-center sm:justify-end mb-1">
                      <span 
                        className={`text-[10px] sm:text-xs font-medium w-5 h-5 sm:w-6 sm:h-6 flex items-center justify-center rounded-full transition-colors duration-200 ${isToday ? 'font-semibold' : ''}`}
                        style={isToday ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)' } : { color: 'var(--color-text-primary)' }}
                      >
                        {day.getDate()}
                      </span>
                    </div>
                    
                    <div className="flex flex-col gap-0.5 sm:gap-1 overflow-hidden">
                      {dayEvents.slice(0, 4).map((e: any, idx) => {
                        const isConflict = e.requires_review || e.has_drifted;
                        const isGhost = e.is_ghost;
                        const isCompleted = e.completion_status === 'completed';
                        const isMissed = e.completion_status === 'missed';
                        const catClass = getCategoryClass(e.category);
                        
                        let bgStyle = "var(--cat-bg)";
                        let borderStyle = "1px solid var(--cat-border)";
                        let textStyle = "var(--cat-text)";

                        if (isConflict) {
                          bgStyle = "var(--color-danger-bg)";
                          borderStyle = "1px solid var(--color-danger)";
                          textStyle = "var(--color-danger)";
                        } else if (isCompleted) {
                          bgStyle = "var(--color-success-bg)";
                          borderStyle = "1px solid var(--color-success)";
                          textStyle = "var(--color-success)";
                        } else if (isMissed) {
                          bgStyle = "var(--color-bg-subtle)";
                          borderStyle = "1px dashed var(--color-border)";
                          textStyle = "var(--color-text-muted)";
                        }

                        return (
                          <div 
                            key={e.id || idx} 
                            onClick={(ev) => {
                              ev.stopPropagation(); 
                              if (!isPreviewMode) onEventClick(e, day);
                            }}
                            className={`flex items-center gap-1 text-[8px] sm:text-[10px] border rounded px-1 py-0.5 truncate font-medium transition-colors ${catClass}`}
                            style={{ background: bgStyle, border: borderStyle, color: textStyle }}
                          >
                            {isGhost ? (
                              <svg className="w-2.5 h-2.5 flex-shrink-0" style={{ color: textStyle }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                              </svg>
                            ) : isCompleted ? (
                              <svg className="w-2.5 h-2.5 flex-shrink-0" style={{ color: textStyle }} fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                            ) : e.is_locked ? (
                              <svg className="w-2.5 h-2.5 flex-shrink-0" style={{ color: textStyle }} fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
                              </svg>
                            ) : null}
                            <span className={`truncate ${isMissed ? 'line-through opacity-80' : ''}`}>{e.title}</span>
                          </div>
                        );
                      })}
                      {dayEvents.length > 4 && (
                        <div className="text-[8px] sm:text-[9px] font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
                          +{dayEvents.length - 4} more
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <>
            <div 
              className={`flex z-10 transition-colors duration-500 ${weekLayout === 'timeline' ? 'pl-10' : 'pl-0'}`}
              style={{
                background: 'var(--color-bg-glass-strong)',
                borderBottom: '1px solid var(--color-border)',
              }}
            >
              {daysToRender.map((day: Date, i: number) => (
                <div 
                  key={i} 
                  onClick={() => {
                    setCurrentDate(day);
                    setView("day"); 
                  }}
                  className="flex-1 py-2 text-center cursor-pointer transition-colors"
                  style={{ borderLeft: '1px solid var(--color-border-subtle)' }}
                >
                  <p className="text-[10px] uppercase font-medium transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>{day.toLocaleDateString('en-GB', { weekday: 'short' })}</p>
                  <p 
                    className={`text-lg mx-auto w-7 h-7 flex items-center justify-center rounded-full mt-0.5 transition-colors duration-200 ${day.toDateString() === new Date().toDateString() ? 'font-semibold' : ''}`}
                    style={day.toDateString() === new Date().toDateString() ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)' } : { color: 'var(--color-text-primary)' }}
                  >
                    {day.getDate()}
                  </p>
                </div>
              ))}
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto relative scroll-smooth transition-colors duration-500" style={{ background: 'var(--color-bg-base)' }}>
              
              {weekLayout === "stacked" ? (
                <div className="flex w-full min-h-full">
                  {daysToRender.map((day: Date, dayIndex: number) => (
                    <div key={dayIndex} className="flex-1 min-w-0 flex flex-col gap-1 p-1 transition-colors duration-500" style={{ borderRight: '1px solid var(--color-border-subtle)' }}>
                      {events
                        .filter(e => isEventOnDay(e as any, day))
                        .sort((a, b) => getRenderTimeForDay(a, day).start.getTime() - getRenderTimeForDay(b, day).start.getTime())
                        .map((event: any, idx: number) => {
                          const isConflict = event.requires_review || event.has_drifted;
                          const isGhost = event.is_ghost;
                          const isCompleted = event.completion_status === 'completed';
                          const isMissed = event.completion_status === 'missed';
                          const t = getRenderTimeForDay(event, day);
                          const catClass = getCategoryClass(event.category);
                          
                          let bgStyle = "var(--cat-bg)";
                          let borderStyle = "1px solid var(--cat-border)";
                          let textStyle = "var(--cat-text)";

                          if (isConflict) {
                            bgStyle = "var(--color-danger-bg)";
                            borderStyle = "1px solid var(--color-danger)";
                            textStyle = "var(--color-danger)";
                          } else if (isCompleted) {
                            bgStyle = "var(--color-success-bg)";
                            borderStyle = "1px solid var(--color-success)";
                            textStyle = "var(--color-success)";
                          } else if (isMissed) {
                            bgStyle = "var(--color-bg-subtle)";
                            borderStyle = "1px dashed var(--color-border)";
                            textStyle = "var(--color-text-muted)";
                          }

                          return (
                            <div
                              key={`${event.id}-${day.toDateString()}-${idx}`}
                              onClick={() => { if (!isPreviewMode) onEventClick(event, day); }}
                              className={`border rounded-md p-1.5 ${!isPreviewMode ? 'cursor-pointer' : ''} flex flex-col w-full overflow-hidden transition-all duration-200 ${catClass}`}
                              style={{ background: bgStyle, border: borderStyle, color: textStyle }}
                            >
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-[9px] font-semibold" style={{ color: textStyle }}>
                                  {t.start.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                                </span>
                                
                                {(event.travel_time || 0) > 0 ? (
                                  <span className="text-[8px] font-bold px-1.5 py-[1px] rounded-sm transition-colors duration-200" style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text-secondary)' }}>
                                    +{event.travel_time}m travel
                                  </span>
                                ) : null}
                                
                                {isGhost ? (
                                  <svg className="w-2.5 h-2.5" style={{ color: textStyle }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                                  </svg>
                                ) : isCompleted ? (
                                  <svg className="w-2.5 h-2.5" style={{ color: textStyle }} fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                                ) : event.is_locked ? (
                                  <svg className="w-2.5 h-2.5" style={{ color: textStyle }} fill="currentColor" viewBox="0 0 20 20">
                                    <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
                                  </svg>
                                ) : null}
                              </div>
                              
                              <span className={`text-[10px] font-medium leading-tight whitespace-normal break-words mt-0.5 ${isMissed ? 'line-through opacity-80' : ''}`}>
                                {event.title}
                              </span>
                            </div>
                          );
                        })}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex h-[1440px] relative w-full">
                  <div 
                    className="w-10 flex flex-col z-10 sticky left-0 transition-colors duration-500"
                    style={{
                      background: 'var(--color-surface)',
                      borderRight: '1px solid var(--color-border)',
                    }}
                  >
                    {hours.map((hour: number) => (
                      <div key={hour} className="flex-1 relative">
                        <span className="absolute -top-2 right-1 text-[9px] font-medium transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
                          {hour === 0 ? '12a' : hour < 12 ? `${hour}a` : hour === 12 ? '12p' : `${hour - 12}p`}
                        </span>
                      </div>
                    ))}
                  </div>

                  {daysToRender.map((day: Date, dayIndex: number) => {
                    const dayEventsRaw = events.filter(e => isEventOnDay(e as any, day));
                    const processedEvents = groupOverlappingEvents(dayEventsRaw, day);

                    return (
                      <div key={dayIndex} className="flex-1 relative min-w-0 transition-colors duration-500" style={{ borderRight: '1px solid var(--color-border-subtle)' }}>
                        {hours.map((hour: number) => (
                          <div key={hour} className="absolute w-full transition-colors duration-500" style={{ top: `${hour * 60}px`, height: '60px', borderTop: '1px solid var(--color-border-subtle)' }} />
                        ))}
                        
                        {processedEvents.map((event: any, idx: number) => {
                          const t = event.renderTime;
                          const top = (t.start.getHours() * 60) + t.start.getMinutes();
                          const height = ((t.end.getHours() * 60) + t.end.getMinutes()) - top;
                          
                          const isSyncConflict = event.requires_review || event.has_drifted;
                          const isOverlap = event.isOverlapping;
                          const isConflict = isSyncConflict || isOverlap;
                          const isGhost = event.is_ghost;
                          const isCompleted = event.completion_status === 'completed';
                          const isMissed = event.completion_status === 'missed';
                          const hasTravel = (event.travel_time || 0) > 0;
                          
                          const catClass = getCategoryClass(event.category);
                          
                          let bgStyle = "var(--cat-bg)";
                          let borderStyle = "1px solid var(--cat-border)";
                          let textStyle = "var(--cat-text)";

                          if (isConflict) {
                            bgStyle = "var(--color-danger-bg)";
                            borderStyle = "1px solid var(--color-danger)";
                            textStyle = "var(--color-danger)";
                          } else if (isCompleted) {
                            bgStyle = "var(--color-success-bg)";
                            borderStyle = "1px solid var(--color-success)";
                            textStyle = "var(--color-success)";
                          } else if (isMissed) {
                            bgStyle = "var(--color-bg-subtle)";
                            borderStyle = "1px dashed var(--color-border)";
                            textStyle = "var(--color-text-muted)";
                          }
                          
                          const widthPct = 92 / event.totalCols;
                          const leftPct = 4 + (event.colIdx * widthPct);

                          return (
                            <div key={`${event.id}-${day.toDateString()}-${idx}`}>
                              {hasTravel && (
                                <div
                                  className="absolute w-[92%] left-[4%] rounded-t-md opacity-60 flex items-center justify-center overflow-hidden z-10 transition-colors duration-500"
                                  style={{
                                    top: `${top - event.travel_time!}px`,
                                    height: `${event.travel_time}px`,
                                    width: `${widthPct}%`,
                                    left: `${leftPct}%`,
                                    backgroundImage: `repeating-linear-gradient(45deg, var(--color-border) 25%, transparent 25%, transparent 75%, var(--color-border) 75%, var(--color-border)), repeating-linear-gradient(45deg, var(--color-border) 25%, var(--color-bg-base) 25%, var(--color-bg-base) 75%, var(--color-border) 75%, var(--color-border))`,
                                    backgroundPosition: `0 0, 8px 8px`,
                                    backgroundSize: `16px 16px`
                                  }}
                                >
                                  {event.travel_time! >= 15 && (
                                    <span className="text-[8px] font-bold px-1 rounded shadow-sm transition-colors duration-200" style={{ background: 'var(--color-bg-glass-strong)', color: 'var(--color-text-secondary)' }}>
                                      {event.travel_time}m travel
                                    </span>
                                  )}
                                </div>
                              )}

                              <div
                                onClick={() => { 
                                  if (!isPreviewMode) {
                                    const overlaps = isOverlap ? processedEvents.filter(e => e.isOverlapping && e.id !== event.id && (e.renderTime.start < t.end && e.renderTime.end > t.start)) : [];
                                    onEventClick(event, day, overlaps);
                                  } 
                                }}
                                className={`absolute p-1.5 shadow-sm flex flex-col border-l-[3px] overflow-hidden transition-all duration-200 ${!isPreviewMode ? 'cursor-pointer' : ''} ${hasTravel ? 'rounded-b-md rounded-tr-md' : 'rounded-md'} ${catClass} z-20`}
                                style={{ 
                                  top: `${top}px`, 
                                  height: `${Math.max(height, 20)}px`, 
                                  width: `${widthPct}%`, 
                                  left: `${leftPct}%`,
                                  background: bgStyle,
                                  border: borderStyle,
                                  color: textStyle,
                                  borderLeftColor: textStyle,
                                  zIndex: isConflict ? 30 : 20 
                                }}
                              >
                                <div className="flex items-start gap-1">
                                  {isGhost ? (
                                    <svg className="w-3 h-3 flex-shrink-0 mt-0.5" style={{ color: textStyle }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                                    </svg>
                                  ) : isCompleted ? (
                                    <svg className="w-3 h-3 flex-shrink-0 mt-0.5" style={{ color: textStyle }} fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                                  ) : event.is_locked ? (
                                    <svg className="w-3 h-3 flex-shrink-0 mt-0.5" style={{ color: textStyle }} fill="currentColor" viewBox="0 0 20 20">
                                      <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
                                    </svg>
                                  ) : null}
                                  <span className={`text-[9px] sm:text-[10px] font-semibold truncate leading-tight ${isMissed ? 'line-through opacity-80' : ''}`}>
                                    {event.title}
                                  </span>
                                </div>
                                
                                {isConflict && height > 40 && (
                                  <span className="text-[8px] font-bold uppercase mt-0.5 tracking-wider transition-colors duration-200" style={{ color: 'var(--color-danger)' }}>
                                    {isOverlap ? "Overlap" : "Review"}
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}