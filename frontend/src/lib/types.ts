export interface InsightMetric {
  label: string;
  value: string;
  sub?: string;
}

export interface InsightCard {
  id: string;
  label: string;
  description: string;
  accent: string;
  icon: string;
  metrics: InsightMetric[];
  sparkline: number[];
}

export interface BrandDossierRow {
  name: string;
  meta: string;
  percent: number;
  status: "Live" | "In Build";
}

export interface ReviewStageRow {
  stage: string;
  submissions: number;
  firstPass: number;
  avgDays: number;
  sentBack: number;
}

export interface LibraryAsset {
  title: string;
  uses: number;
}

// Mirrors backend/src/data/dashboard.py. The campaign/audience/field-rep
// shapes that used to live here (ActiveCampaign, ChannelPerformance) went
// out with the nav entries behind them — see that file's header.
export interface DashboardData {
  insights: InsightCard[];
  brandDossiers: BrandDossierRow[];
  reviewStages: ReviewStageRow[];
  topAssets: LibraryAsset[];
}

export interface AnalyticsStat {
  id: string;
  label: string;
  value: number;
  icon: string;
  accent: string;
}

export interface WeeklySendChannel {
  channel: string;
  color: string;
  values: number[];
}

export interface FunnelStage {
  stage: string;
  value: number;
  color: string;
}

export interface AnalyticsOverview {
  stats: AnalyticsStat[];
  weeklySendVolume: {
    weeks: string[];
    channels: WeeklySendChannel[];
  };
  engagementFunnel: FunnelStage[];
}

export type ApprovalState = "pending" | "approved" | "rejected" | "withdrawn";
export type ApprovalEntityKind = "asset" | "campaign";

export interface ApprovalRow {
  id: string;
  submissionNumber: number;
  entityKind: ApprovalEntityKind;
  entity: { name: string; type: string; therapy: string };
  currentStage: string;
  stageIndex: number;
  stageTotal: number;
  state: ApprovalState;
  submittedBy: { name: string; email: string };
  submittedAt: string;
  canDecide: boolean;
}

export interface ApprovalsData {
  rows: ApprovalRow[];
  stages: string[];
}

export interface BrandKitData {
  workspaceName: string;
  logoInitials: string;
  palette: {
    primary: string;
    accent: string;
    calloutBackground: string;
    text: string;
  };
  typography: {
    headingFont: string;
    bodyFont: string;
  };
  preview: {
    title: string;
    subtitle: string;
    heading: string;
    body: string;
    calloutLabel: string;
    calloutBody: string;
  };
}
