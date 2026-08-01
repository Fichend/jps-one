const API_BASE = "/api/v1";
const API_ACCESS_TOKEN = import.meta.env.VITE_API_ACCESS_TOKEN?.trim() ?? "";
const API_TIMEOUT_MS = 60000;
const DEEP_ENRICH_TIMEOUT_MS = 5 * 60 * 1000;

type ApiRequestInit = RequestInit & { timeoutMs?: number };

function withApiAuth(headers?: HeadersInit): HeadersInit {
  if (!API_ACCESS_TOKEN) {
    return headers ?? {};
  }
  return {
    ...(headers ?? {}),
    "X-API-Key": API_ACCESS_TOKEN,
  };
}
const SETTINGS_API_BASE = "/api/settings";
const ADMIN_API_BASE = "/api/admin";

export interface HuntRequest {
  website_url: string;
  description: string;
  product_keywords: string[];
  target_customer_profile: string;
  uploaded_file_ids: string[];
  target_regions: string[];
  target_lead_count: number;
  max_rounds: number;
  min_new_leads_threshold: number;
  search_sources: string[];
  search_budget: Record<string, number | string>;
  tool_plan?: HuntCopilotToolPlan | null;
  enable_email_craft: boolean;
  email_template_examples: string[];
  email_template_notes: string;
}

export interface HuntCopilotStrategy {
  target_regions: string[];
  customer_types: string[];
  product_keywords: string[];
  exclusions: string[];
  hard_filters: {
    require_instagram: boolean;
    require_facebook: boolean;
    require_email: boolean;
    require_phone: boolean;
    require_website: boolean;
    require_address: boolean;
  };
  budget: {
    preview_total_usd: number;
    total_usd: number;
    apify_actor_max_items: number;
    apify_actor_max_total_charge_usd: number;
    apify_task_max_total_charge_usd: number;
    max_candidates: number;
    final_leads: number;
  };
  rules: {
    hard_filter_enabled: boolean;
    missing_required_action: "pending_then_reject" | "reject_immediately";
    candidate_pool_enabled: boolean;
    merge_multi_source_evidence: boolean;
    allow_execution: boolean;
  };
  search_sources: string[];
  raw_requirement: string;
  required_fields: string[];
  preferred_fields: string[];
  confirmed_fields: string[];
  product_knowledge_refs: string[];
  product_knowledge_notes: string[];
  product_knowledge_summary: string;
  strategy_version: number;
  strategy_confirmed: boolean;
  needs_recheck: boolean;
}

export interface HuntCopilotMessage {
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface HuntCopilotChannelStatus {
  channel: string;
  enabled: boolean;
  configured: boolean;
  status: "ok" | "missing_config" | "disabled" | "not_execution_tested";
  message: string;
}

export interface HuntCopilotSearchSkill {
  id: string;
  name: string;
  description: string;
  applicable_intents: string[];
  target_company_types: string[];
  default_product_categories: string[];
  recommended_channels: string[];
  optional_channels: string[];
  default_filters: string[];
  required_fields: string[];
  planner_instructions: string;
  risk_notes: string[];
}

export interface HuntCopilotSkillSelection {
  skill: HuntCopilotSearchSkill;
  reason: string;
  overlays: HuntCopilotSearchSkill[];
}

export interface HuntCopilotCriticNote {
  level: "info" | "warning" | "blocking";
  title: string;
  message: string;
  impact: string;
  suggested_fix: string;
}

export interface SearchToolCapability {
  id: string;
  name: string;
  provider: string;
  best_for: string[];
  not_for: string[];
  requires: string[];
  requires_any: string[];
  budget_sensitive: boolean;
  role: string;
  returned_fields: string[];
  limitations: string[];
}

export interface SearchToolStatus {
  capability: SearchToolCapability;
  configured: boolean;
  status: "ok" | "missing_config" | "disabled" | "not_execution_tested";
  message: string;
}

export interface HuntCopilotPreview {
  status: "ready" | "blocked";
  estimated_queries: number;
  expected_candidate_pool: number;
  expected_final_leads: number;
  required_fields: string[];
  channel_breakdown: Record<string, string>;
  warnings: string[];
}

export interface HuntCopilotToolPlanStep {
  tool: string;
  query: string;
  max_results: number;
  purpose: string;
  requires_confirmation: boolean;
  phase?: "discovery" | "enrichment" | "evidence";
  execution_mode?: "search_phase" | "candidate_enrichment" | "disabled";
}

export interface HuntCopilotToolPlan {
  objective: string;
  steps: HuntCopilotToolPlanStep[];
  estimated_max_results: number;
  requires_user_confirmation: boolean;
  created_by: "minimax" | "fallback";
  plan_hash: string;
  summary: string;
}

export interface HuntCopilotToolExecutionPreview {
  tool: string;
  status: "ready" | "missing_config" | "disabled" | "blocked";
  message: string;
  phase?: "discovery" | "enrichment" | "evidence";
  execution_mode?: "search_phase" | "candidate_enrichment" | "disabled";
}

export interface HuntCopilotSession {
  session_id: string;
  state: string;
  messages: HuntCopilotMessage[];
  strategy: HuntCopilotStrategy;
  channel_status: HuntCopilotChannelStatus[];
  preview: HuntCopilotPreview | null;
  automation_job_id: string;
  allowed_actions: string[];
  missing_fields: string[];
  detected_conflicts: string[];
  strategy_version: number;
  needs_recheck: boolean;
  selected_skill: HuntCopilotSkillSelection | null;
  critic_notes: HuntCopilotCriticNote[];
  tool_plan: HuntCopilotToolPlan | null;
  tool_execution_preview: HuntCopilotToolExecutionPreview[];
  strategy_hash: string;
  similar_history: HuntCopilotHistorySummary[];
  suggested_replies: string[];
  conversation_summary: string;
  last_user_intent: string;
  last_ai_action: string;
  clarification_focus: string;
  recent_strategy_changes: string[];
  created_at: string;
  updated_at: string;
}

export interface HuntCopilotHistorySummary {
  session_id: string;
  created_at: string;
  updated_at: string;
  state: string;
  target_regions: string[];
  customer_types: string[];
  product_keywords: string[];
  required_fields: string[];
  max_candidates: number;
  final_leads: number;
  job_id: string;
  job_status: string;
  result_count: number;
  candidate_count: number;
  instagram_count: number;
  email_count: number;
  phone_count: number;
  strategy_hash: string;
  similarity: number;
}

export interface HuntCopilotHistoryResponse {
  sessions: HuntCopilotHistorySummary[];
}

export interface HuntCopilotResponse {
  session: HuntCopilotSession;
  assistant_message: string;
}

export interface HuntCopilotExecutionResponse {
  session: HuntCopilotSession;
  job: AutomationJob;
}

export interface SearchSkillsResponse {
  skills: HuntCopilotSearchSkill[];
}

export interface SearchToolCapabilitiesResponse {
  capabilities: SearchToolCapability[];
}

export interface SearchToolStatusResponse {
  tools: SearchToolStatus[];
}

export interface UploadedFile {
  original_name: string;
  file_id: string;
}

export interface HuntResponse {
  hunt_id: string;
  status: string;
}

export interface HuntStatus {
  hunt_id: string;
  status: string;
  current_stage: string | null;
  hunt_round: number;
  leads_count: number;
  email_sequences_count: number;
  error: string | null;
}

export interface EmailDraft {
  sequence_number: number;
  email_type: string;
  subject: string;
  body_text: string;
  suggested_send_day: number;
  personalization_points?: string[];
  cultural_adaptations?: string[];
  send_status?: string;
  sent_at?: string;
  sent_to?: string;
}

export interface EmailReviewSummary {
  status: string;
  score: number;
  issues: string[];
  suggestions: string[];
  min_score_required: number;
  max_blocking_issues: number;
  blocking_issue_count: number;
  locale: string;
}

export interface EmailManualReview {
  decision: string;
  notes?: string;
  updated_at?: string;
}

export interface EmailSequence {
  lead: Record<string, unknown>;
  locale: string;
  emails: EmailDraft[];
  template_profile: Record<string, unknown>;
  template_plan: Record<string, unknown>;
  validation_summary?: {
    passed?: boolean;
    status?: string;
    issues?: string[];
    suggestions?: string[];
  };
  review_summary: EmailReviewSummary;
  auto_send_eligible: boolean;
  generation_mode?: string;
  template_reused?: boolean;
  template_group?: string;
  template_id?: string;
  template_usage_index?: number;
  template_assigned_count?: number;
  template_remaining_capacity?: number;
  template_max_send_count?: number;
  template_performance?: {
    sent_count?: number;
    replied_count?: number;
    reply_rate?: number;
    status?: string;
    optimization_needed?: boolean;
    recommended_action?: string;
    reason?: string;
  };
  manual_review?: EmailManualReview;
  reply_detection?: {
    checked_at?: string;
    reply_count?: number;
    replies?: Array<Record<string, string>>;
  };
}

export interface HuntResult {
  hunt_id: string;
  status: string;
  insight: Record<string, unknown> | null;
  leads: Record<string, unknown>[];
  email_sequences: EmailSequence[];
  used_keywords: string[];
  hunt_round: number;
  round_feedback: Record<string, unknown> | null;
  keyword_search_stats: Record<string, unknown>;
  search_result_count: number;
  candidate_pool: Record<string, unknown>[];
  rejected_candidates: Record<string, unknown>[];
  candidate_lead_progress: Record<string, unknown>[];
  candidate_quality_summary: Record<string, unknown>;
}

export interface LLMAgentCost {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  call_count: number;
  models: Record<string, { prompt_tokens: number; completion_tokens: number; total_tokens: number; cost_usd: number; call_count: number }>;
}

export interface CostSummary {
  total_cost_usd: number;
  total_tokens: number;
  total_llm_calls: number;
  rounds_completed: number;
  avg_cost_per_round_usd: number;
  by_agent: Record<string, LLMAgentCost>;
  by_round: Record<string, { cost_usd: number; total_tokens: number }>;
  search_api: Record<string, { call_count: number; result_count: number }>;
}

export interface HuntCost {
  hunt_id: string;
  status: string;
  cost_summary: CostSummary;
}

export interface ResumeRequest {
  target_lead_count: number;
  max_rounds: number;
  min_new_leads_threshold: number;
  enable_email_craft: boolean;
  email_template_examples?: string[];
  email_template_notes?: string;
}

export interface HuntListItem {
  hunt_id: string;
  status: string;
  leads_count: number;
  created_at: string;
  website_url: string;
  product_keywords: string[];
  target_customer_profile: string;
  target_regions: string[];
  hunt_round: number;
  email_sequences_count: number;
  task_type?: string;
  source_label?: string;
  customer_pool_status?: "imported" | "not_imported";
  customer_pool_imported_at?: string;
}

export interface DeepSearchRequest {
  website: string;
  company_name?: string;
  country?: string;
  product_keywords?: string[];
  target_customer_profile?: string;
  customer_types?: string[];
  mode?: "deep" | "research";
  max_depth?: number;
  max_pages?: number;
}

export interface DeepSearchCreateResponse {
  hunt_id: string;
  status: string;
  task_type: "single_deep_search";
}

export interface LeadSourceHunt {
  hunt_id: string;
  created_at: string;
  status: string;
  website_url: string;
  product_keywords: string[];
  target_regions: string[];
}

export interface LeadPoolItem {
  lead_id: string;
  company_name: string;
  website: string;
  country_code: string;
  industry: string;
  customer_role: string;
  description: string;
  emails: string[];
  phone_numbers: string[];
  social_media: Record<string, string>;
  social_profiles?: Array<Record<string, unknown>>;
  jps_score?: number;
  lead_grade?: string;
  score_breakdown?: Record<string, { points?: number; reason?: string; evidence?: string }>;
  scoring_version?: string;
  fit_score: number;
  contactability_score: number;
  priority_tier: string;
  evidence_strength: string;
  latest_hunt_at: string;
  source_hunts: LeadSourceHunt[];
}

export interface LeadPoolTaskGroup {
  source: LeadSourceHunt;
  imported_at: string;
  lead_count: number;
  leads: LeadPoolItem[];
}

export interface LeadPoolResponse {
  summary: {
    total_leads: number;
    with_email: number;
    high_fit: number;
    country_count: number;
    source_hunt_count: number;
  };
  groups: LeadPoolTaskGroup[];
}

export interface EmailCampaign {
  id: string;
  hunt_id: string;
  email_account_id: string;
  name: string;
  status: string;
  language_mode: string;
  default_language: string;
  fallback_language: string;
  tone: string;
  step1_delay_days: number;
  step2_delay_days: number;
  step3_delay_days: number;
  min_fit_score: number;
  min_contactability_score: number;
  created_at: string;
  updated_at: string;
}

export interface EmailSequenceSummary {
  id: string;
  campaign_id: string;
  hunt_id: string;
  lead_key: string;
  lead_email: string;
  lead_name: string;
  decision_maker_name: string;
  decision_maker_title: string;
  locale: string;
  status: string;
  current_step: number;
  stop_reason: string;
  replied_at: string;
  last_sent_at: string;
  next_scheduled_at: string;
  created_at: string;
  updated_at: string;
}

export interface EmailCampaignListItem {
  campaign: EmailCampaign;
  sequence_count: number;
  sent_count: number;
  pending_count: number;
  failed_count: number;
  sequences: EmailSequenceSummary[];
}

export interface EmailMessage {
  id: string;
  sequence_id: string;
  step_number: number;
  goal: string;
  locale: string;
  subject: string;
  body_text: string;
  status: string;
  scheduled_at: string;
  sent_at: string;
  provider_message_id: string;
  thread_key: string;
  failure_reason: string;
  created_at: string;
  updated_at: string;
}

export interface EmailSequenceDetail {
  sequence: EmailSequenceSummary;
  messages: EmailMessage[];
  reply_events?: Array<{
    id: string;
    sequence_id: string;
    message_id: string;
    from_email: string;
    subject: string;
    snippet: string;
    received_at: string;
    raw_ref: string;
    created_at: string;
  }>;
}

export interface EmailContactProfile {
  id: string;
  hunt_id: string;
  candidate_id: string;
  lead_id: string;
  company_name: string;
  recipient_email: string;
  recipient_name: string;
  recipient_title: string;
  recipient_type: string;
  website: string;
  country_or_region: string;
  customer_type: string;
  target_type: string;
  company_summary: string;
  jps_fit_reason: string;
  matched_product_keywords: string[];
  evidence_summary: string;
  evidence_urls: string[];
  phone: string;
  linkedin_url: string;
  instagram_url: string;
  facebook_url: string;
  x_url: string;
  language: string;
  send_eligibility: "sendable" | "missing_email" | "invalid_email" | "duplicate_contact" | "blocked_by_policy" | "manually_excluded" | string;
  skip_reason: string;
  risk_flags: string[];
  variables: Record<string, string>;
  selected_for_outreach?: boolean;
  selection_source?: string;
  selected_at?: string;
  calibration_status?: string;
  calibration_notes?: string;
  calibration_confidence?: number;
  sync_result?: { synced?: boolean; matched_count?: number; updated_at?: string };
}

export interface EmailTaskSummary {
  hunt_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  product_keywords: string[];
  target_regions: string[];
  target_customer_profile: string;
  display_name?: string;
  note?: string;
  profile_count: number;
  sendable_count: number;
  blocked_count: number;
}

export interface EmailTemplateWorkspace {
  subject_template: string;
  body_template: string;
  body_html_template?: string;
  messages: Array<{ role: "user" | "assistant" | "system" | string; content: string }>;
  variable_keys: string[];
}

export interface EmailTaskDetail extends EmailTaskSummary {
  workspace: EmailTemplateWorkspace;
  profiles: EmailContactProfile[];
}

export interface EmailProfileExtractResponse {
  hunt_id: string;
  profile_count: number;
  sendable_count: number;
  blocked_count: number;
  profiles: EmailContactProfile[];
}

export interface EmailTemplateChatResponse extends EmailTemplateWorkspace {
  hunt_id: string;
  assistant_message: string;
  used_variables?: string[];
  invalid_variables?: string[];
}

export interface EmailTemplateLibraryItem {
  id: string;
  name: string;
  category: string;
  language: string;
  product_tags: string[];
  customer_type_tags: string[];
  subject_template: string;
  body_template: string;
  body_html_template?: string;
  variable_keys: string[];
  used_variables: string[];
  invalid_variables: string[];
  status: string;
  usage_count: number;
  last_used_at: string;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateLibraryPayload {
  name: string;
  category: string;
  language: string;
  product_tags: string[];
  customer_type_tags: string[];
  subject_template: string;
  body_template: string;
  body_html_template?: string;
}

export interface EmailTemplateApplyResponse extends EmailTemplateChatResponse {
  template: EmailTemplateLibraryItem;
}

export interface OneClickEmailPreview {
  profile_id: string;
  company_name: string;
  recipient_email: string;
  subject: string;
  body_text: string;
  body_html?: string;
  edited?: boolean;
  send_eligibility: string;
  skip_reason: string;
  render_status?: "ready" | "missing_variables" | "invalid_variables" | string;
  used_variables?: string[];
  missing_variables?: string[];
  invalid_variables?: string[];
  rendered_variables?: Record<string, string>;
  recipient_name?: string;
  recipient_title?: string;
  website?: string;
  country_or_region?: string;
  customer_type?: string;
  target_type?: string;
  company_summary?: string;
  jps_fit_reason?: string;
  matched_product_keywords?: string[];
  evidence_summary?: string;
  evidence_urls?: string[];
  phone?: string;
  linkedin_url?: string;
  instagram_url?: string;
  facebook_url?: string;
  x_url?: string;
}

export interface OneClickEmailOverride {
  subject: string;
  body_text: string;
  body_html?: string;
}

export interface OneClickEmailPreviewResponse {
  hunt_id: string;
  preview_id: string;
  content_hash: string;
  expires_at: string;
  sendable_count: number;
  skipped_count: number;
  duplicate_count: number;
  blocked_reason: string;
  previews: OneClickEmailPreview[];
  skipped: OneClickEmailPreview[];
}

export interface OneClickEmailStartResponse {
  hunt_id: string;
  campaign_id: string;
  send_request_id: string;
  status: string;
  status_url: string;
  queued_count: number;
  skipped_count: number;
  duplicate_count: number;
}

export interface EmailSendRequestStatus {
  send_request_id: string;
  hunt_id: string;
  campaign_id: string;
  campaign_name?: string;
  from_email?: string;
  status: string;
  queued_count: number;
  duplicate_count: number;
  skipped_count: number;
  created_at?: string;
  updated_at?: string;
  send_limits?: Record<string, number | boolean | string>;
  summary: Record<string, number>;
  messages: Array<Record<string, unknown>>;
}

export interface EmailTaskHideResponse {
  hunt_id: string;
  status: string;
  hidden_at: string;
}

export interface EmailTaskPreferencesResponse {
  hunt_id: string;
  display_name: string;
  note: string;
  hidden_at: string;
  updated_at: string;
}

export interface EmailProfileUpdateResponse {
  profile: EmailContactProfile;
}

export interface CandidateUpdateResponse {
  hunt_id: string;
  candidate_id: string;
  candidate: Record<string, unknown>;
  updated_collections: string[];
}

export interface CandidateDeepEnrichResponse extends CandidateUpdateResponse {
  summary: Record<string, unknown>;
  email_candidates: EmailCandidateSuggestion[];
  contacts: Array<Record<string, unknown>>;
  evidence_items: Array<Record<string, unknown>>;
  warnings: string[];
  email_profile_sync: Record<string, unknown>;
}

export interface EmailProfileSendListResponse {
  profile: EmailContactProfile;
}

export interface EmailCandidateSuggestion {
  email: string;
  source_url: string;
  confidence: number;
  reason: string;
}

export interface EmailProfileEnrichResponse {
  profile_id: string;
  company_name: string;
  website: string;
  checked_urls: string[];
  candidates: EmailCandidateSuggestion[];
  errors: string[];
}

export interface EmailSequenceDecisionRequest {
  decision: "approved" | "rejected";
  notes?: string;
}

export interface EmailSequenceDecisionResponse {
  hunt_id: string;
  sequence_index: number;
  decision: string;
  auto_send_eligible: boolean;
  manual_review: EmailManualReview;
}

export interface SmtpTestResponse {
  status: string;
  message: string;
  host: string;
  username: string;
}

export interface ImapTestResponse {
  status: string;
  message: string;
  host: string;
  username: string;
}

export interface SettingsApiResponse {
  settings: Record<string, string>;
  is_configured: boolean;
}

export interface IntegrationConfigResponse {
  provider: string;
  enabled: boolean;
  status: string;
  config: Record<string, string | boolean | number>;
  secret_status: Record<string, boolean>;
  scopes: string;
  last_test_at: string;
  last_test_status: string;
  last_test_message: string;
  created_at?: string;
  updated_at?: string;
}

export interface IntegrationTestResponse {
  provider: string;
  status: "ok" | "error";
  message: string;
  assets: Record<string, unknown>;
}

export interface CurrentUser {
  username: string;
}

export interface FeishuTestResponse {
  status: string;
  message: string;
  webhook_url: string;
}

export interface SendEmailDraftRequest {
  sequence_number: number;
}

export interface SendEmailDraftResponse {
  hunt_id: string;
  sequence_index: number;
  sequence_number: number;
  sent_to: string;
  subject: string;
  status: string;
}

export interface DetectReplyResponse {
  hunt_id: string;
  sequence_index: number;
  reply_count: number;
  replies: Array<Record<string, string>>;
}

export interface BackcheckExportCandidateResponse {
  file_name: string;
  download_url: string;
  count: number;
}

export interface AutomationJob {
  job_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  started_at: string;
  finished_at: string;
  claimed_by: string;
  attempt_count: number;
  last_error: string;
  last_hunt_id: string;
  progress_stage: string;
  progress_message: string;
  template_seed_status: string;
  template_seed_source: string;
  template_seed: Record<string, unknown>;
  website_url: string;
  description: string;
  product_keywords: string[];
  target_regions: string[];
  target_lead_count: number;
  search_budget: Record<string, unknown>;
  enable_email_craft: boolean;
  hunt_status: string;
  hunt_stage: string;
  hunt_error: string;
  leads_count: number;
  email_sequences_count: number;
  lead_preview: Array<{
    company_name: string;
    website: string;
    country: string;
    emails: string[];
    email_count: number;
  }>;
  email_sequence_preview: Array<{
    company_name: string;
    website: string;
    target_emails: string[];
    email_count: number;
    subjects: string[];
  }>;
  campaign_summary: {
    campaign_id?: string;
    status?: string;
    sequences_total?: number;
    sent_count?: number;
    failed_count?: number;
    pending_count?: number;
    replied_count?: number;
  };
  campaign_count: number;
  campaign_sequence_count: number;
  campaign_target_emails: string[];
}

export interface AutomationStatus {
  hunt_jobs: {
    queued: number;
    running: number;
    failed: number;
  };
  hunts: {
    running: number;
    pending: number;
    running_details: Array<{
      hunt_id: string;
      website_url: string;
      current_stage: string;
      leads_count: number;
      email_sequences_count: number;
    }>;
  };
  email_queue: {
    pending: number;
    sent: number;
    failed: number;
    cancelled: number;
    active_campaigns: number;
    draft_campaigns: number;
    active_sequences: number;
    replied_sequences: number;
  };
  features: {
    email_auto_send_enabled: boolean;
    email_reply_detection_enabled: boolean;
    automation_summary_enabled: boolean;
    automation_alerts_enabled: boolean;
  };
  workers: {
    consumer?: {
      enabled?: boolean;
      running?: boolean;
      worker_id?: string;
      active_job_id?: string;
      last_claimed_job_id?: string;
      last_completed_job_id?: string;
      last_error?: string;
      last_poll_at?: string;
      last_activity_at?: string;
    };
    template_seed?: {
      enabled?: boolean;
      running?: boolean;
      worker_id?: string;
      active_job_id?: string;
      last_claimed_job_id?: string;
      last_completed_job_id?: string;
      last_error?: string;
      last_poll_at?: string;
      last_activity_at?: string;
    };
  };
}

export interface AutomationMetrics {
  window_hours: number;
  hunt_jobs: {
    completed: number;
    failed: number;
    queued: number;
    running: number;
    retrying: number;
  };
  hunts: {
    created: number;
    completed: number;
    failed: number;
    new_leads: number;
    generated_email_sequences: number;
  };
  emails: {
    queued: number;
    sent: number;
    failed: number;
    replied: number;
    active_campaigns: number;
    draft_campaigns: number;
    active_sequences: number;
    replied_sequences: number;
  };
  recent_failures: Array<{
    sequence_id?: string;
    lead_email?: string;
    subject?: string;
    failure_reason?: string;
  }>;
  recent_sent_messages: Array<{
    id: string;
    subject: string;
    sent_at: string;
    lead_email: string;
    lead_name: string;
    hunt_id: string;
    campaign_id: string;
  }>;
  recent_reply_events: Array<{
    id: string;
    from_email: string;
    subject: string;
    snippet: string;
    received_at: string;
    lead_name: string;
    hunt_id: string;
    campaign_id: string;
  }>;
  top_failure_reasons: Array<{
    failure_reason: string;
    count: number;
  }>;
  recent_completed_hunts: Array<{
    hunt_id: string;
    website_url: string;
    lead_count: number;
    email_sequence_count: number;
    status: string;
  }>;
  recent_failed_hunts: Array<{
    hunt_id: string;
    website_url: string;
    current_stage: string;
    error: string;
    retry_status: string;
    retry_attempts: number;
  }>;
}

export interface JpsOneLayerStatus {
  id: string;
  name: string;
  path: string;
  status: string;
  description: string;
  readme?: boolean;
}

export interface JpsOneFrontendModule {
  id: string;
  name: string;
  path: string;
  status: string;
}

export interface JpsOneMcpTool {
  name: string;
  purpose: string;
  safety: string;
  status: string;
  input_fields: string[];
  output_fields: string[];
}

export interface JpsOneFrameworkStatus {
  product_name: string;
  domain: string;
  positioning: string;
  execution_strategy: string;
  runtime: {
    python_env: string;
    backend_entry: string;
  };
  layers: JpsOneLayerStatus[];
  frontend_modules: JpsOneFrontendModule[];
  mcp_tools: JpsOneMcpTool[];
  next_steps: string[];
}

async function requestSettings<T>(path: string, options?: ApiRequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options?.timeoutMs ?? API_TIMEOUT_MS;
  const { timeoutMs: _timeoutMs, ...fetchOptions } = options ?? {};
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${SETTINGS_API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...fetchOptions,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

async function requestAdmin<T>(path: string, options?: ApiRequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options?.timeoutMs ?? API_TIMEOUT_MS;
  const { timeoutMs: _timeoutMs, ...fetchOptions } = options ?? {};
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${ADMIN_API_BASE}${path}`, {
      headers: withApiAuth({ "Content-Type": "application/json" }),
      ...fetchOptions,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

async function request<T>(path: string, options?: ApiRequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options?.timeoutMs ?? API_TIMEOUT_MS;
  const { timeoutMs: _timeoutMs, ...fetchOptions } = options ?? {};
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers: withApiAuth({ "Content-Type": "application/json", ...(fetchOptions.headers ?? {}) }),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  getCurrentUser: () =>
    fetch("/api/auth/me").then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }
      return res.json() as Promise<CurrentUser>;
    }),

  createHunt: (data: HuntRequest) =>
    request<HuntResponse>("/hunts", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  createAutomationJob: (data: HuntRequest) =>
    request<AutomationJob>("/automation/jobs", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  startHuntCopilot: (message: string) =>
    request<HuntCopilotResponse>("/hunt-copilot/sessions", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  sendHuntCopilotMessage: (sessionId: string, message: string) =>
    request<HuntCopilotResponse>(`/hunt-copilot/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  getHuntCopilotSession: (sessionId: string) =>
    request<HuntCopilotResponse>(`/hunt-copilot/sessions/${sessionId}`),

  listHuntCopilotSessions: () =>
    request<HuntCopilotHistoryResponse>("/hunt-copilot/sessions"),

  duplicateHuntCopilotSession: (sessionId: string) =>
    request<HuntCopilotResponse>(`/hunt-copilot/sessions/${sessionId}/duplicate`, {
      method: "POST",
    }),

  updateHuntCopilotStrategy: (sessionId: string, strategy: HuntCopilotStrategy) =>
    request<HuntCopilotResponse>(`/hunt-copilot/sessions/${sessionId}/strategy`, {
      method: "PATCH",
      body: JSON.stringify({ strategy }),
    }),

  checkHuntCopilotChannels: (sessionId: string) =>
    request<HuntCopilotResponse>(`/hunt-copilot/sessions/${sessionId}/check-channels`, {
      method: "POST",
    }),

  confirmHuntCopilotStrategy: (sessionId: string) =>
    request<HuntCopilotResponse>(`/hunt-copilot/sessions/${sessionId}/confirm-strategy`, {
      method: "POST",
    }),

  executeHuntCopilot: (sessionId: string) =>
    request<HuntCopilotExecutionResponse>(`/hunt-copilot/sessions/${sessionId}/execute`, {
      method: "POST",
      body: JSON.stringify({ enable_email_craft: false, email_template_examples: [], email_template_notes: "" }),
    }),

  listHuntCopilotSkills: () =>
    request<SearchSkillsResponse>("/hunt-copilot/skills"),

  listSearchToolCapabilities: () =>
    request<SearchToolCapabilitiesResponse>("/search-tools/capabilities"),

  listSearchToolStatus: () =>
    request<SearchToolStatusResponse>("/search-tools/status"),

  listAutomationJobs: () =>
    request<AutomationJob[]>("/automation/jobs"),

  getAutomationJob: (jobId: string) =>
    request<AutomationJob>(`/automation/jobs/${jobId}`),

  streamAutomationJob: (jobId: string) => {
    const suffix = API_ACCESS_TOKEN ? `?api_key=${encodeURIComponent(API_ACCESS_TOKEN)}` : "";
    const url = `${API_BASE}/automation/jobs/${jobId}/stream${suffix}`;
    return new EventSource(url);
  },

  getAutomationJobByHunt: (huntId: string) =>
    request<AutomationJob>(`/automation/jobs/by-hunt/${huntId}`),

  createAutomationJobFromHunt: (huntId: string, data: ResumeRequest) =>
    request<AutomationJob>(`/automation/jobs/from-hunt/${huntId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  cancelAutomationJob: (jobId: string) =>
    request<AutomationJob>(`/automation/jobs/${jobId}/cancel`, {
      method: "POST",
    }),

  retryAutomationJob: (jobId: string) =>
    request<AutomationJob>(`/automation/jobs/${jobId}/retry`, {
      method: "POST",
    }),

  getAutomationStatus: () =>
    request<AutomationStatus>("/automation/status"),

  getAutomationMetrics: (hours = 24) =>
    request<AutomationMetrics>(`/automation/metrics?hours=${hours}`),

  getJpsOneFrameworkStatus: () =>
    request<JpsOneFrameworkStatus>("/jps-one/framework/status"),

  getHuntStatus: (huntId: string) =>
    request<HuntStatus>(`/hunts/${huntId}/status`),

  getHuntResult: (huntId: string) =>
    request<HuntResult>(`/hunts/${huntId}/result`),

  exportCandidateBackcheck: (huntId: string, leadSnapshot: Record<string, unknown>, candidateId = "") =>
    request<BackcheckExportCandidateResponse>("/backcheck/export-candidate", {
      method: "POST",
      body: JSON.stringify({ hunt_id: huntId, candidate_id: candidateId, lead_snapshot: leadSnapshot }),
    }),

  setCandidateOutreachSelection: (huntId: string, candidateId: string, selected: boolean) =>
    request<CandidateUpdateResponse>(`/hunts/${huntId}/candidates/${encodeURIComponent(candidateId)}/outreach-selection`, {
      method: "POST",
      body: JSON.stringify({ selected }),
    }),

  updateCandidateProfile: (huntId: string, candidateId: string, fields: Record<string, unknown>) =>
    request<CandidateUpdateResponse>(`/hunts/${huntId}/candidates/${encodeURIComponent(candidateId)}/update`, {
      method: "POST",
      body: JSON.stringify({ fields }),
    }),

  calibrateCandidateProfile: (huntId: string, candidateId: string) =>
    request<CandidateUpdateResponse>(`/hunts/${huntId}/candidates/${encodeURIComponent(candidateId)}/calibrate`, {
      method: "POST",
    }),

  deepEnrichCandidateProfile: (huntId: string, candidateId: string, data: { mode?: "deep" | "research"; max_depth?: number; max_pages?: number } = {}) =>
    request<CandidateDeepEnrichResponse>(`/hunts/${huntId}/candidates/${encodeURIComponent(candidateId)}/deep-enrich`, {
      method: "POST",
      body: JSON.stringify({ mode: data.mode || "deep", max_depth: data.max_depth || 2, max_pages: data.max_pages || 30 }),
      timeoutMs: DEEP_ENRICH_TIMEOUT_MS,
    }),

  downloadBackcheckFile: async (fileName: string): Promise<Blob> => {
    const res = await fetch(`${API_BASE}/backcheck/download/${encodeURIComponent(fileName)}`, {
      headers: withApiAuth(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return res.blob();
  },

  listHunts: () => request<HuntListItem[]>("/hunts"),

  createDeepSearch: (data: DeepSearchRequest) =>
    request<DeepSearchCreateResponse>("/deep-search", {
      method: "POST",
      body: JSON.stringify(data),
      timeoutMs: DEEP_ENRICH_TIMEOUT_MS,
    }),

  getCustomerPool: () => request<LeadPoolResponse>("/customer-pool"),

  importHuntToCustomerPool: (huntId: string) =>
    request<{ hunt_id: string; status: string; imported_at: string; lead_count: number }>(`/customer-pool/imports/${huntId}`, {
      method: "POST",
    }),

  deleteHunt: (huntId: string) =>
    request<{ hunt_id: string; status: string }>(`/hunts/${huntId}`, {
      method: "DELETE",
    }),

  uploadFiles: async (files: File[]): Promise<UploadedFile[]> => {
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));
    const res = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      body: formData,
      headers: withApiAuth(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    return data.uploaded as UploadedFile[];
  },

  resumeHunt: (huntId: string, data: ResumeRequest) =>
    request<HuntResponse>(`/hunts/${huntId}/resume`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  decideEmailSequence: (huntId: string, sequenceIndex: number, data: EmailSequenceDecisionRequest) =>
    request<EmailSequenceDecisionResponse>(`/hunts/${huntId}/email-sequences/${sequenceIndex}/decision`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  sendEmailDraft: (huntId: string, sequenceIndex: number, data: SendEmailDraftRequest) =>
    request<SendEmailDraftResponse>(`/hunts/${huntId}/email-sequences/${sequenceIndex}/send`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  testEmailSettings: () =>
    requestSettings<SmtpTestResponse>("/email/test", {
      method: "POST",
    }),

  getSettings: () =>
    requestSettings<SettingsApiResponse>(""),

  saveSettings: (payload: Record<string, string>) =>
    requestSettings<void>("", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listIntegrations: () =>
    requestAdmin<IntegrationConfigResponse[]>("/integrations"),

  saveIntegration: (provider: string, payload: { enabled: boolean; config: Record<string, string | boolean | number> }) =>
    requestAdmin<IntegrationConfigResponse>(`/integrations/${provider}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  testIntegration: (provider: string) =>
    requestAdmin<IntegrationTestResponse>(`/integrations/${provider}/test`, {
      method: "POST",
    }),

  testImapSettings: () =>
    requestSettings<ImapTestResponse>("/email/imap-test", {
      method: "POST",
    }),

  testFeishuWebhook: () =>
    requestSettings<FeishuTestResponse>("/automation/feishu-test", {
      method: "POST",
    }),

  detectReplies: (huntId: string, sequenceIndex: number) =>
    request<DetectReplyResponse>(`/hunts/${huntId}/email-sequences/${sequenceIndex}/detect-replies`, {
      method: "POST",
    }),

  getHuntCost: (huntId: string) =>
    request<HuntCost>(`/hunts/${huntId}/cost`),

  createEmailCampaign: (huntId: string, name: string) =>
    request<{ campaign_id: string; status: string; sequence_count: number }>(`/hunts/${huntId}/email-campaigns`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  extractEmailProfiles: (huntId: string) =>
    request<EmailProfileExtractResponse>(`/hunts/${huntId}/email-profiles/extract`, {
      method: "POST",
    }),

  listEmailTasks: () =>
    request<EmailTaskSummary[]>("/email/tasks"),

  getEmailTask: (huntId: string) =>
    request<EmailTaskDetail>(`/email/tasks/${huntId}`),

  hideEmailTask: (huntId: string) =>
    request<EmailTaskHideResponse>(`/email/tasks/${huntId}`, {
      method: "DELETE",
    }),

  updateEmailTaskPreferences: (huntId: string, data: { display_name?: string; note?: string }) =>
    request<EmailTaskPreferencesResponse>(`/email/tasks/${huntId}/preferences`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  chatEmailTemplate: (huntId: string, message: string) =>
    request<EmailTemplateChatResponse>(`/email/tasks/${huntId}/template/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  listEmailTemplates: () =>
    request<EmailTemplateLibraryItem[]>("/email/templates"),

  createEmailTemplate: (data: EmailTemplateLibraryPayload) =>
    request<EmailTemplateLibraryItem>("/email/templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateEmailTemplate: (templateId: string, data: EmailTemplateLibraryPayload) =>
    request<EmailTemplateLibraryItem>(`/email/templates/${templateId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteEmailTemplate: (templateId: string) =>
    request<EmailTemplateLibraryItem>(`/email/templates/${templateId}`, {
      method: "DELETE",
    }),

  applyEmailTemplate: (huntId: string, templateId: string) =>
    request<EmailTemplateApplyResponse>(`/email/tasks/${huntId}/template/apply`, {
      method: "POST",
      body: JSON.stringify({ template_id: templateId }),
    }),

  updateEmailContactProfile: (profileId: string, data: { recipient_email?: string; recipient_name?: string; recipient_title?: string }) =>
    request<EmailProfileUpdateResponse>(`/email/contact-profiles/${profileId}/update`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  excludeEmailContactProfileFromSend: (profileId: string) =>
    request<EmailProfileSendListResponse>(`/email/contact-profiles/${profileId}/exclude-from-send`, {
      method: "POST",
    }),

  restoreEmailContactProfileToSend: (profileId: string) =>
    request<EmailProfileSendListResponse>(`/email/contact-profiles/${profileId}/restore-to-send`, {
      method: "POST",
    }),

  setEmailContactProfileOutreachSelection: (profileId: string, selected: boolean) =>
    request<EmailProfileSendListResponse>(`/email/contact-profiles/${profileId}/outreach-selection`, {
      method: "POST",
      body: JSON.stringify({ selected }),
    }),

  enrichEmailContactProfile: (profileId: string) =>
    request<EmailProfileEnrichResponse>(`/email/contact-profiles/${profileId}/enrich-email`, {
      method: "POST",
    }),

  previewOneClickEmail: (huntId: string, data: { subject_template: string; body_template: string; body_html_template?: string; overrides?: Record<string, OneClickEmailOverride> }) =>
    request<OneClickEmailPreviewResponse>(`/email/tasks/${huntId}/one-click/preview`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  startOneClickEmail: (huntId: string, data: { preview_id?: string; subject_template?: string; body_template?: string; body_html_template?: string; campaign_name?: string; overrides?: Record<string, OneClickEmailOverride> }, idempotencyKey?: string) =>
    request<OneClickEmailStartResponse>(`/email/tasks/${huntId}/one-click/start`, {
      method: "POST",
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      body: JSON.stringify(data),
    }),

  getEmailSendRequest: (sendRequestId: string) =>
    request<EmailSendRequestStatus>(`/email/send-requests/${sendRequestId}`),

  listEmailSendRequests: (huntId?: string) =>
    request<EmailSendRequestStatus[]>(`/email/send-requests${huntId ? `?hunt_id=${encodeURIComponent(huntId)}` : ""}`),

  listEmailCampaigns: (huntId: string) =>
    request<EmailCampaignListItem[]>(`/hunts/${huntId}/email-campaigns`),

  startEmailCampaign: (campaignId: string) =>
    request<{ campaign_id: string; status: string }>(`/email-campaigns/${campaignId}/start`, {
      method: "POST",
    }),

  pauseEmailCampaign: (campaignId: string) =>
    request<{ campaign_id: string; status: string }>(`/email-campaigns/${campaignId}/pause`, {
      method: "POST",
    }),

  runEmailReplyCheck: () =>
    request<{ checked: number; matched: number; skipped: number; ignored: number }>(`/email-replies/check`, {
      method: "POST",
    }),

  getEmailSequence: (sequenceId: string) =>
    request<EmailSequenceDetail>(`/email-sequences/${sequenceId}`),

  streamHunt: (huntId: string) => {
    const suffix = API_ACCESS_TOKEN ? `?api_key=${encodeURIComponent(API_ACCESS_TOKEN)}` : "";
    const url = `${API_BASE}/hunts/${huntId}/stream${suffix}`;
    return new EventSource(url);
  },
};
