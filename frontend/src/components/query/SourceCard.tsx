import { ExternalLink, ShieldCheck, CircleCheck } from "lucide-react";
import { getSourceAuthority, getDomain, truncateTitle } from "@/lib/queryHelpers";
import type { SourceMetadata } from "@/types";

interface SourceCardProps {
  source: SourceMetadata;
  rank: number;
}

export function SourceCard({ source, rank }: SourceCardProps) {
  const authority = getSourceAuthority(source.source_url);
  const domain = getDomain(source.source_url);
  const similarityPct = Math.round(source.similarity_score * 100);

  const AuthorityIcon =
    authority.level === "high"
      ? ShieldCheck
      : authority.level === "medium"
      ? CircleCheck
      : ExternalLink;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-600">
          {rank}
        </span>
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${authority.color}`}
        >
          <AuthorityIcon className="h-3 w-3" />
          {authority.label}
        </span>
      </div>

      <p className="mt-2 text-sm font-medium text-slate-800 line-clamp-2">
        {truncateTitle(source.title)}
      </p>

      <p className="mt-1 text-xs text-slate-500">
        {domain && <span>{domain} · </span>}
        {similarityPct}% match
      </p>

      {source.source_url ? (
        <a
          href={source.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
        >
          View Source <ExternalLink className="h-3 w-3" />
        </a>
      ) : (
        <p className="mt-2 text-xs text-slate-400">Source document</p>
      )}
    </div>
  );
}
