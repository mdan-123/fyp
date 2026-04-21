"use client";

import { useState, useEffect } from "react";
import { auth } from "@/lib/firebase";
import { Capacitor } from "@capacitor/core";
import { NativeBiometric } from "@capgo/capacitor-native-biometric";
import { startRegistration } from "@simplewebauthn/browser";
import { fetchWithRetry } from "@/lib/fetchUtils";

type SecuritySettingsProps = {
  userId: string;
  onBack: () => void;
};

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function SecuritySettings({ userId, onBack }: SecuritySettingsProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const [isNative, setIsNative] = useState(false);
  const [mobileEnabled, setMobileEnabled] = useState(false);
  const [passkeyEnabled, setPasskeyEnabled] = useState(false);

  useEffect(() => {
    setIsNative(Capacitor.isNativePlatform());
    fetchStatus();
  }, [userId]);

  const fetchStatus = async () => {
    setIsLoading(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/auth/biometrics/status/${userId}`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        timeoutMs: 8000,
      });
      if (res.ok) {
        const data = await res.json();
        setMobileEnabled(data.mobile_enabled);
        setPasskeyEnabled(data.passkey_enabled);
      }
    } catch (err) {
      console.error("Failed to load security status:", err);
      setError("Could not load your security settings.");
    } finally {
      setIsLoading(false);
    }
  };

  const clearMessages = () => {
    setError("");
    setSuccessMsg("");
  };

  // --- ENABLE FLOWS ---
  const handleEnableMobile = async () => {
    clearMessages();
    setIsProcessing(true);
    try {
      const available = await NativeBiometric.isAvailable();
      if (!available) throw new Error("Biometrics not supported on this device.");

      await NativeBiometric.verifyIdentity({
        reason: "Verify your identity to enable biometric login",
      });

      const currentUser = auth.currentUser;
      const res = await fetchWithRetry(`${API_BASE_URL}/api/auth/register/mobile-biometrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          user_id: userId, 
          email: currentUser?.email,
          has_mobile_biometrics: true 
        }),
      });

      if (res.ok) {
        setMobileEnabled(true);
        setSuccessMsg("Face ID / Touch ID enabled successfully.");
      } else {
        throw new Error("Failed to update database.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to enable biometrics.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleEnablePasskey = async () => {
    clearMessages();
    setIsProcessing(true);
    try {
      const currentUser = auth.currentUser;
      
      const startRes = await fetchWithRetry(`${API_BASE_URL}/api/auth/register/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, email: currentUser?.email }),
      });
      
      const options = await startRes.json();
      const credential = await startRegistration(options);

      const verifyRes = await fetchWithRetry(`${API_BASE_URL}/api/auth/register/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, credential }),
      });

      if (verifyRes.ok) {
        setPasskeyEnabled(true);
        setSuccessMsg("Passkey created successfully.");
      } else {
        throw new Error("Failed to verify passkey.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to create passkey.");
    } finally {
      setIsProcessing(false);
    }
  };

  // --- DISABLE FLOWS ---
  const handleDisableMobile = async () => {
    if (!window.confirm("Are you sure you want to disable biometric login? You will need to use your password next time.")) return;
    
    clearMessages();
    setIsProcessing(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/auth/biometrics/mobile/${userId}`, {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        setMobileEnabled(false);
        setSuccessMsg("Biometric login disabled.");
      } else throw new Error("Failed to disable.");
    } catch (err: any) {
      setError(err.message || "Could not disable biometrics.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDisablePasskey = async () => {
    if (!window.confirm("Are you sure you want to remove your passkeys? You will need to use your password next time.")) return;
    
    clearMessages();
    setIsProcessing(true);
    try {
      const token = await auth.currentUser?.getIdToken();
      const res = await fetchWithRetry(`${API_BASE_URL}/api/auth/biometrics/passkeys/${userId}`, {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        setPasskeyEnabled(false);
        setSuccessMsg("Passkeys removed successfully.");
      } else throw new Error("Failed to remove passkeys.");
    } catch (err: any) {
      setError(err.message || "Could not remove passkeys.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col pb-36 animate-in fade-in" style={{ background: 'transparent' }}>
      
      {/* Header */}
      <div
        className="sticky top-0 z-10 px-4 py-3 flex items-center justify-between"
        style={{ 
          paddingTop: "calc(env(safe-area-inset-top, 20px) + 8px)",
          background: 'var(--color-bg-glass)',
          backdropFilter: 'blur(var(--blur-lg))',
          WebkitBackdropFilter: 'blur(var(--blur-lg))',
          borderBottom: '1px solid var(--color-border)'
        }}
      >
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[16px] font-semibold transition-colors active:opacity-50"
          style={{ color: 'var(--color-accent-primary)' }}
        >
          <span className="text-2xl leading-none">‹</span> Settings
        </button>
        <span className="text-[15px] font-bold truncate px-4" style={{ color: 'var(--color-text-primary)' }}>
          Security
        </span>
        <div className="w-16"></div>
      </div>

      <div className="flex-1 px-4 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-8">
        
        {/* Intro */}
        <div className="space-y-2 text-center md:text-left">
          <h2 className="text-3xl font-extrabold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>
            Security & Login
          </h2>
          <p className="text-sm max-w-xl" style={{ color: 'var(--color-text-secondary)' }}>
            Manage how you sign in to your account. Enable fast, passwordless login using your device's built-in security.
          </p>
        </div>

        {error && (
          <div className="p-3 rounded-xl flex items-center gap-2 text-sm" style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)', border: '1px solid var(--color-danger)' }}>
            <span className="font-bold">Error:</span> {error}
          </div>
        )}

        {successMsg && (
          <div className="p-3 rounded-xl flex items-center gap-2 text-sm" style={{ background: 'var(--color-success-bg)', color: 'var(--color-success)', border: '1px solid var(--color-success)' }}>
            <span className="font-bold">Success:</span> {successMsg}
          </div>
        )}

        {isLoading ? (
           <div className="flex justify-center p-10">
             <div className="w-8 h-8 border-4 border-t-transparent rounded-full animate-spin" style={{ borderColor: 'var(--color-border-accent)', borderTopColor: 'var(--color-accent-primary)' }}></div>
           </div>
        ) : (
          <div 
            className="rounded-3xl p-6 transition-all duration-500 shadow-sm"
            style={{
              background: 'var(--color-bg-glass)',
              border: '1px solid var(--color-border)',
              backdropFilter: 'blur(16px)'
            }}
          >
            <div className="flex items-center gap-4 mb-6">
              <div 
                className="w-12 h-12 rounded-xl flex items-center justify-center"
                style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border-subtle)' }}
              >
                {isNative ? (
                  <svg className="w-6 h-6" style={{ color: 'var(--color-accent-primary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3" />
                  </svg>
                ) : (
                  <svg className="w-6 h-6" style={{ color: 'var(--color-accent-primary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
                  </svg>
                )}
              </div>
              <div>
                <h3 className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  {isNative ? "Face ID / Touch ID" : "Device Passkey"}
                </h3>
                <p className="text-xs font-medium uppercase tracking-widest mt-1" style={{ color: (isNative ? mobileEnabled : passkeyEnabled) ? 'var(--color-success)' : 'var(--color-text-tertiary)' }}>
                  Status: {(isNative ? mobileEnabled : passkeyEnabled) ? "Active" : "Disabled"}
                </p>
              </div>
            </div>

            <div className="pt-2 border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
              {isNative ? (
                /* MOBILE UI */
                mobileEnabled ? (
                  <button
                    onClick={handleDisableMobile}
                    disabled={isProcessing}
                    className="mt-4 w-full md:w-auto px-6 py-2.5 rounded-xl text-sm font-bold transition-all disabled:opacity-50"
                    style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)', border: '1px solid var(--color-danger)' }}
                  >
                    {isProcessing ? "Processing..." : "Disable Biometrics"}
                  </button>
                ) : (
                  <button
                    onClick={handleEnableMobile}
                    disabled={isProcessing}
                    className="mt-4 w-full md:w-auto px-6 py-2.5 rounded-xl text-sm font-bold transition-all disabled:opacity-50 btn-primary"
                  >
                    {isProcessing ? "Processing..." : "Enable Face ID / Touch ID"}
                  </button>
                )
              ) : (
                /* DESKTOP UI */
                passkeyEnabled ? (
                  <button
                    onClick={handleDisablePasskey}
                    disabled={isProcessing}
                    className="mt-4 w-full md:w-auto px-6 py-2.5 rounded-xl text-sm font-bold transition-all disabled:opacity-50"
                    style={{ background: 'var(--color-danger-bg)', color: 'var(--color-danger)', border: '1px solid var(--color-danger)' }}
                  >
                    {isProcessing ? "Processing..." : "Remove Passkey"}
                  </button>
                ) : (
                  <button
                    onClick={handleEnablePasskey}
                    disabled={isProcessing}
                    className="mt-4 w-full md:w-auto px-6 py-2.5 rounded-xl text-sm font-bold transition-all disabled:opacity-50 btn-primary"
                  >
                    {isProcessing ? "Creating..." : "Create Passkey"}
                  </button>
                )
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}