"use client";

import { useState, useEffect, useRef } from "react";
import { fetchLocationPredictions } from "@/lib/places";
import { fetchWithRetry } from "@/lib/fetchUtils"; 
import { auth } from "@/lib/firebase";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export async function fetchLocationDetails(placeId: string) {
  try {
    const res = await fetchWithRetry(`${API_BASE_URL}/api/places/details?place_id=${placeId}`, {
      timeoutMs: 8000
    });
    const data = await res.json();
    return data.location || null;
  } catch (err) {
    console.error("Error fetching place details:", err);
    return null;
  }
}

export interface SubTask {
  id: string;
  title: string;
  is_completed: boolean;
}

export interface Task {
  id?: string;
  user_id?: string;
  title: string;
  description?: string;
  sub_tasks: SubTask[];
  estimated_duration?: number | null;
  start_date?: string | null;
  due_date?: string | null;
  status: string;
  priority: number;
  energy_level: string;
  tags: string[];
  linked_event_ids?: string[];
  linked_reminder_ids?: string[];
  is_locked?: boolean;
  
  // --- NEW TELEMETRY FIELDS ---
  snooze_count?: number;
  completed_at?: string | null;
  debt_applied?: boolean;
  is_perishable?: boolean;
}

export interface Reminder {
  id?: string;
  user_id?: string;
  title: string;
  body?: string | null;
  type: "event" | "task" | "standalone";
  reference_id?: string | null;
  trigger_type: "time" | "location" | "time_and_location";
  trigger_time?: string | null;
  location_data?: any | null;
  priority: "standard" | "high";
  repeat: "none" | "daily" | "weekly" | "monthly" | "custom";
  status: "pending" | "delivered" | "dismissed" | "missed";
}

export interface CapacityData {
  status: "OK" | "MODERATE" | "OVERLOADED";
  danger_count: number;
  avg_risk_score: number;
  total_pending: number;
  time_debt_mins: number;
  tasks_due_today: number;
  top_risk_tasks: { title: string; risk_score: number; risk_label: string }[];
}

interface TaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
  editTask?: Task | null;
  onSaveSuccess: () => void;
  capacityData?: CapacityData | null;
}

const CAPACITY_DISMISS_KEY = "capacity_warning_dismissed_at";
const DISMISS_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

export default function TaskModal({
  isOpen,
  onClose,
  userId,
  editTask,
  onSaveSuccess,
  capacityData,
}: TaskModalProps) {
  // --- Task States ---
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [subTasks, setSubTasks] = useState<SubTask[]>([]);
  const [newSubTask, setNewSubTask] = useState("");
  const [durationMode, setDurationMode] = useState<"flexible" | "preset" | "custom">("flexible");
  const [duration, setDuration] = useState<number | "">("");
  const [isAiEstimating, setIsAiEstimating] = useState(false);
  const [priority, setPriority] = useState(3);
  const [energyLevel, setEnergyLevel] = useState<"high" | "medium" | "low">("medium");
  const [status, setStatus] = useState("pending");
  const [startDate, setStartDate] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");

  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // --- Capacity Warning States ---
  const [warningDismissed, setWarningDismissed] = useState(false);
  const [liveRiskScore, setLiveRiskScore] = useState<number | null>(null);
  const [liveRiskLabel, setLiveRiskLabel] = useState<string | null>(null);
  const [isComputingRisk, setIsComputingRisk] = useState(false);

  // --- Telemetry States ---
  const [snoozeCount, setSnoozeCount] = useState(0);
  const [isPerishable, setIsPerishable] = useState(false);

  // --- Reminder States ---
  const [existingReminders, setExistingReminders] = useState<Reminder[]>([]);
  const [queuedLinkIds, setQueuedLinkIds] = useState<string[]>([]);
  const [pendingNewReminders, setPendingNewReminders] = useState<Reminder[]>([]);
  
  const [isAddingReminder, setIsAddingReminder] = useState(false);
  const [newRemTitle, setNewRemTitle] = useState("");
  const [newRemTriggerType, setNewRemTriggerType] = useState<"time" | "location">("time");
  const [newRemDate, setNewRemDate] = useState("");
  const [newRemTime, setNewRemTime] = useState("");
  
  // Location specific reminder states
  const [locQuery, setLocQuery] = useState("");
  const [locPredictions, setLocPredictions] = useState<any[]>([]);
  const [isLocDropdownOpen, setIsLocDropdownOpen] = useState(false);
  const [isSearchingLoc, setIsSearchingLoc] = useState(false);
  const [locLat, setLocLat] = useState("");
  const [locLng, setLocLng] = useState("");
  const [locRadius, setLocRadius] = useState<number>(100);
  const [locTriggerOn, setLocTriggerOn] = useState<"entry" | "exit">("entry");
  
  const locDropdownRef = useRef<HTMLDivElement>(null);

  // Reset warning state each time the modal opens for a NEW task
  useEffect(() => {
    if (isOpen && !editTask) {
      const dismissedAt = localStorage.getItem(CAPACITY_DISMISS_KEY);
      const stillSuppressed =
        dismissedAt && Date.now() - parseInt(dismissedAt, 10) < DISMISS_TTL_MS;
      setWarningDismissed(!!stillSuppressed);
      setLiveRiskScore(null);
      setLiveRiskLabel(null);
    }
  }, [isOpen, editTask]);

  // Live risk preview — recomputes when key form fields change (new tasks only)
  useEffect(() => {
    if (editTask || !isOpen || !capacityData || warningDismissed) return;
    if (capacityData.status === "OK") return;

    const debounce = setTimeout(async () => {
      try {
        setIsComputingRisk(true);
        const token = await auth.currentUser?.getIdToken();
        const dueDateObj = dueDate ? new Date(dueDate) : null;
        const energyMap: Record<string, number> = { low: 1, medium: 2, high: 3 };
        const payload = {
          snooze_count: 0,
          priority,
          energy_level: energyMap[energyLevel] ?? 2,
          estimated_duration:
            durationMode !== "flexible" && duration !== ""
              ? typeof duration === "string"
                ? parseInt(duration, 10) || 60
                : duration
              : 60,
          global_time_debt: capacityData.time_debt_mins,
          tasks_due_same_day: dueDateObj
            ? capacityData.tasks_due_today + 1
            : capacityData.tasks_due_today,
          days_since_created: 1,
          hour_of_due_time: dueDateObj ? dueDateObj.getHours() : new Date().getHours(),
          day_of_week: dueDateObj ? dueDateObj.getDay() : new Date().getDay(),
        };
        const res = await fetchWithRetry(`${API_BASE_URL}/api/analytics/predict_risk`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(payload),
          timeoutMs: 8000,
        });
        if (res.ok) {
          const data = await res.json();
          setLiveRiskScore(Math.round(data.risk_score * 100));
          setLiveRiskLabel(data.risk_label);
        }
      } catch {
        // silently ignore live-risk errors
      } finally {
        setIsComputingRisk(false);
      }
    }, 600);

    return () => clearTimeout(debounce);
  }, [priority, energyLevel, dueDate, duration, durationMode, editTask, isOpen, capacityData, warningDismissed]);

  const handleDismissWarning = () => {
    localStorage.setItem(CAPACITY_DISMISS_KEY, Date.now().toString());
    setWarningDismissed(true);
  };

  useEffect(() => {
    if (isOpen && userId) {
      fetchUserReminders();
      
      if (editTask) {
        setTitle(editTask.title || "");
        setDescription(editTask.description || "");
        setSubTasks(editTask.sub_tasks || []);
        
        if (editTask.estimated_duration === null || editTask.estimated_duration === undefined) {
          setDurationMode("flexible");
          setDuration("");
        } else {
          setDurationMode("custom");
          setDuration(editTask.estimated_duration);
        }
        
        setPriority(editTask.priority ?? 3);
        setEnergyLevel(editTask.energy_level as any || "medium");
        setStatus(editTask.status || "pending");
        setTags(editTask.tags || []);
        setStartDate(formatDateForInput(editTask.start_date));
        setDueDate(formatDateForInput(editTask.due_date));
        
        setSnoozeCount(editTask.snooze_count || 0);
        setIsPerishable(editTask.is_perishable || false);

      } else {
        resetForm();
      }
    }
  }, [isOpen, editTask, userId]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (locDropdownRef.current && !locDropdownRef.current.contains(event.target as Node)) {
        setIsLocDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const timer = setTimeout(async () => {
      if (locQuery.trim() && isLocDropdownOpen) {
        setIsSearchingLoc(true);
        const preds = await fetchLocationPredictions(locQuery);
        setLocPredictions(preds);
        setIsSearchingLoc(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [locQuery, isLocDropdownOpen]);

  const fetchUserReminders = async () => {
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/reminders/list/${userId}`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 8000
      });
      if (res.ok) {
        const data = await res.json();
        setExistingReminders(data.reminders || []);
      }
    } catch (error) {
      console.error("Failed to fetch reminders", error);
    }
  };

  const formatDateForInput = (isoString?: string | null) => {
    if (!isoString) return "";
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return "";
    
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    const dd = String(date.getDate()).padStart(2, "0");
    const hh = String(date.getHours()).padStart(2, "0");
    const min = String(date.getMinutes()).padStart(2, "0");

    return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
  };

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setSubTasks([]);
    setNewSubTask("");
    setDurationMode("flexible");
    setDuration("");
    setPriority(3);
    setEnergyLevel("medium");
    setStatus("pending");
    setStartDate("");
    setDueDate("");
    setTags([]);
    setNewTag("");
    setQueuedLinkIds([]);
    setPendingNewReminders([]);
    setIsAddingReminder(false);
    setSnoozeCount(0);
    setIsPerishable(false);
  };

  const handleQueueExistingReminder = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const remId = e.target.value;
    if (remId && !queuedLinkIds.includes(remId)) {
      setQueuedLinkIds([...queuedLinkIds, remId]);
    }
    e.target.value = ""; 
  };

  const handleCreatePendingReminder = () => {
    if (!newRemTitle.trim()) return;

    let trigger_time = null;
    if (newRemTriggerType === "time" && newRemDate && newRemTime) {
      trigger_time = new Date(`${newRemDate}T${newRemTime}:00`).toISOString();
    }

    let location_data = null;
    if (newRemTriggerType === "location" && locLat && locLng) {
      location_data = {
        lat: parseFloat(locLat),
        lng: parseFloat(locLng),
        radius: locRadius,
        trigger_on: locTriggerOn
      };
    }

    const newRem: Reminder = {
      user_id: userId,
      title: newRemTitle.trim(),
      type: "task",
      trigger_type: newRemTriggerType,
      trigger_time,
      location_data,
      priority: "standard",
      repeat: "none",
      status: "pending"
    };

    setPendingNewReminders([...pendingNewReminders, newRem]);
    
    setNewRemTitle("");
    setLocQuery("");
    setLocLat("");
    setLocLng("");
    setIsAddingReminder(false);
  };

  const handleAddSubTask = () => {
    if (!newSubTask.trim()) return;
    setSubTasks([...subTasks, { id: `sub_${Date.now()}`, title: newSubTask.trim(), is_completed: false }]);
    setNewSubTask("");
  };

  const handleRemoveSubTask = (id: string) => {
    setSubTasks(subTasks.filter(st => st.id !== id));
  };

  const handleToggleSubTask = (id: string) => {
    setSubTasks(subTasks.map(st => st.id === id ? { ...st, is_completed: !st.is_completed } : st));
  };

  const handleAddTag = () => {
    if (!newTag.trim() || tags.includes(newTag.trim())) return;
    setTags([...tags, newTag.trim()]);
    setNewTag("");
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter(t => t !== tagToRemove));
  };

  const handleAiEstimate = async () => {
    if (!title) return;
    setIsAiEstimating(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/tasks/estimate-duration`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ title, description }),
        timeoutMs: 12000
      });
      if (res.ok) {
        const data = await res.json();
        setDurationMode("custom");
        setDuration(data.estimated_minutes);
      } else {
        setDurationMode("custom");
        setDuration(60); 
      }
    } catch (error) {
      setDurationMode("custom");
      setDuration(60); 
    } finally {
      setIsAiEstimating(false);
    }
  };

  const handleSave = async () => {
    if (!userId || !title.trim()) return;
    setIsSaving(true);

    let finalDuration = null;
    if (durationMode !== "flexible" && duration !== "") {
      finalDuration = typeof duration === "string" ? parseInt(duration, 10) : duration;
    }

    const finalSubTasks = [...subTasks];
    if (newSubTask.trim()) {
      finalSubTasks.push({ id: `sub_${Date.now()}`, title: newSubTask.trim(), is_completed: false });
    }

    const payload: Task = {
      user_id: userId,
      title: title.trim(),
      description: description.trim(),
      sub_tasks: finalSubTasks,
      estimated_duration: finalDuration,
      start_date: startDate ? new Date(startDate).toISOString() : null,
      due_date: dueDate ? new Date(dueDate).toISOString() : null,
      priority,
      energy_level: energyLevel,
      status,
      tags,
      is_perishable: isPerishable 
    };

    try {
      const token = await auth.currentUser?.getIdToken();
      let endpoint = "/api/tasks/create";
      let method = "POST";

      if (editTask?.id) {
        endpoint = "/api/tasks/update";
        method = "PUT";
        payload.id = editTask.id;
      }

      const res = await fetchWithRetry(`${API_BASE_URL}${endpoint}`, {
        method,
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify(payload),
        timeoutMs: 10000
      });

      if (res.ok) {
        const data = await res.json();
        const finalTaskId = editTask?.id || data.task_id || data.id;

        if (finalTaskId) {
          for (const rId of queuedLinkIds) {
            await fetchWithRetry(`${API_BASE_URL}/api/reminders/update`, {
              method: "PUT",
              headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
              body: JSON.stringify({ id: rId, user_id: userId, type: "task", reference_id: finalTaskId }),
              timeoutMs: 8000
            });
          }

          for (const newRem of pendingNewReminders) {
            newRem.reference_id = finalTaskId;
            await fetchWithRetry(`${API_BASE_URL}/api/reminders/create`, {
              method: "POST",
              headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
              body: JSON.stringify(newRem),
              timeoutMs: 8000
            });
          }
        }

        onSaveSuccess();
        onClose();
      } else {
        console.error("Failed to save task", await res.text());
      }
    } catch (error) {
      console.error("Network error saving task", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!userId || !editTask?.id) return;
    setIsDeleting(true);

    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/tasks/delete`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ user_id: userId, task_id: editTask.id }),
        timeoutMs: 8000
      });

      if (res.ok) {
        onSaveSuccess();
        onClose();
      }
    } catch (error) {
      console.error("Failed to delete task", error);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!isOpen) return null;

  const activelyLinkedReminders = existingReminders.filter(r => r.reference_id === editTask?.id);
  const availableStandaloneReminders = existingReminders.filter(r => r.type === "standalone" && !queuedLinkIds.includes(r.id!));

  return (
    <div 
      className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-0 sm:p-4 font-sans animate-fadeIn transition-colors duration-500"
      style={{
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        touchAction: 'pan-y',
        overflowX: 'hidden',
      }}
      onClick={onClose} 
    >
      <div 
        className="w-full max-w-xl rounded-t-3xl sm:rounded-2xl flex flex-col max-h-[92vh] overflow-hidden animate-fadeInUp transition-colors duration-500"
        style={{
          background: 'var(--color-bg-glass-strong)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          boxShadow: 'var(--shadow-xl), var(--shadow-inner-glow)',
          border: '1px solid var(--color-border)',
        }}
        onClick={(e) => e.stopPropagation()} 
      >
        
        <div 
          className="px-6 py-5 flex justify-between items-center z-10 transition-colors duration-500"
          style={{
            background: 'var(--color-bg-subtle)',
            borderBottom: '1px solid var(--color-border)',
          }}
        >
          <button type="button" onClick={onClose} className="text-sm font-medium transition-colors hover:opacity-80" style={{ color: 'var(--color-text-secondary)' }}>Cancel</button>
          <span className="font-semibold text-sm transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{editTask ? "Edit Task" : "New Task"}</span>
          <button 
            type="button"
            onClick={handleSave} 
            disabled={!title.trim() || isSaving || isDeleting} 
            className="font-semibold text-sm disabled:opacity-50 transition-colors hover:opacity-80"
            style={{ color: 'var(--color-accent-primary)' }}
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 space-y-8 scrollbar-hide">

          {/* --- Capacity Warning Banner (new tasks only) --- */}
          {!editTask && !warningDismissed && capacityData && capacityData.status !== "OK" && (
            <div
              className="rounded-2xl p-4 animate-fadeIn"
              style={{
                background:
                  capacityData.status === "OVERLOADED"
                    ? "var(--color-danger-bg)"
                    : "var(--color-warning-bg)",
                border: `1px solid ${
                  capacityData.status === "OVERLOADED"
                    ? "var(--color-danger)"
                    : "var(--color-warning)"
                }`,
              }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5 flex-1 min-w-0">
                  <svg
                    className="w-5 h-5 flex-shrink-0 mt-0.5"
                    style={{
                      color:
                        capacityData.status === "OVERLOADED"
                          ? "var(--color-danger)"
                          : "var(--color-warning)",
                    }}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
                    />
                  </svg>
                  <div className="space-y-1.5 min-w-0">
                    <p
                      className="text-sm font-bold leading-snug"
                      style={{
                        color:
                          capacityData.status === "OVERLOADED"
                            ? "var(--color-danger)"
                            : "var(--color-warning)",
                      }}
                    >
                      {capacityData.status === "OVERLOADED"
                        ? `You're at high capacity — ${capacityData.danger_count} task${capacityData.danger_count !== 1 ? "s are" : " is"} already at high risk`
                        : `Your workload is building up — ${capacityData.danger_count} task${capacityData.danger_count !== 1 ? "s need" : " needs"} attention`}
                    </p>
                    <p
                      className="text-xs leading-relaxed"
                      style={{
                        color:
                          capacityData.status === "OVERLOADED"
                            ? "var(--color-danger)"
                            : "var(--color-warning)",
                        opacity: 0.85,
                      }}
                    >
                      {capacityData.total_pending} pending tasks · avg risk{" "}
                      {capacityData.avg_risk_score}%
                      {capacityData.time_debt_mins > 0
                        ? ` · ${Math.round(capacityData.time_debt_mins / 60)}h time debt`
                        : ""}
                    </p>

                    {capacityData.top_risk_tasks.length > 0 && (
                      <div className="pt-1 space-y-1">
                        {capacityData.top_risk_tasks.map((t, i) => (
                          <div key={i} className="flex items-center justify-between gap-2">
                            <span
                              className="text-xs font-medium truncate"
                              style={{
                                color:
                                  capacityData.status === "OVERLOADED"
                                    ? "var(--color-danger)"
                                    : "var(--color-warning)",
                                opacity: 0.9,
                              }}
                            >
                              {t.title}
                            </span>
                            <span
                              className="text-[10px] font-bold uppercase tracking-wider flex-shrink-0 px-1.5 py-0.5 rounded"
                              style={{
                                background:
                                  t.risk_score >= 65
                                    ? "var(--color-danger)"
                                    : "var(--color-warning)",
                                color: "var(--color-bg-base)",
                              }}
                            >
                              {t.risk_score}%
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Live risk score for this new task */}
                    {(isComputingRisk || liveRiskScore !== null) && (
                      <div
                        className="mt-2 pt-2 flex items-center gap-2"
                        style={{
                          borderTop: `1px solid ${
                            capacityData.status === "OVERLOADED"
                              ? "var(--color-danger)"
                              : "var(--color-warning)"
                          }`,
                          opacity: 0.9,
                        }}
                      >
                        {isComputingRisk ? (
                          <span
                            className="text-xs font-medium animate-pulse"
                            style={{
                              color:
                                capacityData.status === "OVERLOADED"
                                  ? "var(--color-danger)"
                                  : "var(--color-warning)",
                            }}
                          >
                            Predicting risk for this task...
                          </span>
                        ) : (
                          <>
                            <span
                              className="text-xs font-semibold"
                              style={{
                                color:
                                  capacityData.status === "OVERLOADED"
                                    ? "var(--color-danger)"
                                    : "var(--color-warning)",
                              }}
                            >
                              This task:
                            </span>
                            <span
                              className="text-xs font-bold px-2 py-0.5 rounded"
                              style={{
                                background:
                                  liveRiskScore! >= 65
                                    ? "var(--color-danger)"
                                    : liveRiskScore! >= 35
                                    ? "var(--color-warning)"
                                    : "var(--color-success)",
                                color: "var(--color-bg-base)",
                              }}
                            >
                              {liveRiskScore}% {liveRiskLabel}
                            </span>
                            <span
                              className="text-xs"
                              style={{
                                color:
                                  capacityData.status === "OVERLOADED"
                                    ? "var(--color-danger)"
                                    : "var(--color-warning)",
                                opacity: 0.75,
                              }}
                            >
                              predicted risk
                            </span>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleDismissWarning}
                  className="flex-shrink-0 p-1 rounded-lg transition-opacity hover:opacity-70 mt-0.5"
                  style={{
                    color:
                      capacityData.status === "OVERLOADED"
                        ? "var(--color-danger)"
                        : "var(--color-warning)",
                  }}
                  aria-label="Dismiss warning"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}
          
          <div className="space-y-4">
            <input 
              type="text" 
              placeholder="Task Name" 
              className={`w-full text-2xl font-semibold border-none px-0 focus:ring-0 outline-none transition-colors duration-200 bg-transparent ${status === 'missed' ? 'line-through' : ''}`} 
              style={{ color: status === 'missed' ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <textarea 
              placeholder="Add a description or notes..." 
              rows={2}
              className="w-full text-sm border-none px-0 focus:ring-0 outline-none resize-none bg-transparent transition-colors duration-200"
              style={{ color: 'var(--color-text-secondary)' }}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Status</span>
              <div 
                className="flex p-1.5 rounded-xl w-full transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                 <button type="button" onClick={() => setStatus("pending")} className={`flex-1 px-2 sm:px-5 py-2.5 text-xs font-bold rounded-lg transition-all`} style={["pending", "scheduled", "in_progress"].includes(status) ? { background: 'var(--color-surface)', color: 'var(--color-text-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Pending</button>
                 <button type="button" onClick={() => setStatus("completed")} className={`flex-1 px-2 sm:px-5 py-2.5 text-xs font-bold rounded-lg transition-all`} style={status === "completed" ? { background: 'var(--color-success)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Completed</button>
                 <button type="button" onClick={() => setStatus("missed")} className={`flex-1 px-2 sm:px-5 py-2.5 text-xs font-bold rounded-lg transition-all`} style={status === "missed" ? { background: 'var(--color-danger)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Missed</button>
              </div>
            </div>

            {snoozeCount > 0 && (
              <div 
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg w-fit mt-2 transition-colors duration-500"
                style={{
                  background: 'var(--color-warning-bg)',
                  border: '1px solid var(--color-warning)',
                }}
              >
                <svg className="w-4 h-4" style={{ color: 'var(--color-warning)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-warning)' }}>Snoozed {snoozeCount} time{snoozeCount > 1 ? 's' : ''}</span>
              </div>
            )}
          </div>

          <div className="space-y-3">
            <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Checklist</span>
            <div className="space-y-2">
              {subTasks.map((st) => (
                <div 
                  key={st.id} 
                  className="flex items-center justify-between p-3 rounded-xl transition-colors duration-500"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    <button 
                      type="button"
                      onClick={() => handleToggleSubTask(st.id)}
                      className="flex-shrink-0 w-5 h-5 rounded-md flex items-center justify-center transition-all duration-200"
                      style={{
                        background: st.is_completed ? 'var(--color-accent-gradient)' : 'var(--color-bg-base)',
                        border: st.is_completed ? 'none' : '1px solid var(--color-border-accent)',
                        boxShadow: st.is_completed ? 'var(--shadow-sm)' : 'none',
                      }}
                    >
                      {st.is_completed && (
                        <svg className="w-3.5 h-3.5" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>
                    <span className={`text-sm truncate transition-colors duration-200 ${st.is_completed ? 'line-through' : 'font-medium'}`} style={{ color: st.is_completed ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}>
                      {st.title}
                    </span>
                  </div>
                  <button type="button" onClick={() => handleRemoveSubTask(st.id)} className="transition-colors px-2 hover:opacity-80" style={{ color: 'var(--color-danger)' }}>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
              <div className="flex gap-2">
                <input 
                  type="text" 
                  placeholder="Add an item..." 
                  className="flex-1 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                  value={newSubTask}
                  onChange={(e) => setNewSubTask(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddSubTask()}
                />
                <button 
                  type="button"
                  onClick={handleAddSubTask} 
                  disabled={!newSubTask.trim()}
                  className="px-4 rounded-xl font-semibold transition-all disabled:opacity-50 btn-secondary"
                >
                  +
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Estimated Duration</span>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setDurationMode("flexible")} className={`px-4 py-2 text-xs font-semibold uppercase tracking-wider rounded-lg transition-all`} style={durationMode === "flexible" ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { background: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}>Flexible</button>
              <button type="button" onClick={() => { setDurationMode("preset"); setDuration(15); }} className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all`} style={durationMode === "preset" && duration === 15 ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { background: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}>15m</button>
              <button type="button" onClick={() => { setDurationMode("preset"); setDuration(30); }} className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all`} style={durationMode === "preset" && duration === 30 ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { background: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}>30m</button>
              <button type="button" onClick={() => { setDurationMode("preset"); setDuration(60); }} className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all`} style={durationMode === "preset" && duration === 60 ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { background: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}>1h</button>
              <button type="button" onClick={() => { setDurationMode("custom"); setDuration(""); }} className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all`} style={durationMode === "custom" ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { background: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}>Custom</button>
              
              <button 
                type="button" 
                onClick={handleAiEstimate} 
                disabled={!title || isAiEstimating} 
                className="ml-auto flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg disabled:opacity-50 transition-all btn-primary"
              >
                {isAiEstimating ? (
                  <span className="animate-pulse">Estimating...</span>
                ) : (
                  <>
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                    </svg>
                    Ask AI
                  </>
                )}
              </button>
            </div>
            {durationMode === "custom" && (
              <input 
                type="number" 
                placeholder="Minutes (e.g. 45)" 
                className="w-full text-sm rounded-xl px-4 py-3 outline-none mt-2 transition-all input-glass"
                value={duration}
                onChange={(e) => setDuration(Number.parseInt(e.target.value) || "")}
              />
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Energy Required</span>
              <div 
                className="flex p-1 rounded-xl transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <button type="button" onClick={() => setEnergyLevel("low")} className={`flex-1 py-2 text-xs font-semibold rounded-lg capitalize transition-all`} style={energyLevel === "low" ? { background: 'var(--color-surface)', color: 'var(--color-info)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Low</button>
                <button type="button" onClick={() => setEnergyLevel("medium")} className={`flex-1 py-2 text-xs font-semibold rounded-lg capitalize transition-all`} style={energyLevel === "medium" ? { background: 'var(--color-surface)', color: 'var(--color-text-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Med</button>
                <button type="button" onClick={() => setEnergyLevel("high")} className={`flex-1 py-2 text-xs font-semibold rounded-lg capitalize transition-all`} style={energyLevel === "high" ? { background: 'var(--color-surface)', color: 'var(--color-warning)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>High</button>
              </div>
            </div>

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Priority (1-5)</span>
              <div className="flex justify-between items-center h-full pb-1 px-2">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button key={star} type="button" onClick={() => setPriority(star)} className="p-1 hover:scale-110 transition-transform">
                    <svg className="w-6 h-6 transition-colors duration-200" style={{ color: star <= priority ? 'var(--color-accent-primary)' : 'var(--color-border-accent)' }} fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4">
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Start Date</span>
              <input 
                type="datetime-local" 
                className="w-full min-w-0 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Due Date</span>
              <input 
                type="datetime-local" 
                className="w-full min-w-0 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>
          </div>
          
          <div className="flex items-center justify-between p-4 rounded-2xl transition-colors duration-500" style={{ background: 'var(--color-bg-subtle)', border: '1px solid var(--color-border)' }}>
            <div className="space-y-0.5">
              <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Routine / Habit</p>
              <p className="text-[11px] transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Skip if missed (Sunk Debt)</p>
            </div>
            <button 
              type="button"
              onClick={() => setIsPerishable(!isPerishable)} 
              className="w-11 h-6 rounded-full transition-all relative flex-shrink-0" 
              style={{ background: isPerishable ? 'var(--color-danger)' : 'var(--color-border)' }}
            >
              <div className={`absolute top-1 w-4 h-4 rounded-full shadow-sm transition-all ${isPerishable ? 'left-6' : 'left-1'}`} style={{ background: 'var(--color-bg-base)' }} />
            </button>
          </div>

          <div className="space-y-3">
            <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Tags</span>
            <div className="flex flex-wrap gap-2 mb-2">
              {tags.map((tag) => (
                <span 
                  key={tag} 
                  className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors duration-500"
                  style={{
                    background: 'var(--color-bg-subtle)',
                    color: 'var(--color-text-secondary)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  {tag}
                  <button type="button" onClick={() => handleRemoveTag(tag)} className="ml-1 transition-colors hover:opacity-80" style={{ color: 'var(--color-danger)' }}>
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input 
                type="text" 
                placeholder="Add a tag..." 
                className="flex-1 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddTag()}
              />
              <button 
                type="button"
                onClick={handleAddTag} 
                disabled={!newTag.trim()}
                className="px-4 rounded-xl font-semibold transition-all disabled:opacity-50 btn-secondary"
              >
                Add
              </button>
            </div>
          </div>

          {/* --- REMINDERS & ALERTS SECTION --- */}
          <div 
            className="space-y-4 pt-6 mt-6 transition-colors duration-500"
            style={{ borderTop: '1px solid var(--color-border-subtle)' }}
          >
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-bold uppercase tracking-widest flex items-center gap-1.5 transition-colors duration-200" style={{ color: 'var(--color-accent-primary)' }}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
                </svg>
                Reminders & Alerts
              </span>
            </div>

            {activelyLinkedReminders.length > 0 && (
              <div className="space-y-2">
                {activelyLinkedReminders.map(r => (
                  <div 
                    key={r.id} 
                    className="flex items-center justify-between px-3 py-2.5 rounded-xl transition-colors duration-500"
                    style={{
                      background: 'var(--color-bg-glass)',
                      border: '1px solid var(--color-border)',
                      boxShadow: 'var(--shadow-sm)',
                    }}
                  >
                    <span className="text-sm font-semibold truncate transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{r.title}</span>
                    <span 
                      className="text-[10px] uppercase font-bold px-2 py-0.5 rounded transition-colors duration-200"
                      style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text-secondary)' }}
                    >Active</span>
                  </div>
                ))}
              </div>
            )}

            {queuedLinkIds.length > 0 && (
              <div className="space-y-2">
                {queuedLinkIds.map(rId => {
                  const rem = existingReminders.find(x => x.id === rId);
                  return (
                    <div 
                      key={rId} 
                      className="flex items-center justify-between px-3 py-2.5 rounded-xl transition-colors duration-500"
                      style={{
                        background: 'var(--color-accent-glow)',
                        border: '1px solid var(--color-border-accent)',
                      }}
                    >
                      <span className="text-sm font-semibold truncate transition-colors duration-200" style={{ color: 'var(--color-accent-primary)' }}>{rem?.title || "Unknown Reminder"}</span>
                      <span className="text-[10px] uppercase font-bold transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Links on Save</span>
                    </div>
                  );
                })}
              </div>
            )}

            {pendingNewReminders.length > 0 && (
              <div className="space-y-2">
                {pendingNewReminders.map((r, idx) => (
                  <div 
                    key={`pending-task-rem-${idx}`} 
                    className="flex items-center justify-between px-3 py-2.5 rounded-xl transition-colors duration-500"
                    style={{
                      background: 'var(--color-success-bg)',
                      border: '1px solid var(--color-success)',
                    }}
                  >
                    <span className="text-sm font-semibold truncate transition-colors duration-200" style={{ color: 'var(--color-success)' }}>{r.title}</span>
                    <span className="text-[10px] uppercase font-bold transition-colors duration-200" style={{ color: 'var(--color-success)' }}>Creates on Save</span>
                  </div>
                ))}
              </div>
            )}

            {availableStandaloneReminders.length > 0 && (
              <select 
                onChange={handleQueueExistingReminder}
                className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all appearance-none input-glass"
                defaultValue=""
              >
                <option value="" disabled>Link an existing standalone reminder...</option>
                {availableStandaloneReminders.map(r => (
                  <option key={r.id} value={r.id}>{r.title}</option>
                ))}
              </select>
            )}

            {isAddingReminder ? (
              <div 
                className="p-4 rounded-xl space-y-4 animate-fadeIn transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-bold uppercase tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>New Alert Details</span>
                  <button type="button" onClick={() => setIsAddingReminder(false)} className="transition-colors hover:opacity-80" style={{ color: 'var(--color-danger)' }}>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
                
                <input 
                  type="text" 
                  placeholder="Reminder Title..." 
                  className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                  value={newRemTitle}
                  onChange={(e) => setNewRemTitle(e.target.value)}
                />

                <div 
                  className="flex p-1 rounded-xl transition-colors duration-500"
                  style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
                >
                  <button type="button" onClick={() => setNewRemTriggerType("time")} className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all`} style={newRemTriggerType === "time" ? { background: 'var(--color-bg-subtle)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Time</button>
                  <button type="button" onClick={() => setNewRemTriggerType("location")} className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all`} style={newRemTriggerType === "location" ? { background: 'var(--color-warning-bg)', color: 'var(--color-warning)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Location</button>
                </div>

                {newRemTriggerType === "time" ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input type="date" className="w-full min-w-0 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass" value={newRemDate} onChange={(e) => setNewRemDate(e.target.value)} />
                    <input type="time" className="w-full min-w-0 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass" value={newRemTime} onChange={(e) => setNewRemTime(e.target.value)} />
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="relative" ref={locDropdownRef}>
                      <input
                        type="text"
                        placeholder="Search location..."
                        className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                        style={{ borderColor: 'var(--color-warning)' }}
                        value={locQuery}
                        onChange={(e) => {
                          setLocQuery(e.target.value);
                          setIsLocDropdownOpen(true);
                        }}
                        onFocus={() => setIsLocDropdownOpen(true)}
                      />
                      {isLocDropdownOpen && locQuery.trim() !== "" && (
                        <div 
                          className="absolute z-50 w-full mt-1 rounded-xl max-h-32 overflow-y-auto transition-colors duration-500"
                          style={{
                            background: 'var(--color-bg-glass-strong)',
                            backdropFilter: 'blur(12px)',
                            WebkitBackdropFilter: 'blur(12px)',
                            border: '1px solid var(--color-border)',
                            boxShadow: 'var(--shadow-md)',
                          }}
                        >
                          {isSearchingLoc ? (
                            <div className="p-3 text-xs text-center transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Searching...</div>
                          ) : locPredictions.length > 0 ? (
                            locPredictions.map((pred: any) => (
                              <button
                                type="button"
                                key={pred.place_id}
                                className="w-full text-left px-4 py-2.5 transition-colors"
                                style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                                onClick={async () => {
                                  setLocQuery(pred.description);
                                  setIsLocDropdownOpen(false);
                                  setIsSearchingLoc(true);
                                  const coords = await fetchLocationDetails(pred.place_id);
                                  if (coords) {
                                    setLocLat(coords.lat.toString());
                                    setLocLng(coords.lng.toString());
                                  }
                                  setIsSearchingLoc(false);
                                }}
                              >
                                <p className="text-xs font-semibold truncate transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{pred.description}</p>
                              </button>
                            ))
                          ) : (
                            <div className="p-3 text-xs text-center transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>No places found.</div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <button 
                  type="button" 
                  onClick={handleCreatePendingReminder}
                  disabled={!newRemTitle.trim() || (newRemTriggerType === "location" && !locLat)}
                  className="w-full py-3 font-semibold rounded-xl disabled:opacity-50 transition-all text-sm btn-primary"
                >
                  Queue Alert for Save
                </button>
              </div>
            ) : (
              <button 
                type="button" 
                onClick={() => {
                  setIsAddingReminder(true);
                  setNewRemTitle(title ? `Reminder: ${title}` : "");
                  const now = new Date();
                  now.setMinutes(now.getMinutes() + 15);
                  
                  const yyyy = now.getFullYear();
                  const mm = String(now.getMonth() + 1).padStart(2, "0");
                  const dd = String(now.getDate()).padStart(2, "0");
                  const hh = String(now.getHours()).padStart(2, "0");
                  const min = String(now.getMinutes()).padStart(2, "0");
                  
                  setNewRemDate(`${yyyy}-${mm}-${dd}`);
                  setNewRemTime(`${hh}:${min}`);
                }}
                className="w-full py-3 font-semibold rounded-xl text-sm transition-all btn-ghost"
                style={{ border: '2px dashed var(--color-border-accent)' }}
              >
                + Create new alert for this task
              </button>
            )}
          </div>
        </div>

        {editTask && (
          <div 
            className="px-6 py-4 flex justify-center mt-auto transition-colors duration-500"
            style={{
              background: 'var(--color-bg-subtle)',
              borderTop: '1px solid var(--color-border-subtle)',
            }}
          >
            <button 
              type="button"
              onClick={handleDelete} 
              disabled={isDeleting || isSaving} 
              className="text-sm font-medium flex items-center gap-2 transition-colors disabled:opacity-50 hover:opacity-80"
              style={{ color: 'var(--color-danger)' }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
              </svg>
              {isDeleting ? "Deleting..." : "Delete Task"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}