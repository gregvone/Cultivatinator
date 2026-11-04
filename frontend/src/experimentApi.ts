export const outcomes = {
  completed_wet_yield: "Completed wet yield",
  completed_dry_yield: "Completed dry yield",
  days_to_pinning: "Days to first pinning",
  days_to_first_harvest: "Days to first harvest",
  cycle_days: "Completed cycle days",
  failure_rate: "Terminal failure rate",
};
export type Outcome = keyof typeof outcomes;
export interface ExperimentPlan {
  title: string;
  category: "substrate" | "genetics" | "conditions";
  scope: "fruiting";
  primary_variable: string;
  primary_outcome: Outcome;
  secondary_outcomes: Outcome[];
  hypotheses: string | null;
  groups: {
    id?: string | null;
    name: string;
    treatment: string;
    control: boolean;
  }[];
  advanced: {
    allocation_schedule?: string | null;
    blocking?: string | null;
    eligibility?: string | null;
    exclusions?: string | null;
    observation_window?: string | null;
    minimum_readings?: number | null;
    maximum_gap_hours?: number | null;
  };
}
export interface Experiment {
  id: string;
  category: string;
  scope: "fruiting";
  state: "draft" | "planned" | "running" | "completed" | "cancelled";
  archived: number;
  revision: number;
  plan: ExperimentPlan;
  plan_revision: number;
  classification: "prospective" | "retrospective" | "uncertain";
  started_at: string | null;
  treatment_start: string | null;
  timing_precision: string | null;
  post_start_amendment: boolean;
  classification_basis: string;
}
export interface ExperimentPage {
  items: Experiment[];
  total: number;
  page: number;
  page_size: number;
}
export interface ExperimentHistory {
  plans: {
    revision: number;
    snapshot: ExperimentPlan;
    reason: string;
    recorded_at: string;
    committed_at: string | null;
  }[];
  audits: {
    id: number;
    action: string;
    reason: string;
    recorded_at: string;
    before: Experiment | null;
    after: Experiment;
  }[];
  plan_total: number;
  audit_total: number;
  page: number;
  page_size: number;
}
export const blankPlan = (): ExperimentPlan => ({
  title: "",
  category: "substrate",
  scope: "fruiting",
  primary_variable: "",
  primary_outcome: "completed_wet_yield",
  secondary_outcomes: [],
  hypotheses: "",
  groups: [
    { name: "Control", treatment: "", control: true },
    { name: "Comparison", treatment: "", control: false },
  ],
  advanced: {},
});
