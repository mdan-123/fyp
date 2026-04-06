"use client";

import { useState, useEffect } from "react";
import { signOut } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useAuth } from "@/lib/AuthContext";
import NavigationBar from "@/components/NavigationBar";
import OptimisationPreferences from "@/components/OptimisationPreferences";
import LinkedAccounts from "@/components/LinkedAccounts"; 
import CalendarSafety from "@/components/CalendarSafety";
import { App as CapacitorApp } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';
import VocabularySettings from "@/components/VocabularySettings";
import RegionTimezone from "@/components/RegionTimezone";
import SecuritySettings from "@/components/SecuritySettings";

const SETTINGS_GROUPS = [
  {
    id: "group-algorithm",
    title: "Optimisation",
    items: [
      { 
        id: "preferences", 
        label: "Optimisation Preferences", 
        icon: (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
          </svg>
        ) 
      },

      { 
        id: "vocabulary", 
        label: "Dictionary & Aliases", 
        icon: (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
          </svg>
        ) 
      },
    ]
  },
  {
    id: "group-calendar",
    title: "Calendar",
    items: [
      { 
        id: "calendar-safety", 
        label: "Safety & Rollback", 
        icon: (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
          </svg>
        ) 
      },
    ]
  },
  {
    id: "group-general",
    title: "General",
    items: [
      { 
        id: "linked-accounts", 
        label: "Linked Accounts", 
        icon: (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
          </svg>
        ) 
      },
      { 
        id: "security", 
        label: "Security & Login", 
        icon: (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
          </svg>
        ) 
      },
      { 
        id: "region-timezone", 
        label: "Region & Timezone", 
        icon: (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
          </svg>
        ) 
      },
      { 
        id: "notifications", 
        label: "Notifications", 
        icon: (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
          </svg>
        ) 
      },
    ]
  }
];

export default function SettingsPage() {
  const { user, loading } = useAuth(); 
  const [activeSetting, setActiveSetting] = useState<string | null>(null);
  const [isMobileDetailOpen, setIsMobileDetailOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [isDarkMode, setIsDarkMode] = useState(false);

  useEffect(() => {
    if (globalThis.window !== undefined) {
      const isDark = document.body.classList.contains('dark') || document.documentElement.classList.contains('dark') || localStorage.getItem('theme') === 'dark';
      setIsDarkMode(isDark);
      if (isDark) {
        document.documentElement.classList.add('dark');
        document.body.classList.add('dark');
      }
    }
  }, []);

  const toggleTheme = () => {
    setIsDarkMode((prev) => {
      const newTheme = !prev;
      if (newTheme) {
        document.documentElement.classList.add('dark');
        document.body.classList.add('dark');
        localStorage.setItem('theme', 'dark');
      } else {
        document.documentElement.classList.remove('dark');
        document.body.classList.remove('dark');
        localStorage.setItem('theme', 'light');
      }
      return newTheme;
    });
  };

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !user) return;

    const appStateListener = CapacitorApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        setRefreshKey(prev => prev + 1); 
      }
    });

    return () => {
      appStateListener.then(listener => listener.remove());
    };
  }, [user]);

  const handleSelect = (id: string) => {
    setActiveSetting(id);
    setIsMobileDetailOpen(true);
  };

  const handleBack = () => {
    setIsMobileDetailOpen(false);
    setActiveSetting(null);
  };

  const handleLogout = async () => {
    try {
      await signOut(auth);
      globalThis.window.location.href = "/login"; 
    } catch (error) {
      console.error("Failed to log out:", error);
    }
  };

  const renderActiveComponent = () => {
    if (!user) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-slate-400 bg-transparent">
          <p>Please log in to view settings.</p>
        </div>
      );
    }

    switch (activeSetting) {
      case "preferences":
        return <OptimisationPreferences key={`pref-${refreshKey}`} userId={user.uid} onBack={handleBack} />;
      case "linked-accounts":
        return <LinkedAccounts key={`link-${refreshKey}`} userId={user.uid} onBack={handleBack} />;
      case "calendar-safety": 
        return <CalendarSafety key={`safe-${refreshKey}`} userId={user.uid} onBack={handleBack} />;
      case "region-timezone":
        return <RegionTimezone key={`tz-${refreshKey}`} userId={user.uid} onBack={handleBack} />;
      case "vocabulary":
        return <VocabularySettings key={`vocab-${refreshKey}`} userId={user.uid} onBack={handleBack} />;
      case "security":
        return <SecuritySettings key={`sec-${refreshKey}`} userId={user.uid} onBack={handleBack} />;
      default:
        return (
          <div className="flex flex-col items-center justify-center h-full bg-transparent animate-in fade-in">
             <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-colors duration-200"
                  style={{ background: 'var(--color-bg-glass)', border: '1px solid var(--color-border)' }}>
                <svg className="w-8 h-8 text-slate-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                </svg>
             </div>
            <p className="text-sm text-slate-400 dark:text-slate-500">Select a setting from the menu</p>
          </div>
        );
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center transition-colors duration-500" style={{ background: 'var(--color-bg-base)' }}>
        <div className="relative">
          <div className="absolute -inset-8 rounded-full bg-gradient-to-r from-indigo-500/20 via-violet-500/20 to-purple-500/20 blur-2xl animate-pulse" />
          <div className="relative w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
            <svg className="w-6 h-6 text-white animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
        </div>
      </div>
    );
  }

  if (isMobileDetailOpen && globalThis.window !== undefined && globalThis.window.innerWidth < 768) {
    return renderActiveComponent();
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row overflow-hidden relative bg-transparent">
      
      <div className="fixed inset-0 -z-10 transition-colors duration-500" style={{ background: 'var(--color-bg-base)' }} />
      
      <aside 
        className="w-full md:w-80 md:h-screen flex-shrink-0 flex flex-col justify-between md:border-r transition-colors duration-200"
        style={{ 
          paddingTop: 'calc(env(safe-area-inset-top, 24px) + 32px)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div>
          <div className="px-6 py-4">
            <h1 className="text-2xl font-bold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Settings</h1>
            <p className="text-sm mt-1 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Customise your experience</p>
          </div>
          
          <div className="p-4 space-y-6 overflow-y-auto scrollbar-hide">
            {SETTINGS_GROUPS.map((group) => (
              <div key={group.id} className="space-y-2">
                <h2 className="px-4 text-[10px] uppercase tracking-[0.15em] font-semibold transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>{group.title}</h2>
                <div 
                  className="rounded-2xl overflow-hidden transition-all duration-200"
                  style={{
                    background: 'var(--color-bg-glass)',
                    backdropFilter: 'blur(12px)',
                    border: '1px solid var(--color-border)',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  {group.items.map((item, index) => {
                    const isActive = activeSetting === item.id;
                    const isLast = index === group.items.length - 1;
                    
                    return (
                      <button
                        key={item.id}
                        onClick={() => handleSelect(item.id)}
                        className={`w-full flex items-center justify-between px-4 py-3.5 transition-all duration-200 text-left`}
                        style={{
                          background: isActive ? 'var(--color-surface-hover)' : 'transparent',
                          borderBottom: isLast ? 'none' : '1px solid var(--color-border-subtle)',
                        }}
                      >
                        <div className="flex items-center gap-3">
                          <span className="transition-colors duration-200" style={{ color: isActive ? 'var(--color-accent-primary)' : 'var(--color-text-tertiary)' }}>
                            {item.icon}
                          </span>
                          <span className="text-[15px] font-medium transition-colors duration-200" style={{ color: isActive ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)' }}>
                            {item.label}
                          </span>
                        </div>
                        <span className="text-lg md:hidden transition-colors duration-200" style={{ color: isActive ? 'var(--color-accent-primary)' : 'var(--color-text-tertiary)' }}>›</span>
                        {isActive && <div className="hidden md:block w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-accent-primary)' }}></div>}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="p-4 mb-24 md:mb-4 space-y-3">
          <button
            onClick={toggleTheme}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 rounded-xl transition-all duration-200 hover:scale-[1.01] active:scale-[0.99]"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            {isDarkMode ? (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} style={{ color: 'var(--color-accent-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} style={{ color: 'var(--color-accent-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
              </svg>
            )}
            <span className="text-[15px] font-semibold">{isDarkMode ? 'Light Mode' : 'Dark Mode'}</span>
          </button>

          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-4 py-3.5 rounded-xl transition-all duration-200 hover:scale-[1.01] active:scale-[0.99]"
            style={{
              background: 'var(--color-danger-bg)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-danger)',
            }}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
            </svg>
            <span className="text-[15px] font-semibold">Log out</span>
          </button>
        </div>
      </aside>

      <main className="flex-1 hidden md:block h-screen overflow-y-auto scrollbar-hide">
        {activeSetting ? (
          <div className="h-full">
            {renderActiveComponent()}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full">
            <div 
              className="w-20 h-20 rounded-2xl flex items-center justify-center mb-4 transition-all duration-200"
              style={{
                background: 'var(--color-bg-glass)',
                border: '1px solid var(--color-border)',
              }}
            >
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1} style={{ color: 'var(--color-text-tertiary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <p className="text-sm transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Select a setting to get started</p>
          </div>
        )}
      </main>

      <NavigationBar />
    </div>
  );
}