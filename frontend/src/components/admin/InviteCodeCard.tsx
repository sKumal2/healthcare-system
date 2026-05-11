"use client";

import { useState } from "react";
import { Copy, RefreshCw, Users } from "lucide-react";
import { api } from "@/lib/api";

export function InviteCodeCard() {
  const [code, setCode] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchCode = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/org/invite-code");
      setCode(data.invite_code);
      setOrgName(data.org_name);
    } finally {
      setLoading(false);
    }
  };

  const regenerate = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/admin/org/regenerate-invite-code");
      setCode(data.invite_code);
    } finally {
      setLoading(false);
    }
  };

  const copyCode = () => {
    if (code) {
      navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Users className="text-blue-600" size={20} />
        <h3 className="text-base font-semibold text-slate-800">
          Organization Invite Code
        </h3>
      </div>

      {!code ? (
        <button
          onClick={fetchCode}
          disabled={loading}
          className="text-sm text-blue-600 hover:underline"
        >
          {loading ? "Loading..." : "Show invite code"}
        </button>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">
            Share this code with your team to join <strong>{orgName}</strong>
          </p>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-mono font-bold tracking-widest text-slate-800 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2">
              {code}
            </span>
            <button
              onClick={copyCode}
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors"
              title="Copy code"
            >
              <Copy size={16} />
            </button>
          </div>
          {copied && (
            <p className="text-xs text-green-600">Copied to clipboard</p>
          )}
          <button
            onClick={regenerate}
            disabled={loading}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-red-500 transition-colors mt-2"
          >
            <RefreshCw size={12} />
            Regenerate code (invalidates old one)
          </button>
        </div>
      )}
    </div>
  );
}
