"use client";

import { useState, useEffect } from "react";
import { auth } from "@/lib/firebase";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { startRegistration } from "@simplewebauthn/browser";
import { useRouter } from "next/navigation";
import { Capacitor } from "@capacitor/core";
import { NativeBiometric } from "@capgo/capacitor-native-biometric";
import Link from "next/link";
import { fetchWithRetry } from "@/lib/fetchUtils"; 

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export default function RegisterPage() {
  const router = useRouter();
  
  const [step, setStep] = useState(1); 
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);

  // New Timezone States 
  const [timezones, setTimezones] = useState<string[]>([]);
  const [selectedZone, setSelectedZone] = useState<string>("");
  const [currentTimePreview, setCurrentTimePreview] = useState<string>("");

  // Load timezones on mount
  useEffect(() => {
    try {
      const zones = Intl.supportedValuesOf("timeZone");
      setTimezones(zones);
      const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      setSelectedZone(browserZone);
    } catch (error) {
      console.error("Timezone API not supported", error);
      setTimezones(["Europe/London", "America/New_York", "UTC"]);
      setSelectedZone("UTC");
    }
  }, []);

  // Live preview clock
  useEffect(() => {
    if (!selectedZone) return;
    const updatePreview = () => {
      try {
        const timeString = new Intl.DateTimeFormat("en-GB", {
          timeZone: selectedZone,
          timeStyle: "medium",
          dateStyle: "full",
        }).format(new Date());
        setCurrentTimePreview(timeString);
      } catch (e) {
        setCurrentTimePreview("Invalid Timezone");
      }
    };
    updatePreview();
    const interval = setInterval(updatePreview, 1000);
    return () => clearInterval(interval);
  }, [selectedZone]);

  const handleEmailSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please fill out all fields.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setIsProcessing(true);
    setError("");

    try {
      await createUserWithEmailAndPassword(auth, email, password);
      // If successful, move to timezone setup
      setStep(2);
    } catch (err: any) {
      if (err.code === 'auth/email-already-in-use') {
        setError("This email is already in use. Please log in.");
      } else {
        setError(err.message || "Registration failed.");
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleTimezoneSubmit = async () => {
    setIsProcessing(true);
    setError("");

    try {
      const currentUser = auth.currentUser;
      if (!currentUser) throw new Error("User not authenticated.");

      const token = await currentUser.getIdToken();
      await fetchWithRetry(`${API_BASE_URL}/api/users/timezone`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({
          user_id: currentUser.uid,
          timezone: selectedZone,
        }),
        timeoutMs: 8000,
      });

      // Move to biometrics
      setStep(3);
    } catch (err: any) {
      console.error(err);
      setError("Failed to save timezone. Please try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const setupBiometrics = async () => {
    setIsProcessing(true);
    setError("");

    try {
      if (Capacitor.isNativePlatform()) {
        const available = await NativeBiometric.isAvailable();
        if (!available) throw new Error("Biometrics not supported on this device.");

        await NativeBiometric.verifyIdentity({
          reason: "Enable FaceID/TouchID for faster logins",
        });

        const currentUser = auth.currentUser;
        
        await fetchWithRetry(`${API_BASE_URL}/api/auth/register/mobile-biometrics`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            user_id: currentUser?.uid, 
            email: currentUser?.email,
            has_mobile_biometrics: true 
          }),
          timeoutMs: 10000
        });

        router.push("/");
      } else {
        const currentUser = auth.currentUser;
        
        const startRes = await fetchWithRetry(`${API_BASE_URL}/api/auth/register/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: currentUser?.uid, email: currentUser?.email }),
          timeoutMs: 8000
        });
        
        const options = await startRes.json();
        const credential = await startRegistration(options);

        await fetchWithRetry(`${API_BASE_URL}/api/auth/register/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: currentUser?.uid, credential }),
          timeoutMs: 10000
        });

        router.push("/");
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to link biometrics. You can set this up later.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div 
      className="flex min-h-screen items-center justify-center p-4 font-sans selection:bg-indigo-100 transition-colors duration-500"
      style={{ background: 'var(--color-bg-base)' }}
    >
      {/* Decorative Orbs handled entirely by body::before in global.css */}

      <div 
        className="relative w-full max-w-md rounded-3xl p-8 sm:p-10 animate-fadeIn transition-colors duration-500"
        style={{
          background: 'var(--color-bg-glass-strong)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid var(--color-border)',
          boxShadow: 'var(--shadow-xl), var(--shadow-inner-glow)',
        }}
      >
        {/* Progress indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {[1, 2, 3].map((s) => (
            <div
              key={s}
              className="transition-all duration-500"
              style={{
                width: step === s ? '24px' : '8px',
                height: '8px',
                borderRadius: '4px',
                background: step >= s 
                  ? 'var(--color-accent-gradient)'
                  : 'var(--color-bg-subtle)',
                boxShadow: step >= s ? 'var(--shadow-sm)' : 'none',
              }}
            />
          ))}
        </div>
        
        {/* --- STEP 1: EMAIL SIGNUP --- */}
        {step === 1 && (
          <div className="animate-fadeIn">
            <div className="flex flex-col items-center mb-8 space-y-3">
              <div 
                className="w-16 h-16 rounded-2xl flex items-center justify-center transition-colors duration-500"
                style={{
                  background: 'var(--color-accent-gradient)',
                  boxShadow: 'var(--shadow-glow)',
                }}
              >
                <svg className="w-8 h-8" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zM4 19.235v-.11a6.375 6.375 0 0112.75 0v.109A12.318 12.318 0 0110.374 21c-2.331 0-4.512-.645-6.374-1.766z" />
                </svg>
              </div>
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Create Account</h2>
              <p className="text-sm font-medium transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Start building your intelligent schedule</p>
            </div>

            {error && (
              <div 
                className="mb-6 p-4 rounded-xl flex items-center gap-3 animate-fadeIn transition-colors duration-200"
                style={{
                  background: 'var(--color-danger-bg)',
                  border: '1px solid var(--color-danger)',
                }}
              >
                <svg className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--color-danger)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <p className="text-sm font-medium" style={{ color: 'var(--color-danger)' }}>{error}</p>
              </div>
            )}

            <form className="space-y-6" onSubmit={handleEmailSignup}>
              <div className="space-y-5">
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider ml-1 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Email Address</label>
                  <input
                    type="email"
                    required
                    className="w-full text-sm rounded-xl px-4 py-3.5 outline-none transition-all duration-200"
                    style={{
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-text-primary)',
                      boxShadow: 'var(--shadow-inner-glow)',
                    }}
                    onFocus={(e) => {
                      e.target.style.borderColor = 'var(--color-accent-primary)';
                      e.target.style.boxShadow = '0 0 0 3px var(--color-accent-glow), var(--shadow-inner-glow)';
                    }}
                    onBlur={(e) => {
                      e.target.style.borderColor = 'var(--color-border)';
                      e.target.style.boxShadow = 'var(--shadow-inner-glow)';
                    }}
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={isProcessing}
                  />
                </div>
                
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-wider ml-1 transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>Password</label>
                  <input
                    type="password"
                    required
                    className="w-full text-sm rounded-xl px-4 py-3.5 outline-none transition-all duration-200"
                    style={{
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-text-primary)',
                      boxShadow: 'var(--shadow-inner-glow)',
                    }}
                    onFocus={(e) => {
                      e.target.style.borderColor = 'var(--color-accent-primary)';
                      e.target.style.boxShadow = '0 0 0 3px var(--color-accent-glow), var(--shadow-inner-glow)';
                    }}
                    onBlur={(e) => {
                      e.target.style.borderColor = 'var(--color-border)';
                      e.target.style.boxShadow = 'var(--shadow-inner-glow)';
                    }}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={isProcessing}
                  />
                </div>
              </div>
              
              <button
                type="submit"
                disabled={isProcessing || !email || !password}
                className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3.5 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] btn-primary"
              >
                {isProcessing ? (
                  <svg className="animate-spin h-4 w-4" style={{ color: 'var(--color-bg-base)' }} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <svg className="w-4 h-4" style={{ color: 'var(--color-bg-base)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12h15m0 0l-6.75-6.75M19.5 12l-6.75 6.75" />
                  </svg>
                )}
                {isProcessing ? "Creating Account..." : "Create Account"}
              </button>
            </form>

            <div className="text-center mt-8">
              <p className="text-sm transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                Already have an account?{" "}
                <Link href="/login" className="font-semibold transition-colors duration-200 hover:opacity-80" style={{ color: 'var(--color-accent-primary)' }}>
                  Sign in here
                </Link>
              </p>
            </div>
          </div>
        )}

        {/* --- STEP 2: REGION & TIMEZONE --- */}
        {step === 2 && (
          <div className="space-y-6 animate-fadeIn">
            <div className="flex flex-col items-center mb-6 space-y-4">
              <div 
                className="w-20 h-20 rounded-full flex items-center justify-center transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-glass)',
                  border: '4px solid var(--color-surface)',
                  boxShadow: 'var(--shadow-md)',
                }}
              >
                <svg className="w-10 h-10 transition-colors duration-200" style={{ color: 'var(--color-accent-primary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
                </svg>
              </div>
              <div className="text-center">
                <h2 className="text-2xl font-bold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Set Your Region</h2>
                <p className="text-sm mt-2 max-w-[280px] mx-auto leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                  So the AI knows exactly what "tomorrow" means for you.
                </p>
              </div>
            </div>

            {error && (
              <div 
                className="mb-4 p-4 rounded-xl flex items-start gap-2 text-left animate-fadeIn transition-colors duration-200"
                style={{
                  background: 'var(--color-danger-bg)',
                  border: '1px solid var(--color-danger)',
                }}
              >
                <p className="text-sm font-medium" style={{ color: 'var(--color-danger)' }}>{error}</p>
              </div>
            )}

            <div className="space-y-4">
              <select
                value={selectedZone}
                onChange={(e) => setSelectedZone(e.target.value)}
                className="w-full text-sm p-4 rounded-xl outline-none appearance-none cursor-pointer transition-all duration-200"
                style={{ 
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394a3b8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, 
                  backgroundPosition: `right 1rem center`, 
                  backgroundRepeat: `no-repeat`, 
                  backgroundSize: `1.5em 1.5em`,
                }}
              >
                {timezones.map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>

              <div 
                className="rounded-xl p-4 text-center transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <p className="text-[10px] font-bold uppercase tracking-widest mb-1 transition-colors duration-200" style={{ color: 'var(--color-accent-primary)' }}>Local Time Preview</p>
                <p className="font-medium text-sm transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>{currentTimePreview || "Loading..."}</p>
              </div>
            </div>

            <button
              onClick={handleTimezoneSubmit}
              disabled={isProcessing || !selectedZone}
              className="w-full flex items-center justify-center gap-2 rounded-xl px-4 py-3.5 text-sm font-semibold disabled:opacity-50 transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] mt-6 btn-primary"
            >
              {isProcessing ? "Saving..." : "Continue"}
            </button>
          </div>
        )}

        {/* --- STEP 3: BIOMETRICS --- */}
        {step === 3 && (
          <div className="space-y-6 text-center animate-fadeIn">
            <div className="flex flex-col items-center mb-6 space-y-4">
              <div 
                className="w-20 h-20 rounded-full flex items-center justify-center transition-colors duration-500"
                style={{
                  background: 'var(--color-bg-glass)',
                  border: '4px solid var(--color-surface)',
                  boxShadow: 'var(--shadow-md)',
                }}
              >
                <svg className="w-10 h-10 transition-colors duration-200" style={{ color: 'var(--color-accent-primary)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 3.75H6A2.25 2.25 0 003.75 6v1.5M16.5 3.75H18A2.25 2.25 0 0120.25 6v1.5m0 9V18A2.25 2.25 0 0118 20.25h-1.5m-9 0H6A2.25 2.25 0 013.75 18v-1.5M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <div>
                <h2 className="text-2xl font-bold transition-colors duration-200" style={{ color: 'var(--color-text-primary)' }}>Enable Fast Login</h2>
                <p className="text-sm mt-2 max-w-[250px] mx-auto leading-relaxed transition-colors duration-200" style={{ color: 'var(--color-text-secondary)' }}>
                  Use your device's biometrics or a passkey to sign in securely and instantly next time.
                </p>
              </div>
            </div>

            {error && (
              <div 
                className="mb-4 p-4 rounded-xl flex items-start gap-2 text-left animate-fadeIn transition-colors duration-200"
                style={{
                  background: 'var(--color-danger-bg)',
                  border: '1px solid var(--color-danger)',
                }}
              >
                <svg className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: 'var(--color-danger)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <p className="text-sm font-medium" style={{ color: 'var(--color-danger)' }}>{error}</p>
              </div>
            )}
            
            <div className="space-y-3 pt-2">
              <button
                onClick={setupBiometrics}
                disabled={isProcessing}
                className="w-full flex items-center justify-center gap-2 rounded-xl px-4 py-3.5 text-sm font-semibold disabled:opacity-50 transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] btn-primary"
              >
                {isProcessing ? "Waiting for device..." : "Setup FaceID / TouchID"}
              </button>
              
              <button
                onClick={() => router.push("/")}
                disabled={isProcessing}
                className="w-full flex items-center justify-center rounded-xl px-4 py-3.5 text-sm font-semibold transition-all duration-200 btn-secondary"
              >
                Skip for now
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}