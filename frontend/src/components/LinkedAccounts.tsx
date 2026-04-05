"use client";

import { useState, useEffect } from "react";
import { doc, getDoc } from "firebase/firestore";
import { db } from "../lib/firebase";
import { LinkedAccount } from "../types";
import { Browser } from '@capacitor/browser';
import { App as CapacitorApp } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';
import { fetchWithRetry } from "@/lib/fetchUtils";

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

interface LinkedAccountsProps {
  userId: string;
  onBack: () => void;
}

export default function LinkedAccounts({ userId, onBack }: LinkedAccountsProps) {
  const [accounts, setAccounts] = useState<LinkedAccount[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState<string | null>(null);

  useEffect(() => {
    fetchAccounts();

    const authListener = CapacitorApp.addListener('appUrlOpen', async (data) => {
      if (data.url.includes('api/auth') || data.url.includes('settings') || data.url.includes('callback')) {
        if (Capacitor.isNativePlatform()) {
          await Browser.close();
        }
        await fetchAccounts();
      }
    });

    return () => {
      authListener.then(listener => listener.remove());
    };
  }, [userId]);

  const fetchAccounts = async () => {
    if (!userId) return;
    try {
      const userRef = doc(db, "users", userId);
      const userSnap = await getDoc(userRef);
      if (userSnap.exists()) {
        setAccounts(userSnap.data().linked_accounts || []);
      }
    } catch (error) {
      console.error("Failed to load accounts:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemoveAccount = async (emailToRemove: string, providerToRemove: string) => {
    if (!userId) return;
    setIsProcessing(emailToRemove);
    
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/calendar/disconnect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          email: emailToRemove,
          provider: providerToRemove
        }),
        timeoutMs: 8000
      });

      if (res.ok) {
        setAccounts(prev => prev.filter(acc => acc.email !== emailToRemove || acc.provider !== providerToRemove));
      } else {
        console.error("Backend failed to disconnect the account.");
      }
    } catch (error) {
      console.error("Failed to remove account:", error);
    } finally {
      setIsProcessing(null);
    }
  };

  const handleAddAccount = async (provider: 'google' | 'outlook') => {
    const isNative = Capacitor.isNativePlatform();
    let popupWindow: Window | null = null;

    if (!isNative) {
      popupWindow = window.open("", "_blank", "width=500,height=600");
      if (!popupWindow) {
        alert("Please allow popups for this site to connect your account.");
        return;
      }
      popupWindow.document.write("Loading secure connection...");
    }

    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/auth/${provider}/login?user_id=${userId}`, {
        method: "GET",
        timeoutMs: 8000
      });
      const data = await res.json();
      
      if (data.url) {
        if (isNative) {
          await Browser.open({ url: data.url });
        } else if (popupWindow) {
          popupWindow.location.href = data.url;
        }

        const checkInterval = setInterval(async () => {
           const updatedRef = doc(db, "users", userId);
           const updatedSnap = await getDoc(updatedRef);
           if (updatedSnap.exists()) {
             const updatedData = updatedSnap.data().linked_accounts || [];
             if (updatedData.length > accounts.length) {
                setAccounts(updatedData);
                clearInterval(checkInterval);
                if (isNative) {
                  await Browser.close(); 
                } else if (popupWindow) {
                  popupWindow.close();
                }
             }
           }
        }, 2000);
        
        setTimeout(() => {
          clearInterval(checkInterval);
          if (popupWindow && !popupWindow.closed) {
            popupWindow.close();
          }
        }, 120000);
      } else {
        if (popupWindow) popupWindow.close();
      }
    } catch (error) {
      console.error(`Failed to initiate ${provider} login:`, error);
      if (popupWindow) popupWindow.close();
    }
  };

  return (
    <div className="min-h-screen font-sans flex flex-col pb-32 bg-transparent transition-colors duration-500">
      
      <div
        className="sticky top-0 z-10 px-4 pb-3 flex items-center justify-between transition-colors duration-200"
        style={{ 
          paddingTop: "calc(env(safe-area-inset-top, 24px) + 50px)",
          background: 'var(--color-bg-glass-strong)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[16px] font-semibold transition-colors active:opacity-50"
          style={{ color: 'var(--color-accent-primary)' }}
        >
          <span className="text-2xl leading-none">‹</span> Settings
        </button>

        <span className="text-[15px] font-semibold truncate px-4 transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
          Linked Accounts
        </span>

        <div className="w-16"></div>
      </div>

      <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-10 animate-fadeIn">
        
        <div className="space-y-2 text-center md:text-left">
          <h2 className="text-3xl font-extrabold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
            Calendar Connections
          </h2>
          <p className="text-sm max-w-xl mx-auto md:mx-0 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
            Manage the external calendars synced with your AI assistant. You can connect multiple accounts from different providers.
          </p>
        </div>

        <div className="space-y-4">
          <h3 className="text-[11px] font-black uppercase tracking-[0.15em] px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
            Active Connections
          </h3>

          {isLoading ? (
            <div 
              className="p-8 rounded-2xl text-center flex items-center justify-center transition-colors duration-200"
              style={{
                background: 'var(--color-bg-glass)',
                border: '1px solid var(--color-border)',
              }}
            >
              <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--color-accent-primary)', borderTopColor: 'transparent' }}></div>
            </div>
          ) : accounts.length === 0 ? (
            <div 
              className="p-8 rounded-2xl text-center transition-colors duration-200"
              style={{
                background: 'var(--color-bg-glass)',
                border: '2px dashed var(--color-border-accent)',
              }}
            >
              <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>No accounts connected.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {accounts.map((account) => (
                <div 
                  key={`${account.provider}-${account.email}`} 
                  className="p-4 sm:p-5 rounded-2xl flex items-center justify-between gap-4 transition-all duration-200"
                  style={{
                    background: 'var(--color-bg-glass)',
                    backdropFilter: 'blur(12px)',
                    WebkitBackdropFilter: 'blur(12px)',
                    border: '1px solid var(--color-border)',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  <div className="flex items-center gap-4 overflow-hidden">
                    <div 
                      className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors duration-200"
                      style={{
                        background: 'var(--color-bg-subtle)',
                        border: '1px solid var(--color-border-subtle)',
                      }}
                    >
                      {account.provider === 'google' ? (
                        <svg className="w-5 h-5" viewBox="0 0 24 24">
                          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5" viewBox="0 0 24 24">
                          <path fill="#f25022" d="M1 1h10v10H1z" />
                          <path fill="#7fba00" d="M13 1h10v10H13z" />
                          <path fill="#00a4ef" d="M1 13h10v10H1z" />
                          <path fill="#ffb900" d="M13 13h10v10H13z" />
                        </svg>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-[15px] font-medium truncate leading-snug transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>
                        {account.email}
                      </p>
                      <p className="text-xs capitalize mt-0.5 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                        {account.provider} Calendar
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={() => handleRemoveAccount(account.email, account.provider)}
                    disabled={isProcessing === account.email}
                    className="flex-shrink-0 p-2 sm:px-4 sm:py-2 rounded-lg transition-all flex items-center gap-2 hover:bg-red-500/10"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    {isProcessing === account.email ? (
                      <div className="w-4 h-4 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--color-danger)', borderTopColor: 'transparent' }}></div>
                    ) : (
                      <>
                        <span className="hidden sm:inline text-sm font-medium">Remove</span>
                        <svg className="w-5 h-5 sm:w-4 sm:h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                      </>
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4 pt-4">
          <h3 className="text-[11px] font-black uppercase tracking-[0.15em] px-1 transition-colors duration-200" style={{ color: 'var(--color-text-tertiary)' }}>
            Add Connection
          </h3>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button 
              onClick={() => handleAddAccount('google')}
              className="flex items-center justify-center gap-3 p-4 rounded-xl transition-all group active:scale-[0.98]"
              style={{
                background: 'var(--color-bg-glass)',
                border: '1px solid var(--color-border)',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              <span className="font-medium transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Connect Google</span>
            </button>

            <button 
              onClick={() => handleAddAccount('outlook')}
              className="flex items-center justify-center gap-3 p-4 rounded-xl transition-all group active:scale-[0.98]"
              style={{
                background: 'var(--color-bg-glass)',
                border: '1px solid var(--color-border)',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#f25022" d="M1 1h10v10H1z" />
                <path fill="#7fba00" d="M13 1h10v10H13z" />
                <path fill="#00a4ef" d="M1 13h10v10H1z" />
                <path fill="#ffb900" d="M13 13h10v10H13z" />
              </svg>
              <span className="font-medium transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Connect Outlook</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}