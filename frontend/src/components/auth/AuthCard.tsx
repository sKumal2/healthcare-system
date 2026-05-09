import { Plus } from "lucide-react";

interface AuthCardProps {
  children: React.ReactNode;
}

export function AuthCard({ children }: AuthCardProps) {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 w-full max-w-md">
        <div className="flex flex-col items-center gap-2 mb-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-500 text-white">
              <Plus size={24} strokeWidth={2.5} />
            </div>
            <span className="text-xl font-semibold text-slate-800">HealthRAG</span>
          </div>
          <p className="text-sm text-slate-500">AI-Powered Healthcare Information</p>
        </div>

        <div className="border-b border-slate-100 mt-6 mb-6" />

        {children}
      </div>
    </div>
  );
}
