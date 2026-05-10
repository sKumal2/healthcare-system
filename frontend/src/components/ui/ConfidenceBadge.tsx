/** Colored pill badge showing RAG answer confidence score. */

interface ConfidenceBadgeProps {
  score: number;
  showLabel?: boolean;
}

function getBadgeStyle(score: number): { className: string; label: string } {
  if (score >= 0.85) return { className: "bg-green-100 text-green-700", label: "High Confidence" };
  if (score >= 0.7) return { className: "bg-blue-100 text-blue-700", label: "Good" };
  if (score >= 0.5) return { className: "bg-amber-100 text-amber-700", label: "Moderate" };
  return { className: "bg-red-100 text-red-700", label: "Low Confidence" };
}

export function ConfidenceBadge({ score, showLabel = false }: ConfidenceBadgeProps) {
  if (!score || isNaN(score)) {
    return (
      <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">
        Calculating...
      </span>
    );
  }

  const { className, label } = getBadgeStyle(score);
  const pct = Math.round(score * 100);

  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {pct}%{showLabel && <span>· {label}</span>}
    </span>
  );
}
