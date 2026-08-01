import { Badge } from "@/components/ui/badge";

type ScoreLike = {
  jps_score?: unknown;
  lead_grade?: unknown;
  fit_score?: unknown;
  match_score?: unknown;
};

function gradeVariant(score: number) {
  if (score >= 80) return "success" as const;
  if (score >= 60) return "warning" as const;
  return "secondary" as const;
}

export function hasJpsScore(item: ScoreLike) {
  return typeof item.jps_score === "number" || typeof item.lead_grade === "string";
}

export function jpsScoreText(item: ScoreLike) {
  if (hasJpsScore(item)) {
    return `${String(item.lead_grade || "D")} · ${Number(item.jps_score || 0)}`;
  }
  const fit = Number(item.fit_score ?? item.match_score ?? 0);
  return fit > 0 ? `${Math.round(fit * 100)}%` : "待评分";
}

export function JpsScoreBadge({ item }: { item: ScoreLike }) {
  if (hasJpsScore(item)) {
    const score = Number(item.jps_score || 0);
    return <Badge variant={gradeVariant(score)}>{jpsScoreText(item)}</Badge>;
  }
  const fit = Number(item.fit_score ?? item.match_score ?? 0);
  return <Badge variant={fit >= 0.7 ? "success" : fit >= 0.4 ? "warning" : "secondary"}>{jpsScoreText(item)}</Badge>;
}
