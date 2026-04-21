"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import NavigationBar from "@/components/NavigationBar";
import CustomCalendar from "@/components/CustomCalendar";
import { fetchWithRetry } from "@/lib/fetchUtils";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

// ─── CSS Animations ───────────────────────────────────────────────
const AnimationsLoader = () => (
  <style>{`
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(20px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes shimmer {
      0%   { background-position: -200% center; }
      100% { background-position: 200% center; }
    }
    @keyframes countUp {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .card-reveal { animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both; }
    .card-reveal:nth-child(1) { animation-delay: 0.05s; }
    .card-reveal:nth-child(2) { animation-delay: 0.10s; }
    .card-reveal:nth-child(3) { animation-delay: 0.15s; }
    .card-reveal:nth-child(4) { animation-delay: 0.20s; }
    .card-reveal:nth-child(5) { animation-delay: 0.25s; }
    
    .shine {
      background-image: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.6) 50%, transparent 60%);
      background-size: 200% 100%;
      animation: shimmer 3s infinite;
    }
    .dark .shine {
      background-image: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.05) 50%, transparent 60%);
    }
    
    .risk-bar { transition: width 1.2s cubic-bezier(0.16, 1, 0.3, 1); }
    .count-in { animation: countUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both; }
  `}</style>
);

interface TrendData {
  date: string;
  tasks: number;
  events: number;
}

interface CategoryStat {
  scheduled: number;
  completed: number;
}

interface DashboardData {
  core_ledgers: { active_debt_mins: number; sunk_debt_mins: number; time_refunded_mins: number };
  procrastination_profile: any[];
  risk_forecast: { average_risk_score: number; danger_zone: any[] };
  energy_analytics: { high: number; medium: number; low: number };
  completion_funnel: { task_completion_rate: number; event_completion_rate: number; routine_adherence: number; trend_data: TrendData[] };
  advanced_metrics: {
    priority_alignment: { high: number; medium: number; low: number };
    peak_action_window: { peak_hour: number; distribution: number[] };
    task_friction_hours: number;
    category_stats: Record<string, CategoryStat>;
  };
}

// ─── Utilities ───────────────────────────────────────────────────
const formatTime = (mins: number) => {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
};

const formatFriction = (hours: number) => {
  if (hours < 24) return `${hours} hrs`;
  const d = Math.floor(hours / 24);
  return `${d} days`;
};

const formatHour = (hour: number) => {
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const h = hour % 12 || 12;
  return `${h} ${ampm}`;
};

const riskColor = (score: number) => {
  if (score >= 65) return "var(--color-danger)"; 
  if (score >= 35) return "var(--color-warning)"; 
  return "var(--color-success)"; 
};

const describeArc = (cx: number, cy: number, r: number, startDeg: number, endDeg: number) => {
  const rad = (d: number) => (d * Math.PI) / 180;
  const x1 = cx + r * Math.cos(rad(startDeg));
  const y1 = cy + r * Math.sin(rad(startDeg));
  const x2 = cx + r * Math.cos(rad(endDeg));
  const y2 = cy + r * Math.sin(rad(endDeg));
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
};

// ─── Dual-Theme Glass Components ─────────────────────────────────
function StatCard({ label, value, sub, accent, delay = 0 }: any) {
  return (
    <div
      className="card-reveal shine relative overflow-hidden rounded-2xl p-5 transition-all duration-500"
      style={{
        animationDelay: `${delay}s`,
        background: "var(--color-bg-glass)",
        border: "1px solid var(--color-border)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div
        className="absolute -top-8 -right-8 w-28 h-28 rounded-full blur-2xl pointer-events-none transition-colors duration-500"
        style={{ background: accent, opacity: 0.15 }}
      />
      <p className="text-[10px] tracking-widest uppercase font-bold mb-2 transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>{label}</p>
      <p className="text-3xl font-black count-in transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>{value}</p>
      <p className="text-[11px] font-semibold mt-1 transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>{sub}</p>
    </div>
  );
}

function SectionLabel({ children, badge }: any) {
  return (
    <div className="flex items-center justify-between mb-5">
      <span className="text-xs tracking-widest uppercase font-bold transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>{children}</span>
      {badge && (
        <span 
          className="px-2 py-1 text-[9px] font-bold rounded uppercase tracking-wider transition-colors duration-200"
          style={{ background: "var(--color-accent-glow)", color: "var(--color-accent-primary)" }}
        >
          {badge}
        </span>
      )}
    </div>
  );
}

function GlassCard({ children, className = "", delay = 0 }: any) {
  return (
    <div
      className={`card-reveal rounded-3xl p-6 transition-all duration-500 ${className}`}
      style={{
        animationDelay: `${delay}s`,
        background: "var(--color-bg-glass)",
        border: "1px solid var(--color-border)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        boxShadow: "var(--shadow-md), var(--shadow-inner-glow)",
      }}
    >
      {children}
    </div>
  );
}

// ─── Visualizations ──────────────────────────────────────────────
function RiskGauge({ score }: { score: number }) {
  const clamp = Math.min(Math.max(score, 0), 100);
  const startAngle = 150;
  const totalSweep = 240;
  const endAngle = startAngle + (clamp / 100) * totalSweep;
  const color = riskColor(clamp);

  return (
    <div className="relative flex flex-col items-center">
      <svg viewBox="0 0 120 80" className="w-full max-w-[220px]">
        <path d={describeArc(60, 60, 36, 150, 390)} fill="none" stroke="var(--color-border-subtle)" strokeWidth="8" strokeLinecap="round" className="transition-colors duration-500" />
        {clamp > 0 && (
          <path d={describeArc(60, 60, 36, 150, endAngle)} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" style={{ transition: "all 1.2s cubic-bezier(0.16, 1, 0.3, 1)" }} />
        )}
        {[0, 25, 50, 75, 100].map((v) => {
          const angle = 150 + (v / 100) * 240;
          const rad = (angle * Math.PI) / 180;
          return <line key={v} x1={60 + 29 * Math.cos(rad)} y1={60 + 29 * Math.sin(rad)} x2={60 + 25 * Math.cos(rad)} y2={60 + 25 * Math.sin(rad)} stroke="var(--color-border-accent)" strokeWidth="1.5" strokeLinecap="round" className="transition-colors duration-500" />;
        })}
      </svg>
      <div className="absolute bottom-0 flex flex-col items-center" style={{ bottom: "0px" }}>
        <span className="text-4xl font-black leading-none transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>{clamp}%</span>
        <span className="text-[9px] font-bold tracking-widest uppercase mt-1 transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>avg failure risk</span>
      </div>
    </div>
  );
}

function EnergyDonut({ high, medium, low }: { high: number; medium: number; low: number }) {
  const total = high + medium + low || 1;
  const r = 16;
  const c = 2 * Math.PI * r;
  const highP = (high / total) * c;
  const medP = (medium / total) * c;

  const segments = [
    { val: high, color: "var(--color-danger)", offset: 0, label: "High" },
    { val: medium, color: "var(--color-warning)", offset: highP, label: "Medium" },
    { val: low, color: "var(--color-success)", offset: highP + medP, label: "Low" },
  ];

  return (
    <div className="flex flex-col items-center gap-6 w-full">
      <div className="relative flex-shrink-0">
        <svg viewBox="0 0 42 42" className="w-28 h-28 -rotate-90">
          <circle cx="21" cy="21" r={r} fill="transparent" stroke="var(--color-border-subtle)" strokeWidth="5" className="transition-colors duration-500" />
          {segments.map((s, i) => (
            <circle key={i} cx="21" cy="21" r={r} fill="transparent" stroke={s.color} strokeWidth="5" strokeDasharray={`${(s.val / total) * c} ${c - (s.val / total) * c}`} strokeDashoffset={-s.offset} style={{ transition: "stroke-dasharray 1s ease" }} />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-black transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>{total}</span>
          <span className="text-[8px] font-bold tracking-widest uppercase transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>tasks</span>
        </div>
      </div>
      <div className="flex justify-between w-full text-xs font-bold uppercase px-2 transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>
        {segments.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }}></div> {s.label}</span>
        ))}
      </div>
    </div>
  );
}

// ─── NEW: Interactive Dual-Color Stacked Bar Chart ────────────────
function InteractiveTrendChart({ data }: { data: TrendData[] }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  
  // Find the highest combined total to scale the chart properly
  const max = Math.max(...data.map(d => d.tasks + d.events), 5);

  return (
    <div className="relative w-full h-44 flex items-end justify-between gap-1 sm:gap-3 mt-4 px-1">
      {data.map((d, i) => {
        const total = d.tasks + d.events;
        const taskPct = total === 0 ? 0 : (d.tasks / total);
        const heightPct = Math.max((total / max) * 100, 4); // 4% minimum height so empty days show a tiny bump

        return (
          <div 
            key={i} 
            onMouseEnter={() => setActiveIndex(i)}
            onMouseLeave={() => setActiveIndex(null)}
            onClick={() => setActiveIndex(activeIndex === i ? null : i)}
            className="flex-1 flex flex-col items-center justify-end h-full relative cursor-pointer group"
          >
            {/* Interactive Tooltip */}
            <div 
              className={`absolute -top-14 z-20 flex flex-col items-center transition-all duration-200 ${activeIndex === i ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none'}`}
            >
              <div 
                className="px-3 py-2 rounded-xl shadow-lg flex flex-col gap-1 min-w-[80px]"
                style={{ background: "var(--color-bg-glass-strong)", border: "1px solid var(--color-border)", backdropFilter: "blur(12px)" }}
              >
                <div className="flex justify-between items-center text-[10px] font-bold">
                  <span style={{ color: "var(--color-accent-primary)" }}>Tasks</span>
                  <span style={{ color: "var(--color-text-primary)" }}>{d.tasks}</span>
                </div>
                <div className="flex justify-between items-center text-[10px] font-bold">
                  <span style={{ color: "var(--color-info)" }}>Events</span>
                  <span style={{ color: "var(--color-text-primary)" }}>{d.events}</span>
                </div>
              </div>
              <div className="w-2 h-2 rotate-45 -mt-1" style={{ background: "var(--color-bg-glass-strong)", borderBottom: "1px solid var(--color-border)", borderRight: "1px solid var(--color-border)" }} />
            </div>

            {/* Stacked Bar container */}
            <div 
              className={`w-full max-w-[32px] relative transition-all duration-300 ease-out overflow-hidden ${activeIndex === i ? 'brightness-125 scale-y-[1.02]' : 'group-hover:brightness-110'}`} 
              style={{ 
                height: `${heightPct}%`, 
                background: total === 0 ? "var(--color-bg-subtle)" : "transparent",
                borderRadius: "6px"
              }}
            >
              {total > 0 && (
                <>
                  {/* Events Section (Top - Cyan/Info) */}
                  <div 
                    className="absolute top-0 left-0 w-full transition-all duration-500" 
                    style={{ height: `${(1 - taskPct) * 100}%`, background: "var(--color-info)" }}
                  />
                  {/* Tasks Section (Bottom - Indigo/Primary) */}
                  <div 
                    className="absolute bottom-0 left-0 w-full transition-all duration-500" 
                    style={{ height: `${taskPct * 100}%`, background: "var(--color-accent-primary)" }}
                  />
                </>
              )}
            </div>
            
            {/* Day Label */}
            <span className="text-[9px] font-bold uppercase tracking-widest mt-3 transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>
              {new Date(d.date).toLocaleDateString("en-US", { weekday: "short" })}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── NEW: Category Progress Stats ──────────────────────────────────
function CategoryStatsLine({ category, scheduled, completed }: { category: string; scheduled: number; completed: number }) {
  const isComplete = scheduled > 0 && completed >= scheduled;
  const progressPct = scheduled === 0 ? 0 : Math.min((completed / scheduled) * 100, 100);
  
  // Dynamic color: Green if finished, Indigo if in progress, Gray if zero
  const barColor = isComplete ? "var(--color-success)" : scheduled === 0 ? "var(--color-border-subtle)" : "var(--color-accent-primary)";
  
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-end">
        <span className="text-[11px] font-bold uppercase tracking-widest transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>
          {category.replace("_", " ")}
        </span>
        <div className="flex items-baseline gap-1">
          <span className="text-sm font-black transition-colors duration-200" style={{ color: barColor }}>{completed}</span>
          <span className="text-[10px] font-bold transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>/ {scheduled}</span>
        </div>
      </div>
      <div className="h-1.5 w-full rounded-full overflow-hidden transition-colors duration-500" style={{ background: "var(--color-border-subtle)" }}>
        <div 
          className="h-full rounded-full risk-bar transition-all duration-500" 
          style={{ width: `${progressPct}%`, background: barColor }} 
        />
      </div>
    </div>
  );
}


// ─── Main Page ───────────────────────────────────────────────────
export default function AnalyticsPage() {
  const { user, loading: authLoading } = useAuth();
  const userId = user?.uid || null;

  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  // --- CALENDAR PREVIEW STATE ---
  const [isPreviewMode, setIsPreviewMode] = useState(false);
  const [isGeneratingSchedule, setIsGeneratingSchedule] = useState(false);
  const [isOptimising, setIsOptimising] = useState(false);
  const [previewToggle, setPreviewToggle] = useState<"original" | "optimised">("optimised");
  const [originalEvents, setOriginalEvents] = useState<any[]>([]);
  const [previewEvents, setPreviewEvents] = useState<any[]>([]);

  useEffect(() => {
    if (!authLoading && userId) fetchDashboard(userId);
  }, [userId, authLoading]);

  const fetchDashboard = async (uid: string) => {
    setIsLoading(true);
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/analytics/dashboard/${uid}`);
      if (res.ok) setData(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  // --- CALENDAR PREVIEW HANDLERS ---
  const handleReclaimTime = async () => {
    if (!userId) return;
    setIsGeneratingSchedule(true);
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/calendar/reschedule_debt/preview`, { 
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }) 
      });
      if (res.ok) {
        const payload = await res.json();
        setOriginalEvents(payload.original_events || []);
        setPreviewEvents(payload.preview_events || []);
        setPreviewToggle("optimised");
        setIsPreviewMode(true);
      }
    } catch (e) {
      console.error("Preview generation failed:", e);
    } finally {
      setIsGeneratingSchedule(false);
    }
  };

  const discardOptimisation = () => {
    setPreviewEvents([]);
    setOriginalEvents([]);
    setIsPreviewMode(false);
  };

  const acceptOptimisation = async () => {
    if (!userId) return;
    setIsOptimising(true);
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/calendar/reschedule_debt/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          events: previewEvents,
        }),
      });

      if (res.ok) {
        setIsPreviewMode(false);
        setPreviewEvents([]);
        setOriginalEvents([]);
        await fetchDashboard(userId); // Refresh analytics scores!
      }
    } catch (error) {
      console.error("Commit failed:", error);
    } finally {
      setIsOptimising(false);
    }
  };


  if (isLoading || !data) {
    return (
      <>
        <AnimationsLoader />
        <div className="min-h-screen flex flex-col items-center justify-center font-sans transition-colors duration-500" style={{ background: "var(--color-bg-base)" }}>
          <div className="w-8 h-8 border-4 border-t-transparent rounded-full animate-spin mb-4" style={{ borderColor: "var(--color-border-accent)", borderTopColor: "var(--color-accent-primary)" }}></div>
          <p className="text-xs tracking-widest uppercase font-bold animate-pulse transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>Analysing Behaviour</p>
        </div>
      </>
    );
  }

  // --- RENDER CALENDAR PREVIEW ---
  if (isPreviewMode) {
    return (
      <div className="h-screen w-screen flex flex-col overflow-hidden relative transition-colors duration-500" style={{ background: "var(--color-bg-base)", color: "var(--color-text-primary)" }}>
        <div 
          className="absolute top-4 left-1/2 -translate-x-1/2 z-[60] rounded-full shadow-lg p-1.5 flex items-center gap-1 animate-in slide-in-from-top-4 transition-all duration-500"
          style={{ background: "var(--color-bg-glass-strong)", backdropFilter: "blur(12px)", border: "1px solid var(--color-border)" }}
        >
          <button 
            onClick={() => setPreviewToggle("original")} 
            className="px-4 py-1.5 rounded-full text-sm font-medium transition-colors"
            style={previewToggle === "original" ? { background: "var(--color-surface)", color: "var(--color-text-primary)", boxShadow: "var(--shadow-sm)" } : { color: "var(--color-text-secondary)" }}
          >
            Original
          </button>
          <button 
            onClick={() => setPreviewToggle("optimised")} 
            className="px-4 py-1.5 rounded-full text-sm font-medium transition-colors"
            style={previewToggle === "optimised" ? { background: "var(--color-accent-glow)", color: "var(--color-accent-primary)", boxShadow: "var(--shadow-sm)" } : { color: "var(--color-text-secondary)" }}
          >
            Reclaimed Plan
          </button>
        </div>

        <div className="flex-1 overflow-hidden relative">
          <CustomCalendar
            events={previewToggle === "optimised" ? previewEvents : originalEvents}
            onEventClick={() => {}}
            onSync={() => {}}
            isSyncing={false}
            onOptimise={() => {}}
            isPreviewMode={true}
          />
        </div>

        <div 
          className="fixed bottom-0 left-0 w-full p-4 sm:px-6 pb-[env(safe-area-inset-bottom,16px)] z-[60] flex flex-col sm:flex-row items-center justify-between gap-4 animate-in slide-in-from-bottom-8 transition-colors duration-500"
          style={{ background: "var(--color-bg-glass-strong)", backdropFilter: "blur(20px)", borderTop: "1px solid var(--color-border)" }}
        >
          <div className="text-center sm:text-left">
            <h3 className="text-base font-semibold transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>Review Reclaimed Time</h3>
            <p className="text-sm transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>The AI has found slots for your missed tasks.</p>
          </div>
          <div className="flex items-center justify-center gap-3 w-full sm:w-auto">
            <button onClick={discardOptimisation} className="flex-1 sm:flex-none px-6 py-2.5 font-medium rounded-xl transition-colors btn-secondary">
              Discard
            </button>
            <button onClick={acceptOptimisation} disabled={isOptimising} className="flex-1 sm:flex-none px-6 py-2.5 font-medium rounded-xl transition-colors disabled:opacity-50 btn-primary">
              {isOptimising ? "Applying..." : "Accept Changes"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const { core_ledgers, procrastination_profile, risk_forecast, energy_analytics, completion_funnel, advanced_metrics } = data;
  const maxSnooze = Math.max(...procrastination_profile.map((t) => t.snooze_count || 0), 1);
  const totalPriority = advanced_metrics.priority_alignment.high + advanced_metrics.priority_alignment.medium + advanced_metrics.priority_alignment.low || 1;

  // Ensure category_stats exists as an object even if backend returned empty
  const categoryStats = advanced_metrics.category_stats || {};
  const sortedCategories = Object.entries(categoryStats).sort((a, b) => b[1].scheduled - a[1].scheduled);

  return (
    <>
      <AnimationsLoader />
      {/* THE FIX: Increased padding-bottom to pb-36 to guarantee clearance 
        above the mobile Navigation Bar. 
      */}
      <div className="min-h-screen font-sans pb-36 relative transition-colors duration-500" style={{ background: "var(--color-bg-base)" }}>

        {/* Standardised Sticky Header */}
        <div className="sticky top-0 z-30 transition-all duration-300" style={{ background: 'var(--color-bg-glass-strong)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', borderBottom: '1px solid var(--color-border)' }}>
          <div className="px-4 sm:px-6 lg:px-8 max-w-6xl mx-auto pt-[calc(env(safe-area-inset-top,24px)+24px)] pb-4 flex items-center justify-between gap-4 transition-colors duration-500">
            <div>
              <h1 className="text-3xl font-bold tracking-tight transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>Analytics</h1>
              <p className="text-sm font-semibold mt-1 transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Behavioral intelligence & risk prediction</p>
            </div>

            {/* Mobile: icon-only */}
            <button
              onClick={handleReclaimTime}
              disabled={isGeneratingSchedule || core_ledgers.active_debt_mins === 0}
              className="sm:hidden p-2.5 rounded-xl transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed btn-primary"
            >
              {isGeneratingSchedule ? (
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
              )}
            </button>
            {/* Desktop: full text */}
            <button
              onClick={handleReclaimTime}
              disabled={isGeneratingSchedule || core_ledgers.active_debt_mins === 0}
              className="hidden sm:flex items-center justify-center gap-2.5 px-6 py-2.5 rounded-xl text-sm font-bold transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed btn-primary"
            >
              {isGeneratingSchedule ? (
                <span className="tracking-widest animate-pulse">Analysing...</span>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  Reclaim {formatTime(core_ledgers.active_debt_mins)}
                </>
              )}
            </button>
          </div>
        </div>

        <div className="relative z-10 px-4 sm:px-6 lg:px-8 max-w-6xl mx-auto pt-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <StatCard label="Active Debt" value={formatTime(core_ledgers.active_debt_mins)} sub="Unscheduled rollover tasks" accent="var(--color-accent-primary)" delay={0.1} />
            <StatCard label="Sunk Debt" value={formatTime(core_ledgers.sunk_debt_mins)} sub="Permanently missed routines" accent="var(--color-danger)" delay={0.15} />
            <StatCard label="Refunded" value={formatTime(core_ledgers.time_refunded_mins)} sub="Successfully paid back" accent="var(--color-success)" delay={0.2} />
          </div>

          {/* Top Funnel Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <GlassCard delay={0.2} className="flex flex-col justify-center py-4">
              <SectionLabel>Task Friction</SectionLabel>
              <div className="mt-auto">
                <p className="text-[10px] font-bold uppercase mb-1 transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>Avg. creation to completion</p>
                <p className="text-2xl font-black transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>{formatFriction(advanced_metrics.task_friction_hours)}</p>
              </div>
            </GlassCard>

            <GlassCard delay={0.25} className="flex flex-col justify-center py-4">
              <SectionLabel>Peak Focus</SectionLabel>
              <div className="mt-auto flex items-end justify-between h-8 gap-0.5 mb-2">
                {advanced_metrics.peak_action_window.distribution.map((count, hr) => (
                  <div key={hr} className="w-full relative flex justify-center">
                    <div 
                      className="w-full rounded-t-sm transition-all duration-500" 
                      style={{ 
                        height: `${Math.max((count / Math.max(...advanced_metrics.peak_action_window.distribution, 1)) * 100, 10)}%`,
                        background: hr === advanced_metrics.peak_action_window.peak_hour ? "var(--color-accent-primary)" : "var(--color-border-accent)" 
                      }}
                    ></div>
                  </div>
                ))}
              </div>
              <div className="flex justify-between items-end">
                <p className="text-[10px] font-bold uppercase transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>Most productive hour</p>
                <p className="text-lg font-black transition-colors duration-200" style={{ color: "var(--color-accent-primary)" }}>{formatHour(advanced_metrics.peak_action_window.peak_hour)}</p>
              </div>
            </GlassCard>

            <GlassCard delay={0.3} className="flex flex-col justify-center py-4">
              <SectionLabel>Priority Alignment</SectionLabel>
              <div className="mt-auto">
                <div className="flex w-full h-2.5 rounded-full overflow-hidden mb-2 transition-colors duration-500" style={{ background: "var(--color-border-subtle)" }}>
                  <div style={{ width: `${(advanced_metrics.priority_alignment.high / totalPriority) * 100}%`, background: "var(--color-accent-primary)" }} className="h-full risk-bar transition-colors duration-500"></div>
                  <div style={{ width: `${(advanced_metrics.priority_alignment.medium / totalPriority) * 100}%`, background: "var(--color-text-muted)" }} className="h-full risk-bar transition-colors duration-500"></div>
                  <div style={{ width: `${(advanced_metrics.priority_alignment.low / totalPriority) * 100}%`, background: "var(--color-danger)" }} className="h-full risk-bar transition-colors duration-500"></div>
                </div>
                <div className="flex justify-between text-[9px] font-black uppercase transition-colors duration-200">
                  <span style={{ color: "var(--color-accent-primary)" }}>P1-P2 ({advanced_metrics.priority_alignment.high})</span>
                  <span style={{ color: "var(--color-text-muted)" }}>P3 ({advanced_metrics.priority_alignment.medium})</span>
                  <span style={{ color: "var(--color-danger)" }}>P4-P5 ({advanced_metrics.priority_alignment.low})</span>
                </div>
              </div>
            </GlassCard>
          </div>

          <GlassCard className="mb-6" delay={0.35}>
            <SectionLabel badge="AI Powered">Risk Forecast</SectionLabel>
            <div className="flex flex-col lg:flex-row gap-8">
              <div className="flex flex-col items-center justify-center lg:w-64 flex-shrink-0">
                <RiskGauge score={risk_forecast.average_risk_score} />
              </div>
              <div className="flex-1 flex flex-col gap-3">
                {risk_forecast.danger_zone.length === 0 ? (
                  <div 
                    className="flex-1 flex flex-col items-center justify-center py-10 rounded-xl border transition-colors duration-500"
                    style={{ background: "var(--color-bg-subtle)", borderColor: "var(--color-border-subtle)" }}
                  >
                    <span className="text-2xl mb-2 transition-colors duration-200" style={{ color: "var(--color-success)" }}>✦</span>
                    <p className="text-sm font-bold transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>No high-risk tasks</p>
                    <p className="text-[10px] font-bold uppercase tracking-widest mt-1 transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>schedule is secure</p>
                  </div>
                ) : (
                  risk_forecast.danger_zone.map((task: any, idx: number) => {
                    const score = task.risk_score || 0;
                    const col = riskColor(score);
                    return (
                      <div 
                        key={task.id || idx} 
                        className="rounded-xl p-4 relative overflow-hidden border shadow-sm transition-colors duration-500" 
                        style={{ background: "var(--color-bg-subtle)", borderColor: "var(--color-border)" }}
                      >
                        <div className="absolute inset-0 opacity-[0.05] risk-bar" style={{ width: `${score}%`, background: col, pointerEvents: "none" }} />
                        <div className="relative flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-bold truncate mb-2 transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>{task.title}</p>
                            <div className="space-y-1">
                              {task.ai_explanations?.slice(0, 2).map((exp: any, i: number) => (
                                <div key={i} className="flex items-center gap-1.5">
                                  <span className="text-[9px] font-black" style={{ color: exp.direction === "increases_risk" ? "var(--color-danger)" : "var(--color-success)" }}>
                                    {exp.direction === "increases_risk" ? "↑" : "↓"}
                                  </span>
                                  <span className="text-[10px] font-bold transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>{exp.explanation}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                          <div 
                            className="flex-shrink-0 flex flex-col items-end px-2 py-1 rounded border transition-colors duration-500"
                            style={{ background: "var(--color-surface)", borderColor: "var(--color-border-subtle)" }}
                          >
                            <span className="text-lg font-black transition-colors duration-200" style={{ color: col }}>{score}%</span>
                            <span className="text-[8px] font-black tracking-widest uppercase transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>risk</span>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </GlassCard>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            
            {/* The Funnel With 3 Elements Now */}
            <GlassCard delay={0.4} className="flex flex-col justify-center">
              <SectionLabel>Completion Funnel</SectionLabel>
              <div className="space-y-6 mt-2">
                {/* Tasks */}
                <div>
                  <div className="flex justify-between items-baseline mb-1.5">
                    <span className="text-[10px] font-bold uppercase transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Tasks</span>
                    <span className="text-lg font-black transition-colors duration-200" style={{ color: "var(--color-accent-primary)" }}>{Math.round(completion_funnel.task_completion_rate)}%</span>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden transition-colors duration-500" style={{ background: "var(--color-border-subtle)" }}>
                    <div className="h-full rounded-full risk-bar transition-colors duration-500" style={{ width: `${completion_funnel.task_completion_rate}%`, background: "var(--color-accent-primary)" }} />
                  </div>
                </div>
                {/* Events */}
                <div>
                  <div className="flex justify-between items-baseline mb-1.5">
                    <span className="text-[10px] font-bold uppercase transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Events</span>
                    <span className="text-lg font-black transition-colors duration-200" style={{ color: "var(--color-info)" }}>{Math.round(completion_funnel.event_completion_rate)}%</span>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden transition-colors duration-500" style={{ background: "var(--color-border-subtle)" }}>
                    <div className="h-full rounded-full risk-bar transition-colors duration-500" style={{ width: `${completion_funnel.event_completion_rate}%`, background: "var(--color-info)" }} />
                  </div>
                </div>
                {/* Routines */}
                <div>
                  <div className="flex justify-between items-baseline mb-1.5">
                    <span className="text-[10px] font-bold uppercase transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Routines</span>
                    <span className="text-lg font-black transition-colors duration-200" style={{ color: "var(--color-success)" }}>{Math.round(completion_funnel.routine_adherence)}%</span>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden transition-colors duration-500" style={{ background: "var(--color-border-subtle)" }}>
                    <div className="h-full rounded-full risk-bar transition-colors duration-500" style={{ width: `${completion_funnel.routine_adherence}%`, background: "var(--color-success)" }} />
                  </div>
                </div>
              </div>
            </GlassCard>

            {/* Event Category Tracker */}
            <GlassCard delay={0.45} className="flex flex-col">
              <SectionLabel>Category Progress</SectionLabel>
              {sortedCategories.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-2">
                  <p className="text-sm font-bold transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>No events scheduled</p>
                </div>
              ) : (
                <div className="space-y-4 mt-2 max-h-[180px] overflow-y-auto scrollbar-hide">
                  {sortedCategories.map(([cat, stats]) => (
                    <CategoryStatsLine key={cat} category={cat} scheduled={stats.scheduled} completed={stats.completed} />
                  ))}
                </div>
              )}
            </GlassCard>

            <GlassCard delay={0.5} className="flex flex-col">
              <SectionLabel>Avoidance Profile</SectionLabel>
              {procrastination_profile.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-2">
                  <p className="text-sm font-bold transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Zero avoidance</p>
                </div>
              ) : (
                <div className="space-y-3 mt-2">
                  {procrastination_profile.slice(0,4).map((task: any, i: number) => {
                    const pct = ((task.snooze_count || 0) / maxSnooze) * 100;
                    const colors = ["var(--color-danger)", "var(--color-warning)", "var(--color-accent-primary)", "var(--color-success)"];
                    const col = colors[i % colors.length];
                    return (
                      <div key={task.id || i}>
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-[10px] font-black w-3 flex-shrink-0 transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>{i + 1}</span>
                            <span className="text-xs font-bold truncate transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>{task.title}</span>
                          </div>
                          <div 
                            className="flex items-center gap-1 flex-shrink-0 ml-2 px-1.5 py-0.5 rounded border transition-colors duration-500"
                            style={{ background: "var(--color-surface)", borderColor: "var(--color-border-subtle)" }}
                          >
                            <span className="text-xs font-black transition-colors duration-200" style={{ color: col }}>{task.snooze_count}</span>
                            <span className="text-[8px] font-bold uppercase transition-colors duration-200" style={{ color: "var(--color-text-tertiary)" }}>snz</span>
                          </div>
                        </div>
                        <div className="h-1.5 rounded-full overflow-hidden transition-colors duration-500" style={{ background: "var(--color-border-subtle)" }}>
                          <div className="h-full rounded-full risk-bar transition-colors duration-200" style={{ width: `${pct}%`, background: col }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </GlassCard>
          </div>

          <GlassCard delay={0.55} className="mb-6">
            <SectionLabel>7-Day Completion Trend</SectionLabel>
            
            {/* Legend for the dual colors */}
            <div className="flex gap-4 mb-2 justify-end text-[10px] font-bold uppercase tracking-widest">
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full" style={{ background: "var(--color-accent-primary)" }}></div><span style={{ color: "var(--color-text-secondary)" }}>Tasks</span></div>
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full" style={{ background: "var(--color-info)" }}></div><span style={{ color: "var(--color-text-secondary)" }}>Events</span></div>
            </div>

            <InteractiveTrendChart data={completion_funnel.trend_data} />
          </GlassCard>

        </div>
        <NavigationBar />
      </div>
    </>
  );
}