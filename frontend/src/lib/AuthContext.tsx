"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { onAuthStateChanged, User } from "firebase/auth";
import { auth } from "./firebase";
import { useRouter, usePathname } from "next/navigation";

interface AuthContextType {
  user: User | null;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType>({ user: null, loading: true });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

    useEffect(() => {
        // Failsafe: force the loading screen to clear if Firebase hangs
        const timeoutId = setTimeout(() => {
        setLoading(false);
        }, 3000);

        const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
        clearTimeout(timeoutId);
        setUser(currentUser);
        setLoading(false);
        });

        return () => {
        clearTimeout(timeoutId);
        unsubscribe();
        };
    }, []);

  useEffect(() => {
    if (loading) return;

    const isAuthPage = pathname?.startsWith("/login") || pathname?.startsWith("/register");

    if (!user && !isAuthPage) {
      router.replace("/login");
    } else if (user && isAuthPage) {
      // ONLY redirect automatically if they are on the login page.
      // If they are on /register, let the RegisterPage component handle it.
      if (pathname?.startsWith("/login")) {
        router.replace("/");
      }
    }
  }, [user, loading, pathname, router]);

  return (
    <AuthContext.Provider value={{ user, loading }}>
      {loading ? (
        <div className="flex min-h-screen items-center justify-center bg-gray-50">
          <p className="text-gray-500">Authorising...</p>
        </div>
      ) : (
        children
      )}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);