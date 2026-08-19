export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export type Complex = {
  complex_id: string;
  complex_name: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  district: string | null;
  analysis_eligible: boolean;
  validation_status: string;
  resilience_score: number | null;
  resilience_grade: string | null;
  data_confidence: number | null;
  assessed_at: string | null;
};

export type Detail = Complex & { assessments: Record<string, any> };
export type Prediction = {
  prediction_id: string; complex_id: string; risk_type: string; risk_level: string;
  risk_probability: number; prediction_time: string; model_version: string;
};

export const fmt = (value: number | null | undefined, unit = "점") =>
  value == null ? "미분석" : `${Number(value).toFixed(1)}${unit}`;

export const riskColor = (score: number | null) =>
  score == null ? "#94a3b8" : score <= 39 ? "#e53935" : score <= 59 ? "#fb8c00" : score <= 74 ? "#eab308" : "#24a774";
