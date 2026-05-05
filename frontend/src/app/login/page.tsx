"use client";

import { useState } from "react";
import { auth } from "@/lib/firebase";
import { signInWithEmailAndPassword, signInWithCustomToken } from "firebase/auth";
import { startAuthentication } from "@simplewebauthn/browser";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Capacitor } from "@capacitor/core";
import { NativeBiometric } from "@capgo/capacitor-native-biometric";
import { fetchWithRetry } from "@/lib/fetchUtils"; 

const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";
// main page
export default function LoginPage() {
  const router = useRouter();
  
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please enter both email and password.");
      return;
    }

    setIsProcessing(true);
    setError("");

    try {
      await signInWithEmailAndPassword(auth, email, password);
      router.push("/");
    } catch (err: any) {
      setError("Invalid email or password.");
      setIsProcessing(false);
    }
  };

  const handleBiometricLogin = async () => {
    if (!email) {
      setError("Please enter your email address to use biometrics.");
      return;
    }

    setIsProcessing(true);
    setError("");

    try {
      if (Capacitor.isNativePlatform()) {
        const available = await NativeBiometric.isAvailable();
        if (!available) throw new Error("Biometrics not available on this device.");

        await NativeBiometric.verifyIdentity({
          reason: "Scan to access your schedule",
        });

        const response = await fetchWithRetry(`${API_BASE_URL}/api/auth/mobile-biometric-login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email }),
          timeoutMs: 10000
        });

        const data = await response.json();

        if (data.status === "success" && data.token) {
          await signInWithCustomToken(auth, data.token);
          router.push("/");
        } else {
          throw new Error(data.message || "Failed to retrieve login token.");
        }
        
      } else {
        const startRes = await fetchWithRetry(`${API_BASE_URL}/api/auth/login/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
          timeoutMs: 8000
        });
        
        const options = await startRes.json();
        const credential = await startAuthentication(options);

        const verifyRes = await fetchWithRetry(`${API_BASE_URL}/api/auth/login/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, credential }),
          timeoutMs: 10000
        });

        const verifyData = await verifyRes.json();
        if (verifyData.status === "success" && verifyData.token) {
          await signInWithCustomToken(auth, verifyData.token);
          router.push("/");
        }
      }
    } catch (err: any) {
      console.error(err);
      setError("Biometric login failed. Please use your password.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4 relative overflow-hidden transition-colors duration-500" style={{ background: "var(--color-bg-base)" }}>
      
      <div 
        className="w-full max-w-md animate-fade-in-up transition-colors duration-500"
        style={{
          background: 'var(--color-bg-glass-strong)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderRadius: '24px',
          border: '1px solid var(--color-border)',
          boxShadow: 'var(--shadow-xl), var(--shadow-inner-glow)',
          padding: '2rem',
        }}
      >
        <div className="flex flex-col items-center mb-8 space-y-4">
          <div 
            className="w-16 h-16 rounded-2xl flex items-center justify-center transition-colors duration-500"
            style={{
              background: 'var(--color-accent-gradient)',
              boxShadow: 'var(--shadow-glow)',
            }}
          >
            <svg className="w-9 h-9" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} style={{ color: "var(--color-bg-base)" }}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
            </svg>
          </div>
          <div className="text-center">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight transition-colors duration-200" style={{ color: "var(--color-text-primary)" }}>Welcome back</h2>
            <p className="text-sm mt-1 transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Sign in to your intelligent schedule</p>
          </div>
        </div>
        
        {error && (
          <div 
            className="mb-6 p-4 rounded-xl flex items-center gap-3 animate-fade-in transition-colors duration-200"
            style={{
              background: 'var(--color-danger-bg)',
              border: '1px solid var(--color-danger)',
            }}
          >
            <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-colors duration-200" style={{ background: "var(--color-surface)", border: "1px solid var(--color-danger)" }}>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: "var(--color-danger)" }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <p className="text-sm font-medium transition-colors duration-200" style={{ color: "var(--color-danger)" }}>{error}</p>
          </div>
        )}

        <div className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider ml-1 transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Email Address</label>
            <input
              type="email"
              required
              className="w-full text-sm px-4 py-3.5 rounded-xl outline-none transition-all duration-200"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = 'var(--color-accent-primary)';
                e.target.style.boxShadow = '0 0 0 3px var(--color-accent-glow)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--color-border)';
                e.target.style.boxShadow = 'none';
              }}
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isProcessing}
            />
          </div>
          
          <button
            onClick={handleBiometricLogin}
            disabled={isProcessing || !email}
            className="w-full flex items-center justify-center gap-2.5 rounded-xl px-4 py-3.5 text-sm font-semibold transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.01] active:scale-[0.99] btn-secondary"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} style={{ color: "var(--color-accent-primary)" }}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 3.75H6A2.25 2.25 0 003.75 6v1.5M16.5 3.75H18A2.25 2.25 0 0120.25 6v1.5m0 9V18A2.25 2.25 0 0118 20.25h-1.5m-9 0H6A2.25 2.25 0 013.75 18v-1.5M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {isProcessing ? "Authenticating..." : "Continue with Passkey / Biometrics"}
          </button>
        </div>

        <div className="relative my-8">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t transition-colors duration-200" style={{ borderColor: "var(--color-border)" }} />
          </div>
          <div className="relative flex justify-center">
            <span 
              className="px-4 text-xs font-semibold uppercase tracking-wider transition-colors duration-200"
              style={{ background: 'var(--color-bg-glass-strong)', color: "var(--color-text-tertiary)" }}
            >
              Or use password
            </span>
          </div>
        </div>

        <form className="space-y-6" onSubmit={handlePasswordLogin}>
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider ml-1 transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>Password</label>
            <input
              type="password"
              required
              className="w-full text-sm px-4 py-3.5 rounded-xl outline-none transition-all duration-200"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = 'var(--color-accent-primary)';
                e.target.style.boxShadow = '0 0 0 3px var(--color-accent-glow)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--color-border)';
                e.target.style.boxShadow = 'none';
              }}
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isProcessing}
            />
          </div>
          
          <button
            type="submit"
            disabled={isProcessing || !email || !password}
            className="w-full flex items-center justify-center gap-2 rounded-xl px-4 py-3.5 text-sm font-semibold transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.01] active:scale-[0.99] btn-primary"
          >
            {isProcessing ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style={{ color: "var(--color-bg-base)" }}>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span style={{ color: "var(--color-bg-base)" }}>Signing In...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} style={{ color: "var(--color-bg-base)" }}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
                </svg>
                <span style={{ color: "var(--color-bg-base)" }}>Sign In</span>
              </>
            )}
          </button>
        </form>

        <div className="text-center mt-8">
          <p className="text-sm transition-colors duration-200" style={{ color: "var(--color-text-secondary)" }}>
            Don't have an account?{" "}
            <Link href="/register" className="font-semibold transition-colors hover:opacity-80" style={{ color: "var(--color-accent-primary)" }}>
              Sign up here
            </Link>
          </p>
        </div>

      </div>
    </div>
  );
}