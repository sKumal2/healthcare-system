"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

function getStrength(password: string): { level: number; label: string; color: string } {
  if (password.length === 0) return { level: 0, label: "", color: "" };
  if (password.length < 8) return { level: 1, label: "Too short", color: "bg-red-500" };
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const typeCount = [hasUpper, hasLower, hasDigit, hasSpecial].filter(Boolean).length;
  if (password.length >= 12 && typeCount >= 3 && hasSpecial) {
    return { level: 4, label: "Strong", color: "bg-green-500" };
  }
  if (typeCount >= 3 || (typeCount >= 2 && password.length >= 10)) {
    return { level: 3, label: "Good", color: "bg-yellow-500" };
  }
  return { level: 2, label: "Weak", color: "bg-orange-500" };
}

const strengthTextColor: Record<number, string> = {
  1: "text-red-600",
  2: "text-orange-600",
  3: "text-yellow-600",
  4: "text-green-600",
};

export function RegisterForm() {
  const router = useRouter();
  const { register, isLoading, error, clearError } = useAuth();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [nameError, setNameError] = useState("");
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");

  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const strength = getStrength(password);

  function validate(): boolean {
    let valid = true;

    if (!fullName.trim()) {
      setNameError("Full name is required");
      valid = false;
    } else if (fullName.trim().length < 2) {
      setNameError("Name must be at least 2 characters");
      valid = false;
    } else if (fullName.trim().length > 100) {
      setNameError("Name must be at most 100 characters");
      valid = false;
    } else {
      setNameError("");
    }

    if (!email.trim()) {
      setEmailError("Email is required");
      valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setEmailError("Enter a valid email address");
      valid = false;
    } else {
      setEmailError("");
    }

    if (!password) {
      setPasswordError("Password is required");
      valid = false;
    } else if (password.length < 8) {
      setPasswordError("Password must be at least 8 characters");
      valid = false;
    } else {
      setPasswordError("");
    }

    return valid;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    const success = await register(email, password, fullName);
    if (success) {
      router.push("/dashboard");
    }
  }

  function handleFocus() {
    clearError();
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <h2 className="text-2xl font-semibold text-slate-800">Create your account</h2>
      <p className="text-sm text-slate-500 mt-1 mb-6">Start using HealthRAG today</p>

      <div className="mb-4">
        <label htmlFor="full-name" className="block text-sm font-medium text-slate-700 mb-1.5">
          Full name
        </label>
        <Input
          ref={nameRef}
          id="full-name"
          type="text"
          placeholder="Dr. Jane Smith"
          autoComplete="name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          onFocus={handleFocus}
          disabled={isLoading}
          className="rounded-lg w-full"
          aria-invalid={!!nameError}
          aria-describedby={nameError ? "name-error" : undefined}
        />
        {nameError && (
          <p id="name-error" className="mt-1 text-xs text-red-600">{nameError}</p>
        )}
      </div>

      <div className="mb-4">
        <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1.5">
          Email address
        </label>
        <Input
          id="email"
          type="email"
          placeholder="you@hospital.com"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onFocus={handleFocus}
          disabled={isLoading}
          className="rounded-lg w-full"
          aria-invalid={!!emailError}
          aria-describedby={emailError ? "email-error" : undefined}
        />
        {emailError && (
          <p id="email-error" className="mt-1 text-xs text-red-600">{emailError}</p>
        )}
      </div>

      <div className="mb-6">
        <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1.5">
          Password
        </label>
        <div className="relative">
          <Input
            id="password"
            type={showPassword ? "text" : "password"}
            placeholder="••••••••"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onFocus={handleFocus}
            disabled={isLoading}
            className="rounded-lg w-full pr-10"
            aria-invalid={!!passwordError}
            aria-describedby={passwordError ? "password-error" : undefined}
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            tabIndex={-1}
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>

        {password.length > 0 && (
          <div className="mt-2">
            <div className="flex gap-1 h-1.5">
              {[1, 2, 3, 4].map((seg) => (
                <div
                  key={seg}
                  className={`flex-1 rounded-full transition-colors ${
                    strength.level >= seg ? strength.color : "bg-slate-200"
                  }`}
                />
              ))}
            </div>
            <p className={`mt-1 text-xs ${strengthTextColor[strength.level] ?? ""}`}>
              {strength.label}
            </p>
          </div>
        )}

        {passwordError && (
          <p id="password-error" className="mt-1 text-xs text-red-600">{passwordError}</p>
        )}
      </div>

      {error && (
        <div className="mb-4">
          <ErrorBanner message={error} onDismiss={clearError} />
        </div>
      )}

      <button
        type="submit"
        disabled={isLoading}
        className="w-full h-11 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium flex items-center justify-center gap-2 transition-colors"
      >
        {isLoading ? (
          <>
            <LoadingSpinner size="sm" />
            <span>Creating account...</span>
          </>
        ) : (
          "Create Account"
        )}
      </button>

      <p className="text-sm text-slate-500 text-center mt-4">
        Already have an account?{" "}
        <Link href="/login" className="text-blue-600 hover:underline font-medium">
          Sign in &rarr;
        </Link>
      </p>
    </form>
  );
}
