import { TriangleAlert } from "lucide-react";

const DEFAULT_TEXT =
  "This information is for educational purposes only and does not constitute medical advice. Always consult a qualified healthcare professional for medical decisions.";

interface DisclaimerBannerProps {
  text?: string;
}

export function DisclaimerBanner({ text }: DisclaimerBannerProps) {
  return (
    <div className="flex gap-2 items-start rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
      <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5" />
      <span>{text ?? DEFAULT_TEXT}</span>
    </div>
  );
}
