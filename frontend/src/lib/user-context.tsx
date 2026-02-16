"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  createUser as apiCreateUser,
  getUser as apiGetUser,
  type UserResponse,
} from "@/lib/api-client";

interface UserContextValue {
  user: UserResponse | null;
  loading: boolean;
  createUser: (displayName: string) => Promise<void>;
  clearUser: () => void;
}

const UserContext = createContext<UserContextValue | null>(null);

const STORAGE_KEY = "taxpilot_user_id";

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, attempt to restore user from localStorage
  useEffect(() => {
    const storedId = localStorage.getItem(STORAGE_KEY);
    if (!storedId) {
      setLoading(false);
      return;
    }

    apiGetUser(storedId)
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(STORAGE_KEY);
      })
      .finally(() => setLoading(false));
  }, []);

  const createUser = useCallback(async (displayName: string) => {
    const newUser = await apiCreateUser({ display_name: displayName });
    localStorage.setItem(STORAGE_KEY, newUser.id);
    setUser(newUser);
  }, []);

  const clearUser = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  }, []);

  return (
    <UserContext.Provider value={{ user, loading, createUser, clearUser }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) {
    throw new Error("useUser must be used within a UserProvider");
  }
  return ctx;
}
