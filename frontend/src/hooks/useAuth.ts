"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import {
  setTokens,
  setUserIdentity,
  getUserIdentity,
  clearAuth,
  isAuthenticated,
} from "@/lib/auth";
import type { UserIdentity, ApiError } from "@/types";
import type { AxiosError } from "axios";

interface AuthState {
  user: UserIdentity | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;
}

interface UseAuthReturn extends AuthState {
  login: (email: string, password: string) => Promise<boolean>;
  register: (email: string, password: string, fullName: string) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export function useAuth(): UseAuthReturn {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: false,
    isAuthenticated: false,
    error: null,
  });

  useEffect(() => {
    const identity = getUserIdentity();
    if (identity) {
      setState({ user: identity, isLoading: false, isAuthenticated: true, error: null });
    } else if (isAuthenticated()) {
      api
        .get<UserIdentity>("/auth/me")
        .then(({ data }) => {
          setUserIdentity(data);
          setState({ user: data, isLoading: false, isAuthenticated: true, error: null });
        })
        .catch(() => {
          setState({ user: null, isLoading: false, isAuthenticated: false, error: null });
        });
    } else {
      setState({ user: null, isLoading: false, isAuthenticated: false, error: null });
    }
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<boolean> => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const formData = new URLSearchParams();
      formData.append("username", email.toLowerCase().trim());
      formData.append("password", password);

      const { data: tokens } = await api.post<{
        access_token: string;
        refresh_token: string;
      }>("/auth/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });

      setTokens(tokens.access_token, tokens.refresh_token);

      const { data: identity } = await api.get<UserIdentity>("/auth/me");
      setUserIdentity(identity);

      setState({ user: identity, isLoading: false, isAuthenticated: true, error: null });
      return true;
    } catch (err: unknown) {
      let message = "Something went wrong. Please try again.";

      if (err && typeof err === "object" && "response" in err) {
        const axiosErr = err as { response?: { status?: number; data?: ApiError } };
        const status = axiosErr.response?.status;
        const code = axiosErr.response?.data?.error?.code;

        if (status === 401 || code === "PERMISSION_DENIED") {
          message = "Invalid email or password";
        } else if (code === "RATE_LIMITED") {
          message = "Too many attempts. Please wait a moment.";
        } else if (axiosErr.response?.data?.error?.message) {
          message = axiosErr.response.data.error.message;
        }
      } else if (err && typeof err === "object" && "request" in err) {
        message = "Cannot connect to server. Check your connection.";
      }

      setState((s) => ({ ...s, isLoading: false, error: message }));
      return false;
    }
  }, []);

  const register = useCallback(async (email: string, password: string, fullName: string): Promise<boolean> => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const { data } = await api.post<{ access_token: string; refresh_token: string }>(
        "/auth/register",
        { email: email.toLowerCase().trim(), password, full_name: fullName.trim() }
      );
      setTokens(data.access_token, data.refresh_token);
      const { data: identity } = await api.get<UserIdentity>("/auth/me");
      setUserIdentity(identity);
      setState({ user: identity, isLoading: false, isAuthenticated: true, error: null });
      return true;
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<ApiError>;
      const httpStatus = axiosErr.response?.status;
      let message: string;
      if (httpStatus === 409) {
        message = "An account with this email already exists.";
      } else if (httpStatus === 422) {
        message = "Please check your details and try again.";
      } else {
        message = axiosErr.response?.data?.error?.message ?? "Registration failed. Try again.";
      }
      setState((s) => ({ ...s, isLoading: false, error: message }));
      return false;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // best effort
    }
    clearAuth();
    setState({ user: null, isLoading: false, isAuthenticated: false, error: null });
    router.push("/login");
  }, [router]);

  const clearError = useCallback(() => {
    setState((s) => ({ ...s, error: null }));
  }, []);

  return { ...state, login, register, logout, clearError };
}
