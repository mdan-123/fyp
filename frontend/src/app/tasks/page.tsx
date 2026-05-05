"use client";

import { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/lib/AuthContext";
import NavigationBar from "@/components/NavigationBar";
import TaskModal, { Task, CapacityData } from "@/components/TaskModal";
import CustomCalendar from "@/components/CustomCalendar";
import { fetchWithRetry } from "@/lib/fetchUtils"; 
import { App as CapacitorApp } from '@capacitor/app'; 
import GlobalSearchModal from "@/components/GlobalSearchModal";
import { Capacitor } from '@capacitor/core';
import { auth } from "@/lib/firebase";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function TasksPage() {
  const { user, loading: authLoading } = useAuth();
  const userId = user?.uid || null;

  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  
  const [expandedTasks, setExpandedTasks] = useState<Record<string, boolean>>({});
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [sortBy, setSortBy] = useState<"dueDate_asc" | "dueDate_desc" | "priority_desc" | "duration_asc" | "duration_desc">("dueDate_asc");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [priorityFilter, setPriorityFilter] = useState<number | "all">("all");
  const [energyFilter, setEnergyFilter] = useState<string>("all");
  const [tagFilter, setTagFilter] = useState<string>("all");
  const [dateFilter, setDateFilter] = useState<string>("");

  const [capacityData, setCapacityData] = useState<CapacityData | null>(null);

  const [isPreviewMode, setIsPreviewMode] = useState(false);
  const [previewToggle, setPreviewToggle] = useState<"original" | "optimised">("optimised");
  const [originalEvents, setOriginalEvents] = useState<any[]>([]);
  const [previewEvents, setPreviewEvents] = useState<any[]>([]);
  const [isGeneratingSchedule, setIsGeneratingSchedule] = useState(false);
  const [isOptimising, setIsOptimising] = useState(false);

  useEffect(() => {
    if (!authLoading) {
      if (userId) {
        fetchTasks(userId);
      } else {
        setIsLoading(false);
      }
    }
  }, [userId, authLoading]);

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !userId) return;

    const appStateListener = CapacitorApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        fetchTasks(userId); 
      }
    });

    return () => {
      appStateListener.then(listener => listener.remove());
    };
  }, [userId]);

  const fetchTasks = async (uid: string) => {
    setIsLoading(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/tasks/list/${uid}`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 8000 
      });
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks || []);
      }
    } catch (error) {
      console.error("Failed to fetch tasks:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const availableTags = useMemo(() => {
    const tagSet = new Set<string>();
    tasks.forEach(t => t.tags?.forEach(tag => tagSet.add(tag)));
    return Array.from(tagSet).sort();
  }, [tasks]);

  const handleOpenNewTask = async () => {
    setEditingTask(null);
    setCapacityData(null);
    setIsModalOpen(true);
    // Fetch capacity in the background — modal opens immediately, warning appears once data arrives
    if (userId) {
      try {
        const token = await user?.getIdToken();
        const res = await fetchWithRetry(
          `${API_BASE_URL}/api/analytics/capacity/${userId}`,
          {
            method: "GET",
            headers: { Authorization: `Bearer ${token}` },
            timeoutMs: 8000,
          }
        );
        if (res.ok) {
          const data = await res.json();
          setCapacityData(data);
        }
      } catch {
        // silently ignore — warning just won't show
      }
    }
  };

  const handleEditTask = (task: Task) => {
    if (selectedTaskIds.length > 0) {
      toggleTaskSelection(task.id!);
      return;
    }
    setEditingTask(task);
    setIsModalOpen(true);
  };

  const handleToggleSubTaskOnline = async (taskId: string, subTaskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!userId) return;

    const taskToUpdate = tasks.find(t => t.id === taskId);
    if (!taskToUpdate) return;

    const updatedSubTasks = taskToUpdate.sub_tasks.map(st => 
      st.id === subTaskId ? { ...st, is_completed: !st.is_completed } : st
    );

    setTasks(tasks.map(t => t.id === taskId ? { ...t, sub_tasks: updatedSubTasks } : t));

    try {
      const token = await user?.getIdToken();
      await fetchWithRetry(`${API_BASE_URL}/api/tasks/update`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ ...taskToUpdate, sub_tasks: updatedSubTasks, user_id: userId }),
      });
    } catch (error) {
      console.error("Failed to update subtask", error);
    }
  };

  const toggleTaskSelection = (taskId: string) => {
    setSelectedTaskIds(prev => 
      prev.includes(taskId) ? prev.filter(id => id !== taskId) : [...prev, taskId]
    );
  };

  const clearSelection = () => setSelectedTaskIds([]);

  const handleBulkComplete = async () => {
    if (!userId || selectedTaskIds.length === 0) return;
    setIsLoading(true);
    try {
      const token = await user?.getIdToken();
      await Promise.all(selectedTaskIds.map(async (taskId) => {
        const task = tasks.find(t => t.id === taskId);
        if (!task) return;
        return fetchWithRetry(`${API_BASE_URL}/api/tasks/update`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
          body: JSON.stringify({ ...task, status: "completed", user_id: userId }),
        });
      }));
      await fetchTasks(userId);
      clearSelection();
    } catch (error) {
      console.error("Bulk complete failed", error);
      setIsLoading(false);
    }
  };

  const handleBulkMissed = async () => {
    if (!userId || selectedTaskIds.length === 0) return;
    setIsLoading(true);
    try {
      const token = await user?.getIdToken();
      await Promise.all(selectedTaskIds.map(async (taskId) => {
        const task = tasks.find(t => t.id === taskId);
        if (!task) return;
        return fetchWithRetry(`${API_BASE_URL}/api/tasks/update`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
          body: JSON.stringify({ ...task, status: "missed", user_id: userId }),
        });
      }));
      await fetchTasks(userId);
      clearSelection();
    } catch (error) {
      console.error("Bulk missed failed", error);
      setIsLoading(false);
    }
  };

  const handleBulkDelete = async () => {
    if (!userId || selectedTaskIds.length === 0) return;
    setIsLoading(true);
    try {
      const token = await user?.getIdToken();
      await Promise.all(selectedTaskIds.map(taskId => 
        fetchWithRetry(`${API_BASE_URL}/api/tasks/delete`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
          body: JSON.stringify({ user_id: userId, task_id: taskId }),
        })
      ));
      await fetchTasks(userId);
      clearSelection();
    } catch (error) {
      console.error("Bulk delete failed", error);
      setIsLoading(false);
    }
  };

  const generateTaskSchedulePreview = async (taskIdsToSchedule: string[] = []) => {
    if (!userId) return;
    setIsGeneratingSchedule(true);
    try {
      const token = await user?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/tasks/schedule/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({
          user_id: userId,
          target_date: new Date().toISOString(),
          task_ids: taskIdsToSchedule
        }),
        timeoutMs: 15000 
      });
      if (res.ok) {
        const data = await res.json();
        setOriginalEvents(data.original_events || []);
        setPreviewEvents(data.preview_events || []);
        setPreviewToggle("optimised");
        setIsPreviewMode(true);
      }
    } catch (error) {
      console.error("Scheduling preview failed", error);
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
      const token = await user?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/tasks/schedule/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({
          user_id: userId,
          events: previewEvents,
        }),
      });

      if (res.ok) {
        setIsPreviewMode(false);
        setPreviewEvents([]);
        setOriginalEvents([]);
        await fetchTasks(userId);
        clearSelection();
      } else {
        console.error("Commit returned an error status:", res.status);
      }
    } catch (error) {
      console.error("Commit failed:", error);
    } finally {
      setIsOptimising(false);
    }
  };

  const toggleTaskExpansion = (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedTasks(prev => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  const getEnergyColor = (level: string) => {
    switch (level) {
      case "high": return { bg: "var(--color-warning-bg)", text: "var(--color-warning)", border: "var(--color-warning)" };
      case "low": return { bg: "var(--color-info-bg)", text: "var(--color-info)", border: "var(--color-info)" };
      default: return { bg: "var(--color-bg-subtle)", text: "var(--color-text-secondary)", border: "var(--color-border-subtle)" };
    }
  };

  const getTaskPillTheme = (status: string, isCompletedSection: boolean) => {
    if (isCompletedSection || status === "completed") {
      return { bg: "var(--color-success-bg)", border: "var(--color-success)", opacity: 0.75 };
    }
    switch (status) {
      case "missed": return { bg: "var(--color-danger-bg)", border: "var(--color-danger)", opacity: 0.8 };
      case "in_progress": return { bg: "var(--color-info-bg)", border: "var(--color-info)", opacity: 1 };
      case "scheduled": return { bg: "var(--color-accent-glow)", border: "var(--color-accent-primary)", opacity: 1 };
      case "pending": 
      default: return { bg: "var(--color-surface)", border: "var(--color-border)", opacity: 1 };
    }
  };

  const getStatusBadgeColor = (status: string) => {
    switch (status) {
      case "scheduled": return { bg: "var(--color-accent-glow)", text: "var(--color-accent-primary)", border: "var(--color-accent-primary)" };
      case "in_progress": return { bg: "var(--color-info-bg)", text: "var(--color-info)", border: "var(--color-info)" };
      case "missed": return { bg: "var(--color-danger-bg)", text: "var(--color-danger)", border: "var(--color-danger)" };
      case "completed": return { bg: "var(--color-success-bg)", text: "var(--color-success)", border: "var(--color-success)" };
      default: return { bg: "var(--color-bg-subtle)", text: "var(--color-text-secondary)", border: "var(--color-border)" };
    }
  };

  const formatStatusText = (status: string) => {
    if (status === "in_progress") return "In Progress";
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  const formatDateLabel = (dateStr?: string | null) => {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  };

  const getDateInfo = (dateStr?: string | null, status?: string) => {
    const fallback = { label: "No Due Date", category: "no_date", bg: "var(--color-bg-subtle)", text: "var(--color-text-secondary)", border: "var(--color-border)" };
    if (!dateStr) return fallback;
    
    const targetDate = new Date(dateStr);
    if (isNaN(targetDate.getTime())) return fallback;

    const labelStr = formatDateLabel(dateStr);

    if (status === "completed") {
      return { label: labelStr, category: "completed", bg: "var(--color-bg-subtle)", text: "var(--color-text-muted)", border: "var(--color-border-subtle)" };
    }
    if (status === "missed") {
      return { label: labelStr, category: "missed", bg: "var(--color-danger-bg)", text: "var(--color-danger)", border: "var(--color-danger)" };
    }

    const today = new Date(); 
    const targetDay = new Date(targetDate.getFullYear(), targetDate.getMonth(), targetDate.getDate()).getTime();
    const todayDay = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const diffDays = Math.round((targetDay - todayDay) / (1000 * 60 * 60 * 24));
    
    if (diffDays < 0) return { label: "Overdue", category: "overdue", bg: "var(--color-danger-bg)", text: "var(--color-danger)", border: "var(--color-danger)" };
    if (diffDays === 0) return { label: "Today", category: "today", bg: "var(--color-warning-bg)", text: "var(--color-warning)", border: "var(--color-warning)" };
    if (diffDays === 1) return { label: "Tomorrow", category: "tomorrow", bg: "var(--color-accent-glow)", text: "var(--color-accent-primary)", border: "var(--color-accent-primary)" };
    
    return { label: labelStr, category: "upcoming", bg: "var(--color-surface)", text: "var(--color-text-secondary)", border: "var(--color-border)" };
  };

  const processedTasks = useMemo(() => {
    let filtered = tasks.filter(t => {
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
      if (energyFilter !== "all" && t.energy_level !== energyFilter) return false;
      if (tagFilter !== "all" && (!t.tags || !t.tags.includes(tagFilter))) return false;
      
      if (dateFilter) {
        if (!t.due_date) return false;
        const d = new Date(t.due_date);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const localTaskDate = `${y}-${m}-${day}`;
        if (localTaskDate !== dateFilter) return false;
      }
      return true;
    });

    filtered.sort((a, b) => {
      switch (sortBy) {
        case "priority_desc": return a.priority - b.priority; 
        case "duration_desc": return (b.estimated_duration || 0) - (a.estimated_duration || 0);
        case "duration_asc": return (a.estimated_duration || 0) - (b.estimated_duration || 0);
        case "dueDate_desc":
          if (!a.due_date) return 1;
          if (!b.due_date) return -1;
          return new Date(b.due_date).getTime() - new Date(a.due_date).getTime();
        case "dueDate_asc":
        default:
          if (!a.due_date) return 1;
          if (!b.due_date) return -1;
          return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
      }
    });

    const groups: Record<string, Task[]> = { overdue: [], today: [], tomorrow: [], upcoming: [], no_date: [], completed: [], missed: [] };

    filtered.forEach(task => {
      if (task.status === "completed") {
        groups.completed.push(task);
      } else if (task.status === "missed") {
        groups.missed.push(task);
      } else {
        const info = getDateInfo(task.due_date, task.status);
        if (groups[info.category]) {
          groups[info.category].push(task);
        } else {
          groups.no_date.push(task);
        }
      }
    });

    return groups;
  }, [tasks, statusFilter, priorityFilter, energyFilter, tagFilter, dateFilter, sortBy]);

  const renderTask = (task: Task, isCompletedSection: boolean) => {
    const completedSubs = task.sub_tasks?.filter(st => st.is_completed).length || 0;
    const totalSubs = task.sub_tasks?.length || 0;
    const isSelected = selectedTaskIds.includes(task.id!);
    const isExpanded = task.id ? expandedTasks[task.id] : false;
    
    const theme = getTaskPillTheme(task.status, isCompletedSection);
    const dateInfo = getDateInfo(task.due_date, task.status);
    const energyTheme = getEnergyColor(task.energy_level);
    const badgeTheme = getStatusBadgeColor(task.status);

    return (
      <div 
        key={task.id} 
        onClick={() => handleEditTask(task)}
        className={`p-4 sm:p-5 rounded-3xl border shadow-sm hover:shadow-md transition-all cursor-pointer relative group duration-300
          ${isSelected ? 'scale-[1.02] shadow-md z-10' : ''}
        `}
        style={{
          background: theme.bg,
          borderColor: isSelected ? 'var(--color-accent-primary)' : theme.border,
          opacity: theme.opacity,
          boxShadow: isSelected ? '0 0 0 1px var(--color-accent-primary), var(--shadow-md)' : 'var(--shadow-sm)'
        }}
      >
        <div className="flex items-start gap-4">
          <button 
            onClick={(e) => {
              e.stopPropagation();
              toggleTaskSelection(task.id!);
            }}
            className={`flex-shrink-0 mt-1 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all duration-200`}
            style={{
              background: isSelected ? 'var(--color-accent-primary)' : 'var(--color-surface)',
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
                className={`text-base sm:text-lg font-bold truncate transition-colors duration-200 ${isCompletedSection || task.status === 'missed' ? 'line-through' : ''}`}
                style={{ color: isCompletedSection || task.status === 'missed' ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}
              >
                {task.title}
              </h3>
              
              {task.status !== "pending" && (
                <span 
                  className={`flex-shrink-0 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider rounded-md border transition-colors duration-200`}
                  style={{ background: badgeTheme.bg, color: badgeTheme.text, borderColor: badgeTheme.border }}
                >
                  {formatStatusText(task.status)}
                </span>
              )}
            </div>

            {task.description && !isCompletedSection && (
              <p className="text-sm mt-1 line-clamp-2 leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                {task.description}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2 mt-3.5">
              
              {(task.snooze_count ?? 0) > 0 && (
                <span 
                  className="flex items-center gap-1 px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border transition-colors duration-200"
                  style={{ background: 'var(--color-warning-bg)', color: 'var(--color-warning)', borderColor: 'var(--color-warning)' }}
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  SNOOZED {task.snooze_count}X
                </span>
              )}

              {task.is_perishable && (
                <span 
                  className="flex items-center gap-1 px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border transition-colors duration-200"
                  style={{ background: 'var(--color-info-bg)', color: 'var(--color-info)', borderColor: 'var(--color-info)' }}
                >
                  ROUTINE
                </span>
              )}

              {(task.start_date || task.due_date) && (
                <span 
                  className={`flex items-center gap-1.5 px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border transition-colors duration-200`}
                  style={{ background: dateInfo.bg, color: dateInfo.text, borderColor: dateInfo.border }}
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                  </svg>
                  {task.start_date && (
                    <span className="opacity-80 mr-1 border-r border-current pr-1.5">Start: {formatDateLabel(task.start_date)}</span>
                  )}
                  {dateInfo.label}
                </span>
              )}

              <span 
                className="flex items-center gap-1 px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border transition-colors duration-200"
                style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)' }}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {task.estimated_duration ? `${task.estimated_duration} MINS` : "FLEXIBLE"}
              </span>
              
              <span 
                className={`px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border transition-colors duration-200`}
                style={{ background: energyTheme.bg, color: energyTheme.text, borderColor: energyTheme.border }}
              >
                {task.energy_level} ENERGY
              </span>

              {task.tags && task.tags.map(tag => (
                <span 
                  key={tag} 
                  className="px-2 py-1 text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-lg border transition-colors duration-200"
                  style={{ background: 'var(--color-surface)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border-subtle)' }}
                >
                  #{tag}
                </span>
              ))}

              <div className="flex items-center gap-0.5 ml-auto">
                {[...Array(5)].map((_, i) => (
                  <svg key={i} className={`w-3.5 h-3.5 transition-colors duration-200`} style={{ color: i < task.priority ? 'var(--color-accent-primary)' : 'var(--color-border-accent)' }} fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                  </svg>
                ))}
              </div>
            </div>

            {totalSubs > 0 && !isCompletedSection && (
              <div className="mt-4 pt-4 transition-colors duration-500" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
                <button 
                  onClick={(e) => task.id && toggleTaskExpansion(task.id, e)}
                  className="w-full flex justify-between items-center mb-2 group/header"
                >
                  <span className="text-[11px] font-bold uppercase tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
                    Checklist ({completedSubs}/{totalSubs})
                  </span>
                  <div className="flex items-center gap-2">
                    {completedSubs === totalSubs && (
                      <span className="text-[11px] font-bold uppercase tracking-wider transition-colors duration-200" style={{ color: 'var(--color-success)' }}>Done</span>
                    )}
                    <div 
                      className="w-6 h-6 rounded-full flex items-center justify-center transition-colors shadow-sm"
                      style={{ background: 'var(--color-surface)', color: 'var(--color-text-tertiary)' }}
                    >
                      <svg className={`w-4 h-4 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                      </svg>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div className="mb-3 space-y-2 animate-in fade-in slide-in-from-top-2 duration-200" onClick={e => e.stopPropagation()}>
                    {task.sub_tasks.map(sub => (
                      <div key={sub.id} className="flex items-center gap-3 py-1.5 px-2 rounded-lg transition-colors" style={{ background: 'var(--color-bg-subtle)' }}>
                        <button 
                          onClick={(e) => handleToggleSubTaskOnline(task.id!, sub.id, e)}
                          className={`flex-shrink-0 w-4 h-4 rounded border flex items-center justify-center transition-colors duration-200`}
                          style={{
                            background: sub.is_completed ? 'var(--color-accent-primary)' : 'var(--color-surface)',
                            borderColor: sub.is_completed ? 'var(--color-accent-primary)' : 'var(--color-border-accent)',
                          }}
                        >
                          {sub.is_completed && (
                            <svg className="w-3 h-3" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </button>
                        <span 
                          className={`text-sm font-medium transition-colors duration-200 ${sub.is_completed ? 'line-through' : ''}`}
                          style={{ color: sub.is_completed ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}
                        >
                          {sub.title}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="w-full h-1.5 rounded-full overflow-hidden transition-colors duration-500" style={{ background: 'var(--color-border-subtle)' }}>
                  <div 
                    className={`h-full transition-all duration-500`}
                    style={{ 
                      width: `${(completedSubs / totalSubs) * 100}%`,
                      background: completedSubs === totalSubs ? 'var(--color-success)' : 'var(--color-accent-primary)'
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  if ((authLoading || isLoading) && tasks.length === 0) {
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
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <p className="font-medium transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Loading your tasks...</p>
        </div>
      </div>
    );
  }

  if (isPreviewMode) {
    return (
      <div className="h-screen w-screen flex flex-col overflow-hidden relative transition-colors duration-500" style={{ background: 'var(--color-bg-base)', color: 'var(--color-text-primary)' }}>
        <div 
          className="absolute top-4 left-1/2 -translate-x-1/2 z-[60] rounded-full p-1.5 flex items-center gap-1 animate-fadeIn transition-colors duration-500"
          style={{
            background: 'var(--color-bg-glass-strong)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          <button
            onClick={() => setPreviewToggle("original")}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-200`}
            style={previewToggle === "original" ? { background: "var(--color-surface)", color: "var(--color-text-primary)", boxShadow: "var(--shadow-sm)" } : { color: "var(--color-text-secondary)" }}
          >
            Original
          </button>
          <button
            onClick={() => setPreviewToggle("optimised")}
            className="px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-200"
            style={previewToggle === "optimised" ? { background: "var(--color-accent-glow)", color: "var(--color-accent-primary)", boxShadow: "var(--shadow-sm)" } : { color: "var(--color-text-secondary)" }}
          >
            With Tasks
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
          className="fixed bottom-0 left-0 w-full p-4 sm:px-6 pb-[env(safe-area-inset-bottom,16px)] z-[60] flex flex-col sm:flex-row items-center justify-between gap-4 animate-fadeIn transition-colors duration-500"
          style={{
            background: 'var(--color-bg-glass-strong)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            borderTop: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-lg), var(--shadow-inner-glow)',
          }}
        >
          <div className="text-center sm:text-left">
            <h3 className="text-base font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
              Review Task Schedule
            </h3>
            <p className="text-sm transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
              Toggle between Original and With Tasks to see the AI suggestions.
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 w-full sm:w-auto">
            <button
              onClick={discardOptimisation}
              className="flex-1 sm:flex-none px-6 py-2.5 font-medium rounded-xl transition-all duration-200 btn-secondary"
            >
              Discard
            </button>
            <button
              onClick={acceptOptimisation}
              disabled={isOptimising}
              className="flex-1 sm:flex-none px-6 py-2.5 font-medium rounded-xl transition-all duration-200 disabled:opacity-50 hover:scale-[1.02] active:scale-[0.98] btn-primary"
            >
              {isOptimising ? "Applying..." : "Accept Changes"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div 
      className="min-h-screen font-sans pb-40 relative transition-colors duration-500"
      style={{ background: 'var(--color-bg-base)' }}
    >
      {/* Decorative Orbs handled entirely by body::before in global.css */}

      <div className="sticky top-0 z-30 transition-all duration-300">
        {selectedTaskIds.length > 0 ? (
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
              <span className="font-bold text-lg" style={{ color: 'var(--color-bg-base)' }}>{selectedTaskIds.length}</span>
            </div>
            <div className="flex gap-2">
              <button 
                onClick={() => generateTaskSchedulePreview(selectedTaskIds)} 
                disabled={isGeneratingSchedule} 
                className="px-3 py-1.5 rounded-lg text-xs font-bold shadow-sm transition-all disabled:opacity-50 hover:opacity-90"
                style={{ background: 'var(--color-bg-base)', color: 'var(--color-accent-primary)' }}
              >
                {isGeneratingSchedule ? "Loading..." : "Schedule"}
              </button>
              <button 
                onClick={handleBulkDelete} 
                className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all hover:opacity-90"
                style={{ background: 'var(--color-danger)', color: 'var(--color-bg-base)' }}
              >
                Delete
              </button>
              <button 
                onClick={handleBulkMissed} 
                className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all hover:opacity-90"
                style={{ background: 'var(--color-warning)', color: 'var(--color-bg-base)' }}
              >
                Missed
              </button>
              <button 
                onClick={handleBulkComplete} 
                className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all hover:opacity-90"
                style={{ background: 'var(--color-success)', color: 'var(--color-bg-base)' }}
              >
                Complete
              </button>
            </div>
          </div>
        ) : (
          <div 
            className="px-4 sm:px-6 pt-[calc(env(safe-area-inset-top,24px)+24px)] pb-4 flex justify-between items-center transition-colors duration-500"
            style={{
              background: 'var(--color-bg-glass-strong)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              borderBottom: '1px solid var(--color-border)',
            }}
          >
            <div>
              <h1 className="text-3xl font-bold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Tasks</h1>
              <p className="text-sm font-medium mt-1 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>{tasks.filter(t => t.status !== "completed" && t.status !== "missed").length} active items</p>
            </div>
            <div className="flex items-center gap-2">
              {/* --- MOBILE: icon-only buttons --- */}
              <div className="flex items-center gap-2 sm:hidden">
                <button 
                  onClick={() => generateTaskSchedulePreview([])}
                  disabled={isGeneratingSchedule}
                  className="p-2.5 rounded-xl transition-all duration-200 disabled:opacity-50 active:scale-95 btn-primary"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                  </svg>
                </button>
                <button 
                  onClick={() => setIsSearchOpen(true)}
                  className="p-2.5 rounded-xl transition-all duration-200 active:scale-95"
                  style={{ background: 'var(--color-bg-glass)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                  </svg>
                </button>
                <button 
                  onClick={() => setIsFilterOpen(!isFilterOpen)}
                  className="p-2.5 rounded-xl transition-all duration-200 active:scale-95"
                  style={{ 
                    background: isFilterOpen ? 'var(--color-accent-glow)' : 'var(--color-bg-glass)', 
                    border: isFilterOpen ? '1px solid var(--color-border-accent)' : '1px solid var(--color-border)', 
                    color: isFilterOpen ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)'
                  }}
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 01-.659 1.591l-5.432 5.432a2.25 2.25 0 00-.659 1.591v2.927a2.25 2.25 0 01-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 00-.659-1.591L3.659 7.409A2.25 2.25 0 013 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0112 3z" />
                  </svg>
                </button>
              </div>

              {/* --- DESKTOP: text + icon buttons --- */}
              <div className="hidden sm:flex items-center gap-2">
                <button 
                  onClick={() => generateTaskSchedulePreview([])}
                  disabled={isGeneratingSchedule}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all disabled:opacity-50 hover:scale-[1.02] active:scale-[0.98] btn-primary"
                >
                  {isGeneratingSchedule ? "..." : "Schedule All"}
                </button>
                <button 
                  onClick={() => setIsSearchOpen(true)}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold shadow-sm transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                  style={{ background: 'var(--color-bg-glass)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                  </svg>
                  Search
                </button>
                <button 
                  onClick={() => setIsFilterOpen(!isFilterOpen)}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold shadow-sm transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                  style={{ 
                    background: isFilterOpen ? 'var(--color-surface-hover)' : 'var(--color-bg-glass)', 
                    border: isFilterOpen ? '1px solid var(--color-accent-primary)' : '1px solid var(--color-border)', 
                    color: isFilterOpen ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)'
                  }}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 01-.659 1.591l-5.432 5.432a2.25 2.25 0 00-.659 1.591v2.927a2.25 2.25 0 01-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 00-.659-1.591L3.659 7.409A2.25 2.25 0 013 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0112 3z" />
                  </svg>
                  Filter
                </button>
              </div>
            </div>
          </div>
        )}

        {isFilterOpen && selectedTaskIds.length === 0 && (
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
                  <option value="dueDate_asc">Due Date (Soonest)</option>
                  <option value="dueDate_desc">Due Date (Latest)</option>
                  <option value="priority_desc">Highest Priority</option>
                  <option value="duration_desc">Longest Duration</option>
                  <option value="duration_asc">Shortest Duration</option>
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
                  <option value="scheduled">Scheduled</option>
                  <option value="in_progress">In Progress</option>
                  <option value="completed">Completed</option>
                  <option value="missed">Missed</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Priority Level</label>
                <select 
                  value={priorityFilter.toString()} 
                  onChange={e => setPriorityFilter(e.target.value === "all" ? "all" : Number.parseInt(e.target.value))} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                >
                  <option value="all">All Priorities</option>
                  <option value="1">1 Stars (Highest)</option>
                  <option value="2">2 Stars</option>
                  <option value="3">3 Stars</option>
                  <option value="4">4 Stars</option>
                  <option value="5">5 Stars (Lowest)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Energy Level</label>
                <select 
                  value={energyFilter} 
                  onChange={e => setEnergyFilter(e.target.value)} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                >
                  <option value="all">All Energy</option>
                  <option value="high">High Energy</option>
                  <option value="medium">Medium Energy</option>
                  <option value="low">Low Energy</option>
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

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-semibold tracking-wider transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Filter by Tag</label>
                <select 
                  value={tagFilter} 
                  onChange={e => setTagFilter(e.target.value)} 
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none transition-all duration-200"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)'
                  }}
                >
                  <option value="all">All Tags</option>
                  {availableTags.map(tag => (
                    <option key={tag} value={tag}>#{tag}</option>
                  ))}
                </select>
              </div>

            </div>
            <div className="max-w-3xl mx-auto mt-4 pt-4 flex justify-end" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
              <button 
                onClick={() => {
                  setSortBy("dueDate_asc");
                  setStatusFilter("all");
                  setPriorityFilter("all");
                  setEnergyFilter("all");
                  setDateFilter("");
                  setTagFilter("all");
                }} 
                className="text-sm font-semibold transition-colors hover:opacity-80"
                style={{ color: 'var(--color-accent-primary)' }}
              >
                Reset All Filters
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="px-4 sm:px-6 pt-6 max-w-3xl mx-auto space-y-8">
        
        {tasks.length === 0 && !isLoading && (
          <div className="text-center py-20 px-4">
            <div 
              className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-6 transition-colors duration-500"
              style={{
                background: 'var(--color-bg-glass)',
                border: '1px solid var(--color-border)',
                boxShadow: 'var(--shadow-md)',
              }}
            >
              <svg className="w-10 h-10 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold mb-2 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Your backlog is clear</h3>
            <p className="text-sm transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Tap the plus icon to add a new task.</p>
          </div>
        )}

        {processedTasks.overdue.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 flex justify-between transition-colors duration-200" style={{ color: 'var(--color-danger)' }}>
              Overdue
              <span className="text-[10px]" style={{ color: 'var(--color-danger)' }}>{processedTasks.overdue.length} items</span>
            </h2>
            {processedTasks.overdue.map(task => renderTask(task, false))}
          </div>
        )}

        {processedTasks.missed.length > 0 && (
          <div className="space-y-4 pt-4 transition-colors duration-500" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 flex justify-between transition-colors duration-200" style={{ color: 'var(--color-danger)' }}>
              Missed / Skipped
              <span className="text-[10px]" style={{ color: 'var(--color-danger)' }}>{processedTasks.missed.length} items</span>
            </h2>
            {processedTasks.missed.map(task => renderTask(task, false))}
          </div>
        )}

        {processedTasks.today.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Today</h2>
            {processedTasks.today.map(task => renderTask(task, false))}
          </div>
        )}

        {processedTasks.tomorrow.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Tomorrow</h2>
            {processedTasks.tomorrow.map(task => renderTask(task, false))}
          </div>
        )}

        {processedTasks.upcoming.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Upcoming</h2>
            {processedTasks.upcoming.map(task => renderTask(task, false))}
          </div>
        )}

        {processedTasks.no_date.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Anytime</h2>
            {processedTasks.no_date.map(task => renderTask(task, false))}
          </div>
        )}

        {processedTasks.completed.length > 0 && (
          <div className="space-y-4 pt-4 transition-colors duration-500" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
            <h2 className="text-sm font-bold uppercase tracking-widest px-2 flex justify-between transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
              Completed
              <span className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>{processedTasks.completed.length} items</span>
            </h2>
            {processedTasks.completed.map(task => renderTask(task, true))}
          </div>
        )}

      </div>

      {selectedTaskIds.length === 0 && (
        <button 
          onClick={handleOpenNewTask}
          className="fixed bottom-36 right-6 w-14 h-14 rounded-full flex items-center justify-center active:scale-95 transition-all duration-300 z-40 btn-primary"
          style={{ padding: 0 }}
        >
          <svg className="w-7 h-7" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </button>
      )}

      {userId && (
        <TaskModal 
          isOpen={isModalOpen} 
          onClose={() => setIsModalOpen(false)} 
          userId={userId} 
          editTask={editingTask} 
          onSaveSuccess={() => { fetchTasks(userId); setSelectedTaskIds([]); }}
          capacityData={editingTask ? null : capacityData}
        />
      )}
      {userId && (
        <GlobalSearchModal
          isOpen={isSearchOpen}
          onClose={() => setIsSearchOpen(false)}
          userId={userId}
          searchType="tasks"
          placeholder="Search tasks by name..."
          onResultClick={(result) => {
            // Find the full task from local state and open the editor
            const foundTask = tasks.find(t => t.id === result.id);
            if (foundTask) {
              setEditingTask(foundTask);
              setIsModalOpen(true);
            }
          }}
        />
      )}
      <NavigationBar />
    </div>
  );
}