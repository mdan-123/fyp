"use client";

import { useState, useEffect, useRef } from "react";

import { fetchLocationPredictions } from "@/lib/places";
import { fetchWithRetry } from "@/lib/fetchUtils"; 
import { auth } from "@/lib/firebase";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export async function fetchLocationDetails(placeId: string) {
  try {
    const res = await fetchWithRetry(`${API_BASE_URL}/api/places/details?place_id=${placeId}`, {
      method: "GET",
      timeoutMs: 8000
    });
    const data = await res.json();
    return data.location || null;
  } catch (err) {
    console.error("Error fetching place details:", err);
    return null;
  }
}

export interface LocationData {
  lat: number;
  lng: number;
  radius: number;
  trigger_on: "entry" | "exit";
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
  location_data?: LocationData | null;
  priority: "standard" | "high";
  repeat: "none" | "daily" | "weekly" | "monthly" | "custom";
  custom_repeat_days?: string[];
  status: "pending" | "delivered" | "dismissed" | "missed";
}

interface RemindersModalProps {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
  editReminder?: Reminder | null;
  onSaveSuccess: () => void;
}

const DAYS_OF_WEEK = [
  { id: "mon", label: "M" },
  { id: "tue", label: "T" },
  { id: "wed", label: "W" },
  { id: "thu", label: "T" },
  { id: "fri", label: "F" },
  { id: "sat", label: "S" },
  { id: "sun", label: "S" },
];

export default function RemindersModal({
  isOpen,
  onClose,
  userId,
  editReminder,
  onSaveSuccess,
}: RemindersModalProps) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  
  const [type, setType] = useState<"standalone" | "task" | "event">("standalone");
  const [referenceId, setReferenceId] = useState("");
  
  const [triggerType, setTriggerType] = useState<"time" | "location" | "time_and_location">("time");
  const [triggerDate, setTriggerDate] = useState("");
  const [triggerTime, setTriggerTime] = useState("");
  
  const [locQuery, setLocQuery] = useState("");
  const [locPredictions, setLocPredictions] = useState<any[]>([]);
  const [isLocDropdownOpen, setIsLocDropdownOpen] = useState(false);
  const [isSearchingLoc, setIsSearchingLoc] = useState(false);
  const locDropdownRef = useRef<HTMLDivElement>(null);

  const [locLat, setLocLat] = useState("");
  const [locLng, setLocLng] = useState("");
  
  const [radiusOption, setRadiusOption] = useState("100");
  const [locRadius, setLocRadius] = useState<number>(100);
  const [locTriggerOn, setLocTriggerOn] = useState<"entry" | "exit">("entry");
  
  const [priority, setPriority] = useState<"standard" | "high">("standard");
  const [repeat, setRepeat] = useState<"none" | "daily" | "weekly" | "monthly" | "custom">("none");
  const [customRepeatDays, setCustomRepeatDays] = useState<string[]>([]);

  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const [availableTasks, setAvailableTasks] = useState<any[]>([]);
  const [availableEvents, setAvailableEvents] = useState<any[]>([]);
  const [isLoadingLinks, setIsLoadingLinks] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && userId) {
      fetchAvailableLinks();
      
      if (editReminder) {
        setTitle(editReminder.title || "");
        setBody(editReminder.body || "");
        setType(editReminder.type || "standalone");
        setReferenceId(editReminder.reference_id || "");
        setTriggerType(editReminder.trigger_type || "time");
        setPriority(editReminder.priority || "standard");
        setRepeat(editReminder.repeat || "none");
        setCustomRepeatDays(editReminder.custom_repeat_days || []);
        
        if (editReminder.trigger_time) {
          const d = new Date(editReminder.trigger_time);
          if (!isNaN(d.getTime())) {
            const yyyy = d.getFullYear();
            const mm = String(d.getMonth() + 1).padStart(2, "0");
            const dd = String(d.getDate()).padStart(2, "0");
            const hh = String(d.getHours()).padStart(2, "0");
            const min = String(d.getMinutes()).padStart(2, "0");

            setTriggerDate(`${yyyy}-${mm}-${dd}`);
            setTriggerTime(`${hh}:${min}`);
          }
        }

        if (editReminder.location_data) {
          setLocLat(editReminder.location_data.lat.toString());
          setLocLng(editReminder.location_data.lng.toString());
          setLocRadius(editReminder.location_data.radius);
          setLocTriggerOn(editReminder.location_data.trigger_on);
          
          const presetRadii = [50, 100, 250, 500, 1000];
          if (presetRadii.includes(editReminder.location_data.radius)) {
            setRadiusOption(editReminder.location_data.radius.toString());
          } else {
            setRadiusOption("custom");
          }
        }
      } else {
        resetForm();
      }
    }
  }, [isOpen, editReminder, userId]);

  useEffect(() => {
    if (referenceId && !isLoadingLinks) {
      const list = type === "task" ? availableTasks : availableEvents;
      const selectedItem = list.find(item => item.id === referenceId);
      if (selectedItem) {
        setSearchQuery(selectedItem.title);
      }
    } else if (!referenceId) {
      setSearchQuery("");
    }
  }, [referenceId, type, availableTasks, availableEvents, isLoadingLinks]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
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

  const fetchAvailableLinks = async () => {
    setIsLoadingLinks(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const tasksRes = await fetchWithRetry(`${API_BASE_URL}/api/tasks/list/${userId}`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 8000
      });
      if (tasksRes.ok) {
        const data = await tasksRes.json();
        setAvailableTasks(data.tasks?.filter((t: any) => t.status !== "completed") || []);
      }

      const eventsRes = await fetchWithRetry(`${API_BASE_URL}/api/calendar/events/${userId}`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 8000
      });
      if (eventsRes.ok) {
        const eventsData = await eventsRes.json();
        const loadedEvents = (eventsData.events || [])
          .filter((e: any) => !e.is_ghost)
          .sort((a: any, b: any) => new Date(a.start).getTime() - new Date(b.start).getTime());
        setAvailableEvents(loadedEvents);
      }

    } catch (error) {
      console.error("Failed to fetch linkable items", error);
    } finally {
      setIsLoadingLinks(false);
    }
  };

  const resetForm = () => {
    setTitle("");
    setBody("");
    setType("standalone");
    setReferenceId("");
    setSearchQuery("");
    setTriggerType("time");
    setPriority("standard");
    setRepeat("none");
    setCustomRepeatDays([]);
    setLocQuery("");
    setLocLat("");
    setLocLng("");
    setRadiusOption("100");
    setLocRadius(100);
    setLocTriggerOn("entry");
    
    const now = new Date();
    now.setMinutes(now.getMinutes() + 15);
    
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    const hh = String(now.getHours()).padStart(2, "0");
    const min = String(now.getMinutes()).padStart(2, "0");
    
    setTriggerDate(`${yyyy}-${mm}-${dd}`);
    setTriggerTime(`${hh}:${min}`);
  };

  const toggleCustomDay = (dayId: string) => {
    setCustomRepeatDays(prev => 
      prev.includes(dayId) ? prev.filter(d => d !== dayId) : [...prev, dayId]
    );
  };

  const handleSave = async () => {
    if (!userId || !title.trim()) return;
    
    if ((triggerType === "location" || triggerType === "time_and_location") && (!locLat || !locLng)) {
      alert("Please select a valid location from the drop-down to save a geofence.");
      return;
    }
    
    setIsSaving(true);

    let combinedTriggerTime = null;
    if ((triggerType === "time" || triggerType === "time_and_location") && triggerDate && triggerTime) {
      combinedTriggerTime = new Date(`${triggerDate}T${triggerTime}:00`).toISOString();
    }

    let locationDataPayload = null;
    if (triggerType === "location" || triggerType === "time_and_location") {
      locationDataPayload = {
        lat: parseFloat(locLat) || 0,
        lng: parseFloat(locLng) || 0,
        radius: locRadius,
        trigger_on: locTriggerOn
      };
    }

    const payload: Reminder = {
      user_id: userId,
      title: title.trim(),
      body: body.trim(),
      type,
      reference_id: type !== "standalone" && referenceId ? referenceId : null,
      trigger_type: triggerType,
      trigger_time: combinedTriggerTime,
      location_data: locationDataPayload,
      priority,
      repeat,
      custom_repeat_days: repeat === "custom" ? customRepeatDays : [],
      status: editReminder?.status || "pending",
    };

    try {
      const token = await auth.currentUser?.getIdToken();
      let endpoint = "/api/reminders/create";
      let method = "POST";

      if (editReminder?.id) {
        endpoint = "/api/reminders/update";
        method = "PUT";
        payload.id = editReminder.id;
      }

      const res = await fetchWithRetry(`${API_BASE_URL}${endpoint}`, {
        method,
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify(payload),
        timeoutMs: 10000
      });

      if (res.ok) {
        onSaveSuccess();
        onClose();
      } else {
        console.error("Failed to save reminder", await res.text());
      }
    } catch (error) {
      console.error("Network error saving reminder", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!userId || !editReminder?.id) return;
    setIsDeleting(true);

    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/reminders/delete`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ user_id: userId, reminder_id: editReminder.id }),
        timeoutMs: 8000
      });

      if (res.ok) {
        onSaveSuccess();
        onClose();
      }
    } catch (error) {
      console.error("Failed to delete reminder", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const getFilteredItems = () => {
    const list = type === "task" ? availableTasks : availableEvents;
    if (!searchQuery) return list;
    return list.filter(item => item.title.toLowerCase().includes(searchQuery.toLowerCase()));
  };

  if (!isOpen) return null;

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
          <button type="button" onClick={onClose} className="text-sm font-medium transition-colors" style={{ color: 'var(--color-text-secondary)' }}>Cancel</button>
          <span className="font-semibold text-sm transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{editReminder ? "Edit Reminder" : "New Reminder"}</span>
          <button 
            type="button"
            onClick={handleSave} 
            disabled={!title.trim() || isSaving || isDeleting || (repeat === "custom" && customRepeatDays.length === 0)} 
            className="font-semibold text-sm disabled:opacity-50 transition-colors"
            style={{ color: 'var(--color-accent-primary)' }}
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 space-y-8 scrollbar-hide">
          
          <div className="space-y-4">
            <input 
              type="text" 
              placeholder="Remind me to..." 
              className="w-full text-2xl font-semibold border-none px-0 focus:ring-0 outline-none bg-transparent transition-colors duration-200" 
              style={{ color: 'var(--color-text-primary)' }}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <textarea 
              placeholder="Add extra details or context..." 
              rows={2}
              className="w-full text-sm border-none px-0 focus:ring-0 outline-none resize-none bg-transparent transition-colors duration-200"
              style={{ color: 'var(--color-text-secondary)' }}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>

          <div className="space-y-3">
            <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Link to Schedule</span>
            <div 
              className="flex p-1 rounded-xl transition-colors duration-500"
              style={{
                background: 'var(--color-bg-subtle)',
                border: '1px solid var(--color-border)',
              }}
            >
              <button 
                type="button" 
                onClick={() => { setType("standalone"); setReferenceId(""); setSearchQuery(""); }} 
                className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`}
                style={type === "standalone" ? { background: 'var(--color-surface)', color: 'var(--color-text-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}
              >
                Standalone
              </button>
              <button 
                type="button" 
                onClick={() => { setType("task"); setReferenceId(""); setSearchQuery(""); }} 
                className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`}
                style={type === "task" ? { background: 'var(--color-surface)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}
              >
                Link Task
              </button>
              <button 
                type="button" 
                onClick={() => { setType("event"); setReferenceId(""); setSearchQuery(""); }} 
                className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`}
                style={type === "event" ? { background: 'var(--color-surface)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}
              >
                Link Event
              </button>
            </div>
            
            {(type === "task" || type === "event") && (
              <div className="relative animate-fadeIn" ref={dropdownRef}>
                <div 
                  className="flex items-center rounded-xl px-4 py-3 transition-colors duration-500"
                  style={{
                    background: 'var(--color-bg-subtle)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  <svg className="w-4 h-4 mr-2 flex-shrink-0 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder={`Search for a ${type}...`}
                    className="w-full text-sm bg-transparent outline-none transition-colors duration-200 input-glass"
                    style={{ padding: 0, border: 'none', background: 'transparent' }}
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setReferenceId(""); 
                      setIsDropdownOpen(true);
                    }}
                    onFocus={() => setIsDropdownOpen(true)}
                  />
                </div>

                {isDropdownOpen && (
                  <div 
                    className="absolute z-50 w-full mt-2 rounded-xl max-h-60 overflow-y-auto transition-colors duration-500"
                    style={{
                      background: 'var(--color-bg-glass-strong)',
                      backdropFilter: 'blur(12px)',
                      WebkitBackdropFilter: 'blur(12px)',
                      border: '1px solid var(--color-border)',
                      boxShadow: 'var(--shadow-md)',
                    }}
                  >
                    {isLoadingLinks ? (
                      <div className="p-4 text-sm text-center transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Loading items...</div>
                    ) : getFilteredItems().length > 0 ? (
                      getFilteredItems().map((item) => {
                        const dateStr = item.start ? new Date(item.start).toLocaleDateString("en-GB", { month: "short", day: "numeric" }) : "";
                        return (
                          <div
                            key={item.id}
                            className="px-4 py-3 cursor-pointer transition-colors"
                            style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                            onClick={() => {
                              setReferenceId(item.id);
                              setSearchQuery(item.title);
                              setIsDropdownOpen(false);
                            }}
                          >
                            <p className="text-sm font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{item.title}</p>
                            {dateStr && <p className="text-xs mt-0.5 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>{dateStr}</p>}
                          </div>
                        );
                      })
                    ) : (
                      <div className="p-4 text-sm text-center transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>No matching {type}s found.</div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Trigger By</span>
              <div 
                className="flex p-1 rounded-xl transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <button type="button" onClick={() => setTriggerType("time")} className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`} style={triggerType === "time" ? { background: 'var(--color-surface)', color: 'var(--color-text-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Time</button>
                <button type="button" onClick={() => setTriggerType("location")} className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`} style={triggerType === "location" ? { background: 'var(--color-warning-bg)', color: 'var(--color-warning)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Location</button>
                <button type="button" onClick={() => setTriggerType("time_and_location")} className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`} style={triggerType === "time_and_location" ? { background: 'var(--color-accent-glow)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Both</button>
              </div>
            </div>

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Priority</span>
              <div 
                className="flex p-1 rounded-xl transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <button type="button" onClick={() => setPriority("standard")} className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`} style={priority === "standard" ? { background: 'var(--color-surface)', color: 'var(--color-text-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Standard</button>
                <button type="button" onClick={() => setPriority("high")} className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200`} style={priority === "high" ? { background: 'var(--color-danger)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>High</button>
              </div>
            </div>
          </div>

          {(triggerType === "time" || triggerType === "time_and_location") && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 animate-fadeIn">
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Date</span>
                <input 
                  type="date" 
                  className="w-full min-w-0 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                  value={triggerDate}
                  onChange={(e) => setTriggerDate(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Time</span>
                <input 
                  type="time" 
                  className="w-full min-w-0 text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass"
                  value={triggerTime}
                  onChange={(e) => setTriggerTime(e.target.value)}
                />
              </div>
            </div>
          )}

          {(triggerType === "location" || triggerType === "time_and_location") && (
            <div 
              className="space-y-4 p-4 rounded-xl animate-fadeIn transition-colors duration-500"
              style={{
                background: 'var(--color-warning-bg)',
                border: '1px solid var(--color-warning)',
              }}
            >
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-bold uppercase tracking-wider transition-colors duration-200" style={{ color: 'var(--color-warning)' }}>Geofence Settings</span>
                <div 
                  className="flex p-0.5 rounded-lg transition-colors duration-500"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  <button type="button" onClick={() => setLocTriggerOn("entry")} className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all duration-200`} style={locTriggerOn === "entry" ? { background: 'var(--color-warning)', color: 'var(--color-bg-base)' } : { color: 'var(--color-text-secondary)' }}>Arriving</button>
                  <button type="button" onClick={() => setLocTriggerOn("exit")} className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all duration-200`} style={locTriggerOn === "exit" ? { background: 'var(--color-warning)', color: 'var(--color-bg-base)' } : { color: 'var(--color-text-secondary)' }}>Leaving</button>
                </div>
              </div>

              <div className="relative" ref={locDropdownRef}>
                <div 
                  className="flex items-center rounded-xl px-3 py-2.5 transition-colors duration-500"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-warning)',
                  }}
                >
                  <svg className="w-4 h-4 mr-2 flex-shrink-0 transition-colors duration-200" style={{ color: 'var(--color-warning)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Search for a place (e.g. Tesco)..."
                    className="w-full text-sm bg-transparent outline-none transition-colors duration-200 input-glass"
                    style={{ padding: 0, border: 'none', background: 'transparent' }}
                    value={locQuery}
                    onChange={(e) => {
                      setLocQuery(e.target.value);
                      setIsLocDropdownOpen(true);
                    }}
                    onFocus={() => setIsLocDropdownOpen(true)}
                  />
                </div>

                {isLocDropdownOpen && locQuery.trim() !== "" && (
                  <div 
                    className="absolute z-50 w-full mt-2 rounded-xl max-h-48 overflow-y-auto transition-colors duration-500"
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
                        <div
                          key={pred.place_id || pred.description}
                          className="px-3 py-2.5 cursor-pointer transition-colors"
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
                          <p className="text-xs font-semibold line-clamp-1 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{pred.description}</p>
                        </div>
                      ))
                    ) : (
                      <div className="p-3 text-xs text-center transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>No places found.</div>
                    )}
                  </div>
                )}
              </div>
              
              <div className="space-y-1.5 pt-2">
                <span className="text-[10px] uppercase tracking-widest font-semibold transition-colors duration-200" style={{ color: 'var(--color-warning)' }}>Radius Area</span>
                <div className="flex gap-2">
                  <select
                    value={radiusOption}
                    onChange={(e) => {
                      setRadiusOption(e.target.value);
                      if (e.target.value !== "custom") setLocRadius(Number.parseInt(e.target.value));
                    }}
                    className="w-full text-sm rounded-lg px-3 py-2.5 outline-none transition-all appearance-none cursor-pointer input-glass"
                    style={{ borderColor: 'var(--color-warning)' }}
                  >
                    <option value="50">50 metres (Very Close)</option>
                    <option value="100">100 metres (Close)</option>
                    <option value="250">250 metres (Walking Distance)</option>
                    <option value="500">500 metres (Neighbourhood)</option>
                    <option value="1000">1000 metres (Driving Distance)</option>
                    <option value="custom">Custom metres...</option>
                  </select>
                  {radiusOption === "custom" && (
                    <input 
                      type="number" 
                      placeholder="e.g. 150"
                      className="w-24 text-sm rounded-lg px-3 py-2.5 outline-none transition-all input-glass"
                      style={{ borderColor: 'var(--color-warning)' }}
                      value={locRadius}
                      onChange={(e) => setLocRadius(Number.parseInt(e.target.value) || 0)}
                    />
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="space-y-3">
            <span className="text-[10px] uppercase tracking-widest font-semibold px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Repeat</span>
            <select 
              value={repeat} 
              onChange={(e) => setRepeat(e.target.value as any)} 
              className="w-full text-sm rounded-xl px-4 py-3 outline-none appearance-none cursor-pointer transition-all input-glass"
            >
              <option value="none">Never repeat</option>
              <option value="daily">Every day</option>
              <option value="weekly">Every week</option>
              <option value="monthly">Every month</option>
              <option value="custom">Custom days...</option>
            </select>

            {repeat === "custom" && (
              <div 
                className="flex justify-between items-center p-2 rounded-xl animate-fadeIn transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                {DAYS_OF_WEEK.map((day) => {
                  const isSelected = customRepeatDays.includes(day.id);
                  return (
                    <button
                      key={day.id}
                      type="button"
                      onClick={() => toggleCustomDay(day.id)}
                      className="w-10 h-10 rounded-full text-sm font-semibold flex items-center justify-center transition-all duration-200"
                      style={isSelected ? {
                        background: 'var(--color-accent-gradient)',
                        color: 'var(--color-bg-base)',
                        boxShadow: 'var(--shadow-sm)',
                        transform: 'scale(1.05)',
                      } : {
                        background: 'var(--color-surface)',
                        color: 'var(--color-text-secondary)',
                        border: '1px solid var(--color-border)',
                      }}
                    >
                      {day.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

        </div>

        {editReminder && (
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
              {isDeleting ? "Deleting..." : "Delete Reminder"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}