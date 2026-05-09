/** Top navigation bar with page title, notification bell, user avatar, and mobile hamburger. */
"use client";

import { useEffect, useState } from "react";
import { Bell, Menu } from "lucide-react";
import type { UserIdentity } from "@/types";

const roleColors: Record<string, string> = {
  admin: "bg-blue-100 text-blue-700",
  clinician: "bg-teal-100 text-teal-700",
  patient: "bg-green-100 text-green-700",
  org_owner: "bg-purple-100 text-purple-700",
};

interface NavbarProps {
  title: string;
  onMenuClick?: () => void;
}

export function Navbar({ title, onMenuClick }: NavbarProps) {
  const [user, setUser] = useState<UserIdentity | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("user_identity");
      if (raw) setUser(JSON.parse(raw) as UserIdentity);
    } catch {
      // ignore
    }
  }, []);

  const initials = user?.name
    ? user.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : "U";

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 md:hidden"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
        <h1 className="text-lg font-semibold text-slate-800">{title}</h1>
      </div>

      <div className="flex items-center gap-4">
        <button
          className="relative rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 transition-colors"
          aria-label="Notifications"
        >
          <Bell className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
            {initials}
          </div>
          <div className="hidden sm:block">
            <p className="text-sm font-medium text-slate-800 leading-tight">{user?.name ?? "User"}</p>
            {user?.role && (
              <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${roleColors[user.role] ?? "bg-slate-100 text-slate-600"}`}>
                {user.role}
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
