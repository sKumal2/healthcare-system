import { PageWrapper } from "@/components/layout/PageWrapper";
import { Users, MessageSquare, FileText, Clock } from "lucide-react";
import { InviteCodeCard } from "@/components/admin/InviteCodeCard";

interface StatCard {
  label: string;
  value: string;
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
}

const stats: StatCard[] = [
  { label: "Total Users", value: "—", icon: Users, iconBg: "bg-blue-100", iconColor: "text-blue-600" },
  { label: "Questions Today", value: "—", icon: MessageSquare, iconBg: "bg-teal-100", iconColor: "text-teal-600" },
  { label: "Docs Processed", value: "—", icon: FileText, iconBg: "bg-green-100", iconColor: "text-green-600" },
  { label: "Avg Response Time", value: "—", icon: Clock, iconBg: "bg-amber-100", iconColor: "text-amber-600" },
];

export default function DashboardPage() {
  return (
    <PageWrapper title="Dashboard" subtitle="Overview of your healthcare RAG system">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.label}
              className="rounded-xl bg-white p-6 shadow-sm border border-slate-200"
            >
              <div className="flex items-center justify-between mb-4">
                <div className={`flex h-10 w-10 items-center justify-center rounded-full ${stat.iconBg}`}>
                  <Icon className={`h-5 w-5 ${stat.iconColor}`} />
                </div>
              </div>
              <p className="text-3xl font-bold text-slate-800">{stat.value}</p>
              <p className="mt-1 text-sm text-slate-500">{stat.label}</p>
            </div>
          );
        })}
      </div>

      <div className="mt-6 max-w-md">
        <InviteCodeCard />
      </div>
    </PageWrapper>
  );
}
