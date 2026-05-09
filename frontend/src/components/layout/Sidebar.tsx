/** Fixed left sidebar with nav items, user info, and logout. Hidden on mobile (use SidebarDrawer). */
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart2,
  Clock,
  FileText,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Shield,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import type { UserIdentity } from "@/types";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Ask a Question", href: "/query", icon: MessageSquare },
  { label: "Documents", href: "/documents", icon: FileText },
  { label: "History", href: "/history", icon: Clock },
  { label: "Users", href: "/admin/users", icon: Users, adminOnly: true },
  { label: "Analytics", href: "/admin/analytics", icon: BarChart2, adminOnly: true },
  { label: "Audit Logs", href: "/admin/audit", icon: Shield, adminOnly: true },
];

const roleColors: Record<string, string> = {
  admin: "bg-blue-100 text-blue-700",
  clinician: "bg-teal-100 text-teal-700",
  patient: "bg-green-100 text-green-700",
  org_owner: "bg-purple-100 text-purple-700",
};

interface SidebarProps {
  onClose?: () => void;
}

export function Sidebar({ onClose }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserIdentity | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("user_identity");
      if (raw) setUser(JSON.parse(raw) as UserIdentity);
    } catch {
      // ignore parse errors
    }
  }, []);

  async function handleLogout() {
    try {
      await api.delete("/auth/logout");
    } catch {
      // proceed regardless
    }
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_identity");
    router.push("/login");
  }

  const visibleItems = navItems.filter((item) => !item.adminOnly || user?.role === "admin");
  const initials = user?.name
    ? user.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : "U";

  return (
    <aside className="flex h-full w-60 flex-col border-r border-slate-200 bg-white">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2.5 border-b border-slate-200 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500 text-white">
          <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4">
            <path d="M8 1v6H2v2h6v6h2V9h6V7H10V1z" />
          </svg>
        </div>
        <span className="text-lg font-semibold text-slate-800">HealthRAG</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "border-l-2 border-blue-600 bg-blue-50 pl-[10px] text-blue-600"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User section */}
      <div className="border-t border-slate-200 px-4 py-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-800">
              {user?.name ?? "User"}
            </p>
            {user?.role && (
              <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${roleColors[user.role] ?? "bg-slate-100 text-slate-600"}`}>
                {user.role}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </aside>
  );
}
