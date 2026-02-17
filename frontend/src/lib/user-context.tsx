"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter, usePathname } from "@/i18n/navigation";
import { useLocale } from "next-intl";
import {
  createUser as apiCreateUser,
  getUser as apiGetUser,
  updateUser as apiUpdateUser,
  type UserResponse,
} from "@/lib/api-client";

interface UserContextValue {
  user: UserResponse | null;
  loading: boolean;
  createUser: (displayName: string) => Promise<void>;
  clearUser: () => void;
  updateLocalePreference: (locale: string) => Promise<void>;
}

const UserContext = createContext<UserContextValue | null>(null);

const STORAGE_KEY = "taxpilot_user_id";

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const hasRestoredLocale = useRef(false);
  const router = useRouter();
  const pathname = usePathname();
  const currentLocale = useLocale();

  // On mount, attempt to restore user from localStorage
  useEffect(() => {
    const storedId = localStorage.getItem(STORAGE_KEY);
    if (!storedId) {
      setLoading(false);
      return;
    }

    apiGetUser(storedId)
      .then((fetchedUser) => {
        setUser(fetchedUser);
        // Redirect to saved locale preference once on initial load
        if (
          !hasRestoredLocale.current &&
          fetchedUser.locale_preference &&
          fetchedUser.locale_preference !== currentLocale
        ) {
          hasRestoredLocale.current = true;
          router.replace(pathname, { locale: fetchedUser.locale_preference });
        }
      })
      .catch(() => {
        localStorage.removeItem(STORAGE_KEY);
      })
      .finally(() => setLoading(false));
  }, [currentLocale, pathname, router]);

  const createUser = useCallback(async (displayName: string) => {
    const newUser = await apiCreateUser({ display_name: displayName });
    localStorage.setItem(STORAGE_KEY, newUser.id);
    setUser(newUser);
  }, []);

  const clearUser = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  }, []);

  const updateLocalePreference = useCallback(
    async (locale: string) => {
      if (!user) return;

      const updatedUser = await apiUpdateUser(user.id, {
        locale_preference: locale,
      });
      setUser(updatedUser);
    },
    [user],
  );

  return (
    <UserContext.Provider
      value={{ user, loading, createUser, clearUser, updateLocalePreference }}
    >
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
