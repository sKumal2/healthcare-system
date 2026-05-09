/** Dismissible error/warning/info banner with icon and optional error code. */
"use client";

import { AlertCircle, AlertTriangle, Info, X } from "lucide-react";

interface ErrorBannerProps {
  message: string;
  code?: string;
  onDismiss?: () => void;
  variant?: "error" | "warning" | "info";
}

const variantStyles = {
  error: {
    wrapper: "bg-red-50 border-red-200 text-red-700",
    icon: AlertCircle,
  },
  warning: {
    wrapper: "bg-amber-50 border-amber-200 text-amber-700",
    icon: AlertTriangle,
  },
  info: {
    wrapper: "bg-blue-50 border-blue-200 text-blue-700",
    icon: Info,
  },
};

export function ErrorBanner({ message, code, onDismiss, variant = "error" }: ErrorBannerProps) {
  const { wrapper, icon: Icon } = variantStyles[variant];

  return (
    <div className={`flex items-start gap-3 rounded-lg border p-4 ${wrapper}`} role="alert">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{message}</p>
        {code && <p className="mt-0.5 text-xs opacity-75">Code: {code}</p>}
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="shrink-0 rounded p-0.5 opacity-70 hover:opacity-100 transition-opacity"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
