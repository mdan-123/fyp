"use client";

import React, { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { collection, query, where, onSnapshot } from "firebase/firestore";
import { onAuthStateChanged } from "firebase/auth";
import { auth, db } from "@/lib/firebase";
import { Capacitor } from "@capacitor/core";
import { LocalNotifications } from "@capacitor/local-notifications";
import { BackgroundGeolocation } from '@capgo/background-geolocation'; // The modern Capgo plugin
import { fetchWithRetry } from "@/lib/fetchUtils"; 

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export interface LocationData {
  lat: number;
  lng: number;
  radius: number;
  trigger_on: "entry" | "exit";
}

export interface Reminder {
  id: string;
  title: string;
  body?: string | null;
  type: "event" | "task" | "standalone";
  reference_id?: string | null;
  trigger_type: "time" | "location" | "time_and_location";
  trigger_time?: string | null;
  location_data?: LocationData | null;
  status: "pending" | "delivered" | "dismissed" | "missed";
}

interface ToastNotification {
  id: string;
  reminderId: string;
  title: string;
  body?: string | null;
  type: string;
}

interface NotificationContextType {
  pendingReminders: Reminder[];
  activeToasts: ToastNotification[];
  dismissToast: (toastId: string, reminderId: string) => void;
}

const NotificationContext = createContext<NotificationContextType>({
  pendingReminders: [],
  activeToasts: [],
  dismissToast: () => {},
});

export const useNotifications = () => useContext(NotificationContext);

const hashStringToNumber = (str: string) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; 
  }
  return Math.abs(hash);
};

const getDistance = (lat1: number, lon1: number, lat2: number, lon2: number) => {
  const R = 6371e3; 
  const φ1 = lat1 * Math.PI / 180;
  const φ2 = lat2 * Math.PI / 180;
  const Δφ = (lat2 - lat1) * Math.PI / 180;
  const Δλ = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
};

export default function NotificationProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<string | null>(null);
  const [pendingReminders, setPendingReminders] = useState<Reminder[]>([]);
  const [activeToasts, setActiveToasts] = useState<ToastNotification[]>([]);

  // 1. Listen for Authentication
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setUserId(user ? user.uid : null);
    });
    return () => unsubscribe();
  }, []);

  // 2. Real-time Firestore Sync
  useEffect(() => {
    if (!userId) {
      setPendingReminders([]);
      return;
    }

    const q = query(
      collection(db, "users", userId, "reminders"),
      where("status", "==", "pending")
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const reminders: Reminder[] = [];
      snapshot.forEach((doc) => {
        reminders.push({ id: doc.id, ...doc.data() } as Reminder);
      });
      setPendingReminders(reminders);
    }, (error) => {
      console.error("Error syncing reminders:", error);
    });

    return () => unsubscribe();
  }, [userId]);

  // 3. Native iOS Time-Based Scheduling
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !userId) return;

    const synchroniseNativeNotifications = async () => {
      try {
        let permStatus = await LocalNotifications.checkPermissions();
        if (permStatus.display !== 'granted') {
          permStatus = await LocalNotifications.requestPermissions();
        }
        
        if (permStatus.display !== 'granted') return;

        const pending = await LocalNotifications.getPending();
        if (pending.notifications.length > 0) {
          await LocalNotifications.cancel(pending);
        }

        const now = new Date().getTime();
        
        const nativeNotifications = pendingReminders
          .filter(rem => rem.trigger_type === "time" && rem.trigger_time)
          .filter(rem => new Date(rem.trigger_time!).getTime() > now)
          .map(rem => {
            const numericId = hashStringToNumber(rem.id);

            return {
              id: numericId,
              title: rem.title,
              body: rem.body || "You have a scheduled reminder.",
              schedule: { at: new Date(rem.trigger_time!) },
              extra: { reminderId: rem.id },
              sound: "default",
            };
          });

        if (nativeNotifications.length > 0) {
          await LocalNotifications.schedule({ notifications: nativeNotifications });
        }
      } catch (error) {
        console.error("Failed to synchronise native notifications:", error);
      }
    };

    synchroniseNativeNotifications();
  }, [pendingReminders, userId]);

  // 4. Native iOS Location Geofencing (Capgo SPM Version)
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !userId) return;

    let isSubscribed = true;

    const setupGeofences = async () => {
      try {
        const locationReminders = pendingReminders.filter(
          rem => (rem.trigger_type === "location" || rem.trigger_type === "time_and_location") && rem.location_data
        );

        // If there are no location reminders, gracefully shut down the native tracker to save battery
        if (locationReminders.length === 0) {
          await BackgroundGeolocation.stop();
          return;
        }

        // Wipe the old session to ensure clean tracking memory
        await BackgroundGeolocation.stop();
        if (!isSubscribed) return;

        // Start the single master Capgo watcher
        await BackgroundGeolocation.start(
          {
            backgroundMessage: "Monitoring your geofences for reminders.",
            backgroundTitle: "Active Reminders",
            requestPermissions: true, // Automatically handles native permissions
            stale: false,
          },
          async (location: any, error: any) => {
            if (error) return console.error(error);
            if (!location) return;

            // Loop through all active location reminders and check them against current coordinates
            for (const rem of locationReminders) {
              const locData = rem.location_data!;
              
              const distance = getDistance(
                location.latitude,
                location.longitude,
                locData.lat,
                locData.lng
              );

              // Condition A: Geofence Breach Check
              let isTriggered = false;
              if (locData.trigger_on === "entry" && distance <= locData.radius) {
                isTriggered = true;
              } else if (locData.trigger_on === "exit" && distance > locData.radius) {
                isTriggered = true;
              }

              // Condition B: The Time-Gate Check
              let timeConditionMet = true;
              if (rem.trigger_type === "time_and_location" && rem.trigger_time) {
                const targetTime = new Date(rem.trigger_time).getTime();
                if (Date.now() < targetTime) {
                  timeConditionMet = false;
                }
              }

              // Fire Notification
              if (isTriggered && timeConditionMet) {
                await LocalNotifications.schedule({
                  notifications: [{
                    id: hashStringToNumber(rem.id + "_loc"),
                    title: rem.title,
                    body: rem.body || "You have arrived at your destination.",
                    schedule: { at: new Date(Date.now() + 1000) }, // Fire immediately
                    extra: { reminderId: rem.id },
                    sound: "default",
                  }]
                });

                markAsDelivered(rem.id);
              }
            }
          }
        );
      } catch (error) {
        console.error("Geofence setup failed:", error);
      }
    };

    setupGeofences();

    // Cleanup: Always stop the native tracker when the component unmounts or user logs out
    return () => {
      isSubscribed = false;
      BackgroundGeolocation.stop().catch(console.error);
    };
  }, [pendingReminders, userId]); 

  // 5. Native iOS Action Listener (Dismissal Loop)
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !userId) return;

    const listener = LocalNotifications.addListener('localNotificationActionPerformed', (notificationAction) => {
      const reminderId = notificationAction.notification.extra?.reminderId;
      if (reminderId) {
        markAsDelivered(reminderId);
      }
    });

    return () => {
      listener.then(sub => sub.remove());
    };
  }, [userId]);

  // 6. The Ticking Clock for Web Delivery (Foreground)
  useEffect(() => {
    if (pendingReminders.length === 0 || !userId) return;

    const checkAlarms = () => {
      const now = new Date().getTime();
      const triggeredWithToast: Reminder[] = [];
      const triggeredSilently: Reminder[] = [];

      pendingReminders.forEach((reminder) => {
        if (
          (reminder.trigger_type === "time" || reminder.trigger_type === "time_and_location") &&
          reminder.trigger_time
        ) {
          const triggerTime = new Date(reminder.trigger_time).getTime();
          
          if (triggerTime <= now) {
            // The 2-Minute Rule
            if (now - triggerTime > 2 * 60 * 1000) {
              triggeredSilently.push(reminder);
            } else {
              triggeredWithToast.push(reminder);
            }
          }
        }
      });

      if (triggeredWithToast.length > 0) {
        triggeredWithToast.forEach((rem) => {
          setActiveToasts((prev) => [
            ...prev,
            { id: `toast_${Date.now()}_${rem.id}`, reminderId: rem.id, title: rem.title, body: rem.body, type: rem.type }
          ]);
          markAsDelivered(rem.id);
        });
      }

      if (triggeredSilently.length > 0) {
        triggeredSilently.forEach((rem) => {
          markAsDelivered(rem.id);
        });
      }
    };

    const intervalId = setInterval(checkAlarms, 10000); 
    checkAlarms(); 

    return () => clearInterval(intervalId);
  }, [pendingReminders, userId]);

  const markAsDelivered = async (reminderId: string) => {
    if (!userId) return;
    try {
      await fetchWithRetry(`${API_BASE_URL}/api/reminders/update`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: reminderId, user_id: userId, status: "delivered" }),
        timeoutMs: 8000
      });
    } catch (error) {
      console.error("Failed to mark reminder as delivered", error);
    }
  };

  const dismissToast = async (toastId: string, reminderId: string) => {
    setActiveToasts((prev) => prev.filter((t) => t.id !== toastId));
    
    if (!userId) return;
    try {
      await fetchWithRetry(`${API_BASE_URL}/api/reminders/update`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: reminderId, user_id: userId, status: "dismissed" }),
        timeoutMs: 8000
      });
    } catch (error) {
      console.error("Failed to dismiss reminder", error);
    }
  };

  return (
    <NotificationContext.Provider value={{ pendingReminders, activeToasts, dismissToast }}>
      {children}
      
      {/* Toast Render Portal - Moved down to clear Dynamic Island */}
      <div className="fixed top-0 right-0 z-[200] p-4 pt-16 sm:p-6 sm:pt-20 flex flex-col gap-3 pointer-events-none mt-[env(safe-area-inset-top,0px)]">
        {activeToasts.map((toast) => (
          <div 
            key={toast.id} 
            className="w-full sm:w-80 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 pointer-events-auto animate-in slide-in-from-top-10 fade-in duration-300 flex items-start gap-3"
          >
            <div className="flex-shrink-0 w-10 h-10 bg-indigo-50 rounded-full flex items-center justify-center text-indigo-600">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
              </svg>
            </div>
            <div className="flex-1 min-w-0 pt-0.5">
              <p className="text-sm font-bold text-slate-900 truncate">{toast.title}</p>
              {toast.body && <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{toast.body}</p>}
              <div className="flex items-center gap-3 mt-3">
                <button 
                  onClick={() => dismissToast(toast.id, toast.reminderId)}
                  className="text-xs font-bold text-indigo-600 hover:text-indigo-800 transition-colors"
                >
                  Acknowledge
                </button>
              </div>
            </div>
            <button 
              onClick={() => setActiveToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              className="text-slate-400 hover:text-slate-600 transition-colors flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </NotificationContext.Provider>
  );
}