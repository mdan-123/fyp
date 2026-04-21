"use client";

import { useState, useEffect, useRef } from "react";
import { getStorage, ref, uploadBytes, getDownloadURL } from "firebase/storage";
import { app, auth } from "../lib/firebase";
import { fetchLocationPredictions } from "@/lib/places"; 
import { fetchWithRetry } from "@/lib/fetchUtils"; 

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
  status: "pending" | "delivered" | "dismissed" | "missed";
}

interface EventModalProps {
  isOpen: boolean;
  onClose: () => void;
  linkedAccounts: any[];
  onSaveSuccess: () => void;
  userId: string;
  editEvent?: any | null; 
  instanceDate?: Date;
}

const DAYS_OF_WEEK = [
  { id: '1', label: 'M' }, { id: '2', label: 'T' }, { id: '3', label: 'W' },
  { id: '4', label: 'T' }, { id: '5', label: 'F' }, { id: '6', label: 'S' },
  { id: '0', label: 'S' }
];

export default function EventModal({ 
  isOpen, onClose, linkedAccounts, onSaveSuccess, userId, editEvent, instanceDate
}: EventModalProps) {
  
  // --- Original Event States ---
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [meetingLink, setMeetingLink] = useState("");
  const [isLocked, setIsLocked] = useState(true);
  const [category, setCategory] = useState("");
  const [startDate, setStartDate] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endDate, setEndDate] = useState("");
  const [endTime, setEndTime] = useState("10:00");
  const [description, setDescription] = useState("");
  
  const [recurrence, setRecurrence] = useState("none");
  const [selectedDays, setSelectedDays] = useState<string[]>([]);
  const [updateMode, setUpdateMode] = useState<'all' | 'single'>('all');

  const [travelTime, setTravelTime] = useState("0");
  const [travelOrigin, setTravelOrigin] = useState("");
  const [travelMode, setTravelMode] = useState<'driving' | 'transit' | 'walking' | 'cycling'>('driving');
  const [isCalculatingTravel, setIsCalculatingTravel] = useState(false);
  const [showTravelCalculator, setShowTravelCalculator] = useState(false);

  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [attachments, setAttachments] = useState<FileList | null>(null);
  const [existingAttachments, setExistingAttachments] = useState<string[]>([]);
  
  const [predictions, setPredictions] = useState<any[]>([]);
  const [showPredictions, setShowPredictions] = useState(false);
  const [originPredictions, setOriginPredictions] = useState<any[]>([]);
  const [showOriginPredictions, setShowOriginPredictions] = useState(false);

  // --- New Telemetry & Habit States ---
  const [completionStatus, setCompletionStatus] = useState<"pending" | "completed" | "missed">("pending");
  const [isPerishable, setIsPerishable] = useState(false);
  const [snoozeCount, setSnoozeCount] = useState(0);

  // --- New Reminder States ---
  const [existingReminders, setExistingReminders] = useState<Reminder[]>([]);
  const [queuedLinkIds, setQueuedLinkIds] = useState<string[]>([]);
  const [pendingNewReminders, setPendingNewReminders] = useState<Reminder[]>([]);
  
  const [isAddingReminder, setIsAddingReminder] = useState(false);
  const [newRemTitle, setNewRemTitle] = useState("");
  const [newRemTriggerType, setNewRemTriggerType] = useState<"time" | "location">("time");
  const [newRemDate, setNewRemDate] = useState("");
  const [newRemTime, setNewRemTime] = useState("");
  
  const [locQuery, setLocQuery] = useState("");
  const [locPredictions, setLocPredictions] = useState<any[]>([]);
  const [isLocDropdownOpen, setIsLocDropdownOpen] = useState(false);
  const [isSearchingLoc, setIsSearchingLoc] = useState(false);
  const [locLat, setLocLat] = useState("");
  const [locLng, setLocLng] = useState("");
  const [locRadius, setLocRadius] = useState<number>(100);
  const [locTriggerOn, setLocTriggerOn] = useState<"entry" | "exit">("entry");
  
  const locDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(async () => {
      if (location.length > 2 && showPredictions) {
        setPredictions(await fetchLocationPredictions(location));
      } else { setPredictions([]); }
    }, 300);
    return () => clearTimeout(timer);
  }, [location, showPredictions]);

  useEffect(() => {
    const timer = setTimeout(async () => {
      if (travelOrigin.length > 2 && showOriginPredictions) {
        setOriginPredictions(await fetchLocationPredictions(travelOrigin));
      } else { setOriginPredictions([]); }
    }, 300);
    return () => clearTimeout(timer);
  }, [travelOrigin, showOriginPredictions]);

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

  useEffect(() => {
    if (isOpen) {
      if (userId) fetchUserReminders();

      if (editEvent) {
        setTitle(editEvent.title || "");
        setLocation(editEvent.location || "");
        setMeetingLink(editEvent.meeting_link || "");
        setIsLocked(editEvent.is_locked ?? true);
        setCategory(editEvent.category || "");
        setDescription(editEvent.description || "");
        setExistingAttachments(editEvent.attachments || []);
        setRecurrence(editEvent.recurrence || "none");
        setSelectedDays(editEvent.recurrence_days || []);
        setTravelTime(editEvent.travel_time ? String(editEvent.travel_time) : "0");
        setTravelOrigin(editEvent.travel_origin || "");
        setTravelMode(editEvent.travel_mode || "driving");
        setUpdateMode('all'); 
        setShowTravelCalculator(!!editEvent.travel_origin);
        
        setCompletionStatus(editEvent.completion_status || "pending");
        setIsPerishable(editEvent.is_perishable || false);
        setSnoozeCount(editEvent.snooze_count || 0);

        let startObj = new Date(editEvent.proposed_start || editEvent.start);
        let endObj = new Date(editEvent.proposed_end || editEvent.end);
        
        if (instanceDate && editEvent.recurrence !== 'none') {
          const durationMs = endObj.getTime() - startObj.getTime();
          startObj = new Date(instanceDate);
          startObj.setHours(new Date(editEvent.start).getHours(), new Date(editEvent.start).getMinutes(), 0, 0);
          endObj = new Date(startObj.getTime() + durationMs);
        }

        const formatLocal = (d: Date) => {
          if (isNaN(d.getTime())) return { date: "", time: "" };
          const yyyy = d.getFullYear();
          const mm = String(d.getMonth() + 1).padStart(2, "0");
          const dd = String(d.getDate()).padStart(2, "0");
          const hh = String(d.getHours()).padStart(2, "0");
          const min = String(d.getMinutes()).padStart(2, "0");
          return { date: `${yyyy}-${mm}-${dd}`, time: `${hh}:${min}` };
        };

        const localStart = formatLocal(startObj);
        const localEnd = formatLocal(endObj);

        setStartDate(localStart.date);
        setStartTime(localStart.time);
        setEndDate(localEnd.date);
        setEndTime(localEnd.time);

        const match = linkedAccounts.find(a => a.email === editEvent.email);
        if (match) {
          setSelectedAccount(JSON.stringify(match));
        } else if (linkedAccounts.length > 0) {
          setSelectedAccount(JSON.stringify(linkedAccounts[0]));
        }
      } else {
        const now = new Date();
        const hourFromNow = new Date(now.getTime() + 60 * 60 * 1000);
        setTitle(""); setLocation(""); setMeetingLink(""); setIsLocked(true); setDescription("");
        setCategory(""); 
        setRecurrence("none"); setSelectedDays([]); setTravelTime("0"); setTravelOrigin("");
        setTravelMode("driving"); setShowTravelCalculator(false); setExistingAttachments([]);
        setAttachments(null); setUpdateMode('all');
        setQueuedLinkIds([]); setPendingNewReminders([]); setIsAddingReminder(false);
        
        setCompletionStatus("pending");
        setIsPerishable(false);
        setSnoozeCount(0);

        if (instanceDate) {
          now.setFullYear(instanceDate.getFullYear(), instanceDate.getMonth(), instanceDate.getDate());
          hourFromNow.setFullYear(instanceDate.getFullYear(), instanceDate.getMonth(), instanceDate.getDate());
        }

        const formatLocal = (d: Date) => {
            const yyyy = d.getFullYear();
            const mm = String(d.getMonth() + 1).padStart(2, "0");
            const dd = String(d.getDate()).padStart(2, "0");
            const hh = String(d.getHours()).padStart(2, "0");
            const min = String(d.getMinutes()).padStart(2, "0");
            return { date: `${yyyy}-${mm}-${dd}`, time: `${hh}:${min}` };
        };

        const localNow = formatLocal(now);
        const localLater = formatLocal(hourFromNow);

        setStartDate(localNow.date);
        setStartTime(localNow.time);
        setEndDate(localLater.date);
        setEndTime(localLater.time);

        if (linkedAccounts.length > 0) setSelectedAccount(JSON.stringify(linkedAccounts[0]));
      }
    }
  }, [isOpen, editEvent, linkedAccounts, instanceDate, userId]);

  const handleStartChange = (newDate: string, newTime: string) => {
    setStartDate(newDate);
    setStartTime(newTime);
    const startObj = new Date(`${newDate}T${newTime}:00`);
    const currentEndObj = new Date(`${endDate}T${endTime}:00`);
    if (startObj.getTime() >= currentEndObj.getTime()) {
      const newEndObj = new Date(startObj.getTime() + 60 * 60 * 1000);
      const yyyy = newEndObj.getFullYear();
      const mm = String(newEndObj.getMonth() + 1).padStart(2, "0");
      const dd = String(newEndObj.getDate()).padStart(2, "0");
      const hh = String(newEndObj.getHours()).padStart(2, "0");
      const min = String(newEndObj.getMinutes()).padStart(2, "0");
      setEndDate(`${yyyy}-${mm}-${dd}`);
      setEndTime(`${hh}:${min}`);
    }
  };

  const handleEndChange = (newDate: string, newTime: string) => {
    const startObj = new Date(`${startDate}T${startTime}:00`);
    const newEndObj = new Date(`${newDate}T${newTime}:00`);
    if (newEndObj.getTime() <= startObj.getTime()) {
      const fallbackEndObj = new Date(startObj.getTime() + 60 * 60 * 1000);
      const yyyy = fallbackEndObj.getFullYear();
      const mm = String(fallbackEndObj.getMonth() + 1).padStart(2, "0");
      const dd = String(fallbackEndObj.getDate()).padStart(2, "0");
      const hh = String(fallbackEndObj.getHours()).padStart(2, "0");
      const min = String(fallbackEndObj.getMinutes()).padStart(2, "0");
      setEndDate(`${yyyy}-${mm}-${dd}`);
      setEndTime(`${hh}:${min}`);
    } else {
      setEndDate(newDate);
      setEndTime(newTime);
    }
  };

  const toggleDay = (id: string) => setSelectedDays(prev => prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]);

  const handleDelete = async () => {
    if (!editEvent?.id) return;
    setIsDeleting(true);
    try {
      let endpoint = "/api/calendar/delete-event";
      let payload: any = { event_id: editEvent.id, user_id: userId };

      if (updateMode === 'single' && instanceDate) {
        endpoint = "/api/calendar/update"; 
        const dateStr = `${instanceDate.getFullYear()}-${String(instanceDate.getMonth()+1).padStart(2, '0')}-${String(instanceDate.getDate()).padStart(2, '0')}`;
        payload = { event_id: editEvent.id, user_id: userId, update_mode: 'exception_delete', instance_date: dateStr };
      }

      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}${endpoint}`, {
        method: updateMode === 'single' ? "POST" : "DELETE",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify(payload),
        timeoutMs: 10000
      });
      
      if (res.ok) { 
        onSaveSuccess(); 
        onClose(); 
      } else {
        alert(`Server refused to delete. Status: ${res.status}`);
      }
    } catch (err) { 
      console.error("Deletion error:", err); 
      alert("Network error while trying to delete.");
    } 
    finally { setIsDeleting(false); }
  };

  const handleCalculateTravel = async () => {
    if (!travelOrigin || !location) return;
    setIsCalculatingTravel(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/location/travel-time`, {
        method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ origin: travelOrigin, destination: location, mode: travelMode }),
        timeoutMs: 10000
      });
      if (res.ok) {
        const data = await res.json();
        setTravelTime(String(data.minutes));
      } else {
        alert("Could not calculate travel time for this mode. Please enter it manually.");
        setTravelTime("0");
      }
    } catch (err) {
      alert("Network error. Please try again.");
      setTravelTime("0");
    } finally { setIsCalculatingTravel(false); }
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
      type: "event",
      trigger_type: newRemTriggerType,
      trigger_time,
      location_data,
      priority: "standard",
      repeat: "none",
      status: "pending"
    };

    setPendingNewReminders([...pendingNewReminders, newRem]);
    setNewRemTitle(""); setLocQuery(""); setLocLat(""); setLocLng(""); setIsAddingReminder(false);
  };

  const handleAction = async () => {
    if (!title) { alert("Please enter a title."); return; }
    if (!selectedAccount) { alert("Please select a calendar account."); return; }
    
    setIsSaving(true);
    const account = JSON.parse(selectedAccount);
    
    const startISO = new Date(`${startDate}T${startTime}:00`).toISOString();
    const endISO = new Date(`${endDate}T${endTime}:00`).toISOString();

    try {
      const token = await auth.currentUser?.getIdToken();
      const storage = getStorage(app);
      const newUploadUrls: string[] = [];
      if (attachments && attachments.length > 0) {
        for (let i = 0; i < attachments.length; i++) {
          const fileRef = ref(storage, `attachments/${userId}/${Date.now()}_${attachments[i].name}`);
          await uploadBytes(fileRef, attachments[i]);
          newUploadUrls.push(await getDownloadURL(fileRef));
        }
      }

      const parsedTravelTime = travelTime === "auto" ? 0 : parseInt(travelTime, 10) || 0;
      let dateStr = null;
      if (instanceDate) {
        dateStr = `${instanceDate.getFullYear()}-${String(instanceDate.getMonth()+1).padStart(2, '0')}-${String(instanceDate.getDate()).padStart(2, '0')}`;
      }

      const payload = {
        event_id: editEvent?.id || null, user_id: userId, title, start: startISO, end: endISO,
        location, meeting_link: meetingLink, is_locked: isLocked, description,
        category: category || null,
        recurrence: updateMode === 'single' ? 'none' : recurrence,
        recurrence_days: (recurrence === 'daily' || recurrence === 'custom') ? selectedDays : [],
        travel_time: parsedTravelTime, travel_origin: travelOrigin, travel_mode: travelMode,
        provider: account.provider, email: account.email,
        attachments: [...existingAttachments, ...newUploadUrls],
        update_mode: updateMode, instance_date: dateStr,
        
        completion_status: completionStatus,
        is_perishable: isPerishable
      };

      const res = await fetchWithRetry(`${API_BASE_URL}${editEvent ? "/api/calendar/update" : "/api/calendar/new"}`, {
        method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify(payload),
        timeoutMs: 12000 
      });
      
      if (res.ok) { 
        const data = await res.json();
        const finalEventId = editEvent?.id || data.event_id || data.id;

        if (finalEventId) {
          for (const rId of queuedLinkIds) {
            await fetchWithRetry(`${API_BASE_URL}/api/reminders/update`, {
              method: "PUT",
              headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
              body: JSON.stringify({ id: rId, user_id: userId, type: "event", reference_id: finalEventId }),
              timeoutMs: 8000
            });
          }
          for (const newRem of pendingNewReminders) {
            newRem.reference_id = finalEventId;
            await fetchWithRetry(`${API_BASE_URL}/api/reminders/create`, {
              method: "POST",
              headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
              body: JSON.stringify(newRem),
              timeoutMs: 8000
            });
          }
        }
        onSaveSuccess(); onClose(); 
      }
    } catch (err) { console.error("Submission error:", err); } 
    finally { setIsSaving(false); }
  };

  if (!isOpen) return null;

  const activelyLinkedReminders = existingReminders.filter(r => r.reference_id === editEvent?.id);
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
      >
        
        <div 
          className="px-6 py-5 flex justify-between items-center z-10 transition-colors duration-500"
          style={{
            background: 'var(--color-bg-subtle)',
            borderBottom: '1px solid var(--color-border)',
          }}
        >
          <button onClick={onClose} className="text-sm font-medium transition-colors" style={{ color: 'var(--color-text-secondary)' }}>Cancel</button>
          <span className="text-sm font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{editEvent ? "Edit Event" : "New Event"}</span>
          <button 
            onClick={handleAction} 
            disabled={isSaving || isDeleting} 
            className="text-sm font-semibold transition-colors disabled:opacity-50"
            style={{ color: 'var(--color-accent-primary)' }}
          >
            {isSaving ? "Saving..." : "Done"}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 space-y-8 scrollbar-hide">
          
          {editEvent && editEvent.recurrence !== 'none' && (
            <div 
              className="p-1 rounded-xl flex transition-colors duration-500"
              style={{
                background: 'var(--color-bg-glass)',
                border: '1px solid var(--color-border-accent)',
              }}
            >
               <button onClick={() => setUpdateMode('single')} className={`flex-1 py-2 text-[11px] uppercase tracking-wider font-medium rounded-lg transition-all`} style={updateMode === 'single' ? { background: 'var(--color-surface)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>This instance only</button>
               <button onClick={() => setUpdateMode('all')} className={`flex-1 py-2 text-[11px] uppercase tracking-wider font-medium rounded-lg transition-all`} style={updateMode === 'all' ? { background: 'var(--color-surface)', color: 'var(--color-accent-primary)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Entire series</button>
            </div>
          )}

          <div className="space-y-4">
            <input 
              type="text" 
              value={title} 
              onChange={(e) => setTitle(e.target.value)} 
              placeholder="Event Title" 
              className={`w-full text-2xl border-none px-0 focus:ring-0 outline-none transition-colors bg-transparent ${completionStatus === 'missed' ? 'line-through' : ''}`}
              style={{ 
                color: completionStatus === 'missed' ? 'var(--color-text-muted)' : 'var(--color-text-primary)',
              }} 
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
                 <button onClick={() => setCompletionStatus("pending")} className={`flex-1 px-2 sm:px-5 py-2.5 text-xs font-bold rounded-lg transition-all`} style={completionStatus === "pending" ? { background: 'var(--color-surface)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border-subtle)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Pending</button>
                 <button onClick={() => setCompletionStatus("completed")} className={`flex-1 px-2 sm:px-5 py-2.5 text-xs font-bold rounded-lg transition-all`} style={completionStatus === "completed" ? { background: 'var(--color-success)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Completed</button>
                 <button onClick={() => setCompletionStatus("missed")} className={`flex-1 px-2 sm:px-5 py-2.5 text-xs font-bold rounded-lg transition-all`} style={completionStatus === "missed" ? { background: 'var(--color-danger)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { color: 'var(--color-text-secondary)' }}>Missed</button>
              </div>
            </div>

            {snoozeCount > 0 && (
              <div 
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg w-fit transition-colors duration-500"
                style={{
                  background: 'var(--color-warning-bg)',
                  border: '1px solid var(--color-warning)',
                  color: 'var(--color-warning)',
                }}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span className="text-xs font-bold uppercase tracking-wider">Snoozed {snoozeCount} time{snoozeCount > 1 ? 's' : ''}</span>
              </div>
            )}
            
            <div className="flex flex-col sm:flex-row gap-3 pt-2">
              <div 
                className="flex-1 flex items-center justify-between p-4 rounded-2xl transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="space-y-0.5">
                  <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Lock Event</p>
                  <p className="text-[11px] transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Prevent AI rescheduling</p>
                </div>
                <button 
                  onClick={() => setIsLocked(!isLocked)} 
                  className="w-11 h-6 rounded-full transition-all relative flex-shrink-0" 
                  style={{ background: isLocked ? 'var(--color-accent-gradient)' : 'var(--color-border)' }}
                >
                  <div className={`absolute top-1 w-4 h-4 rounded-full shadow-sm transition-all ${isLocked ? 'left-6' : 'left-1'}`} style={{ background: 'var(--color-bg-base)' }} />
                </button>
              </div>

              <div 
                className="flex-1 flex items-center justify-between p-4 rounded-2xl transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="space-y-0.5">
                  <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Routine / Habit</p>
                  <p className="text-[11px] transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Skip if missed (Sunk Debt)</p>
                </div>
                <button 
                  onClick={() => setIsPerishable(!isPerishable)} 
                  className="w-11 h-6 rounded-full transition-all relative flex-shrink-0" 
                  style={{ background: isPerishable ? 'var(--color-danger)' : 'var(--color-border)' }}
                >
                  <div className={`absolute top-1 w-4 h-4 rounded-full shadow-sm transition-all ${isPerishable ? 'left-6' : 'left-1'}`} style={{ background: 'var(--color-bg-base)' }} />
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Starts</span>
                <div className="flex flex-col gap-2">
                  <input type="date" value={startDate} onChange={(e) => handleStartChange(e.target.value, startTime)} className="w-full min-w-0 rounded-xl text-sm py-3 px-4 outline-none transition-all input-glass" />
                  <input type="time" value={startTime} onChange={(e) => handleStartChange(startDate, e.target.value)} className="w-full min-w-0 rounded-xl text-sm py-3 px-4 outline-none transition-all input-glass" />
                </div>
              </div>
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Ends</span>
                <div className="flex flex-col gap-2">
                  <input type="date" value={endDate} onChange={(e) => handleEndChange(e.target.value, endTime)} className="w-full min-w-0 rounded-xl text-sm py-3 px-4 outline-none transition-all input-glass" />
                  <input type="time" value={endTime} onChange={(e) => handleEndChange(endDate, e.target.value)} className="w-full min-w-0 rounded-xl text-sm py-3 px-4 outline-none transition-all input-glass" />
                </div>
              </div>
            </div>

            {updateMode === 'all' && (
              <div className="space-y-2 animate-fadeIn">
                <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Repeat</span>
                <select value={recurrence} onChange={(e) => setRecurrence(e.target.value)} className="w-full text-sm rounded-xl px-4 py-3 outline-none appearance-none cursor-pointer transition-all input-glass">
                  <option value="none">Does not repeat</option><option value="daily">Daily / Custom Days</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
                </select>

                {(recurrence === 'daily' || recurrence === 'custom') && (
                  <div className="pt-3 animate-fadeIn">
                    <div className="flex items-center justify-between gap-1 px-1">
                      {DAYS_OF_WEEK.map((day, index) => {
                        const isActive = selectedDays.includes(day.id);
                        return (
                          <button 
                            key={`${day.id}-${index}`} 
                            onClick={() => toggleDay(day.id)} 
                            className="w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center text-sm font-medium transition-all" 
                            style={isActive ? { background: 'var(--color-accent-gradient)', color: 'var(--color-bg-base)', boxShadow: 'var(--shadow-sm)' } : { background: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
                          >
                            {day.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Location</span>
              <div className="relative">
                <input type="text" value={location} onChange={(e) => { setLocation(e.target.value); setShowPredictions(true); }} placeholder="Add Location" className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass" />
                {showPredictions && predictions.length > 0 && (
                  <div 
                    className="absolute z-[60] top-full left-0 w-full mt-1 rounded-xl overflow-hidden transition-colors duration-500"
                    style={{
                      background: 'var(--color-bg-glass-strong)',
                      backdropFilter: 'blur(12px)',
                      WebkitBackdropFilter: 'blur(12px)',
                      border: '1px solid var(--color-border)',
                      boxShadow: 'var(--shadow-md)',
                    }}
                  >
                    {predictions.map((p, i) => (
                      <button key={i} className="w-full text-left px-4 py-3 text-sm transition-colors" style={{ borderBottom: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }} onClick={() => { setLocation(p.description); setPredictions([]); setShowPredictions(false); }}>{p.description}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Travel Time</span>
              <select value={showTravelCalculator ? "auto" : travelTime} onChange={(e) => { if (e.target.value === "auto") { setShowTravelCalculator(true); setTravelTime("0"); } else { setShowTravelCalculator(false); setTravelTime(e.target.value); } }} className="w-full text-sm rounded-xl px-4 py-3 outline-none appearance-none cursor-pointer transition-all input-glass">
                <option value="0">None</option><option value="15">15 minutes</option><option value="20">20 minutes</option><option value="30">30 minutes</option><option value="45">45 minutes</option><option value="60">1 hour</option><option value="90">1.5 hours</option><option value="auto">Calculate automatically...</option>
                {!["0", "15", "20", "30", "45", "60", "90", "auto"].includes(travelTime) && (<option value={travelTime}>{travelTime} mins (Calculated)</option>)}
              </select>

              {showTravelCalculator && (
                <div className="pt-3 pb-1 animate-in fade-in slide-in-from-top-2 duration-200 space-y-3">
                  <div className="flex p-1 rounded-xl w-full shadow-inner transition-colors duration-500" style={{ background: 'var(--color-bg-subtle)' }}>
                    {[{ id: 'driving', icon: <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12" /> }, { id: 'transit', icon: <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-15-11.25V18m12-9.75V18m-11.25-6h10.5m-10.5 3h10.5M5.25 6h13.5c.828 0 1.5.672 1.5 1.5v12H3.75v-12c0-.828.672-1.5 1.5-1.5zM12 4.5v.008" /> }, { id: 'walking', icon: <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" /> }, { id: 'cycling', icon: <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 19.5a2.25 2.25 0 100-4.5 2.25 2.25 0 000 4.5zM15.75 19.5a2.25 2.25 0 100-4.5 2.25 2.25 0 000 4.5zM9 15l2.625-3.375M15 15l-2.625-3.375M11.625 11.625L9.375 9H6.75M11.625 11.625h3.75" /> }].map(mode => (
                      <button 
                        key={mode.id} 
                        onClick={() => setTravelMode(mode.id as any)} 
                        className={`flex-1 py-2 rounded-lg flex justify-center transition-all`}
                        style={travelMode === mode.id ? { background: 'var(--color-surface)', boxShadow: 'var(--shadow-sm)', color: 'var(--color-accent-primary)' } : { color: 'var(--color-text-secondary)' }}
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>{mode.icon}</svg>
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-col gap-2 relative">
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input type="text" value={travelOrigin} onChange={(e) => { setTravelOrigin(e.target.value); setShowOriginPredictions(true); }} placeholder="Starting location (e.g. Home, Office)" className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass" />
                      <button onClick={handleCalculateTravel} disabled={isCalculatingTravel || !travelOrigin || !location} className="whitespace-nowrap px-5 py-3 text-sm font-semibold rounded-xl transition-all disabled:opacity-50 btn-primary">{isCalculatingTravel ? "Calculating..." : "Calculate"}</button>
                    </div>
                    {showOriginPredictions && originPredictions.length > 0 && (
                      <div 
                        className="absolute z-[70] top-full left-0 w-full mt-1 rounded-xl overflow-hidden transition-colors duration-500"
                        style={{
                          background: 'var(--color-bg-glass-strong)',
                          backdropFilter: 'blur(12px)',
                          WebkitBackdropFilter: 'blur(12px)',
                          border: '1px solid var(--color-border)',
                          boxShadow: 'var(--shadow-md)',
                        }}
                      >
                        {originPredictions.map((p, i) => (
                          <button key={i} className="w-full text-left px-4 py-3 text-sm transition-colors" style={{ borderBottom: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }} onClick={() => { setTravelOrigin(p.description); setOriginPredictions([]); setShowOriginPredictions(false); }}>{p.description}</button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Meeting Link</span>
              <input type="url" value={meetingLink} onChange={(e) => setMeetingLink(e.target.value)} placeholder="https://zoom.us/j/..." className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass" />
            </div>
            
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Calendar Account</span>
              <select value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value)} className="w-full text-sm rounded-xl px-4 py-3 outline-none appearance-none cursor-pointer transition-all input-glass">
                {linkedAccounts.map((acc, i) => (<option key={i} value={JSON.stringify(acc)}>{acc.email} ({acc.provider})</option>))}
              </select>
            </div>

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Category</span>
              <select value={category} onChange={(e) => setCategory(e.target.value)} className="w-full text-sm rounded-xl px-4 py-3 outline-none appearance-none cursor-pointer transition-all input-glass">
                <option value="">Auto-assign (AI)</option>
                <option value="DEEP_WORK">Deep Work</option>
                <option value="SHALLOW_WORK">Shallow Work</option>
                <option value="MEETING">Meeting</option>
                <option value="WORKOUT">Workout</option>
                <option value="SOCIAL">Social</option>
                <option value="LEISURE">Leisure</option>
                <option value="TRAVEL">Travel</option>
                <option value="MEAL">Meal</option>
              </select>
            </div>

            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Attachments</span>
              <div className="space-y-2">
                {existingAttachments.map((url, i) => (
                  <div key={i} className="flex items-center justify-between p-2.5 rounded-xl transition-colors duration-500" style={{ background: 'var(--color-bg-subtle)', border: '1px solid var(--color-border)' }}>
                    <span className="text-xs truncate max-w-[200px] transition-colors duration-200" style={{ color: 'var(--color-accent-primary)' }}>{url.split('/').pop()}</span>
                    <button onClick={() => setExistingAttachments(existingAttachments.filter((_, idx) => idx !== i))} className="transition-colors font-medium hover:opacity-80" style={{ color: 'var(--color-danger)' }}>Remove</button>
                  </div>
                ))}
                <label className="inline-flex items-center gap-2 text-sm cursor-pointer mt-1 transition-colors font-medium" style={{ color: 'var(--color-accent-primary)' }}>
                  <span className="text-lg">+</span> Add File
                  <input type="file" multiple className="hidden" onChange={(e) => setAttachments(e.target.files)} />
                </label>
                {attachments && (<p className="text-[10px] transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>{attachments.length} new files selected</p>)}
              </div>
            </div>
            
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>Notes</span>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Add notes or details..." rows={4} className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all resize-none input-glass" />
            </div>

            {/* --- REMINDERS SECTION --- */}
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
                      <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded transition-colors duration-200" style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text-secondary)' }}>Active</span>
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
                      key={idx} 
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
                      <input type="date" className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass" value={newRemDate} onChange={(e) => setNewRemDate(e.target.value)} />
                      <input type="time" className="w-full text-sm rounded-xl px-4 py-3 outline-none transition-all input-glass" value={newRemTime} onChange={(e) => setNewRemTime(e.target.value)} />
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
                  + Create new alert for this event
                </button>
              )}
            </div>

          </div>
        </div>

        {editEvent && (
          <div 
            className="px-6 py-4 flex justify-center mt-auto transition-colors duration-500"
            style={{
              background: 'var(--color-bg-subtle)',
              borderTop: '1px solid var(--color-border-subtle)',
            }}
          >
            <button onClick={handleDelete} disabled={isDeleting || isSaving} className="font-medium flex items-center gap-2 transition-colors disabled:opacity-50 hover:opacity-80" style={{ color: 'var(--color-danger)' }}>
              {isDeleting ? "Deleting..." : "Delete Event"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}