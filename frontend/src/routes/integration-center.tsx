import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bookmark,
  BookOpen,
  CheckCircle2,
  History,
  ExternalLink,
  Loader2,
  Mail,
  MoreHorizontal,
  Play,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { api, EmailCandidateSuggestion, EmailContactProfile, EmailSendRequestStatus, EmailTemplateLibraryItem, OneClickEmailOverride, OneClickEmailPreview, OneClickEmailPreviewResponse, OneClickEmailStartResponse } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RichEmailEditor } from "@/components/email/RichEmailEditor";
import { Input } from "@/components/ui/input";

const DEFAULT_SUBJECT = "";
const DEFAULT_BODY = "";

const SAFE_TEMPLATE_VARIABLES = [
  "company_name",
  "recipient_name",
  "recipient_email",
  "recipient_title",
  "website",
  "country_or_region",
  "customer_type",
  "product_pitch",
  "phone",
  "linkedin_url",
  "instagram_url",
  "facebook_url",
  "x_url",
];

type WorkspaceTab = "profiles" | "template" | "library" | "records";
type ProfileFilter = "all" | "sendable" | "missing_email" | "blocked" | "bookmarked";

const TEMPLATE_CATEGORIES = [
  ["development", "开发信"],
  ["holiday", "节日祝福"],
  ["follow_up", "跟进信"],
  ["custom", "自定义"],
] as const;

function splitTags(value: string) {
  return value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean);
}

function categoryLabel(value: string) {
  return TEMPLATE_CATEGORIES.find(([key]) => key === value)?.[1] || value || "自定义";
}

function statusBadge(value: string) {
  if (value === "sendable") return <Badge variant="success">可发送</Badge>;
  if (value === "missing_email") return <Badge variant="secondary">缺邮箱</Badge>;
  if (value === "invalid_email") return <Badge variant="destructive">邮箱无效</Badge>;
  if (value === "manually_excluded") return <Badge variant="warning">已移出发送</Badge>;
  return <Badge variant="outline">{value || "待检查"}</Badge>;
}

function compactList(values: string[]) {
  return values.filter(Boolean).slice(0, 3).join("、") || "-";
}

function sendStatusLabel(value?: string) {
  if (value === "completed") return "已完成";
  if (value === "queued") return "已进入队列";
  if (value === "sending") return "发送中";
  if (value === "smtp_accepted") return "SMTP 已接收";
  if (value === "retry_wait") return "等待重试";
  if (value === "failed") return "失败";
  if (value === "unknown") return "结果不确定";
  if (value === "cancelled") return "已取消";
  return value || "待确认";
}

function sendRequestTotals(status?: Pick<EmailSendRequestStatus, "summary" | "messages" | "skipped_count" | "duplicate_count"> | null) {
  const summary = status?.summary || {};
  const accepted = Number(summary.smtp_accepted || 0);
  const failed = Number(summary.failed || 0) + Number(summary.unknown || 0);
  return {
    accepted,
    failed,
    skipped: Number(status?.skipped_count || 0),
    duplicate: Number(status?.duplicate_count || 0),
    failedMessages: (status?.messages || []).filter((item) => item.status === "failed" || item.status === "unknown"),
  };
}

function formatDateTime(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function updateProfileSelectionInTask(task: unknown, profileId: string, selected: boolean): unknown {
  if (!task || typeof task !== "object") return task;
  const current = task as Record<string, unknown>;
  const profiles = Array.isArray(current.profiles)
    ? current.profiles.map((row) => {
        const profile = row && typeof row === "object" ? row as EmailContactProfile : null;
        if (!profile || profile.id !== profileId) return row;
        return {
          ...profile,
          selected_for_outreach: selected,
          selection_source: selected ? "email_sending" : "",
          selected_at: selected ? new Date().toISOString() : "",
        };
      })
    : current.profiles;
  return { ...current, profiles };
}

function openWebsite(url: string) {
  if (!url) return;
  const normalized = url.startsWith("http") ? url : `https://${url}`;
  window.open(normalized, "_blank", "noopener,noreferrer");
}

function ProfileListItem({ profile, selected, onSelect, onToggleBookmark, disabled }: { profile: EmailContactProfile; selected: boolean; onSelect: () => void; onToggleBookmark: () => void; disabled?: boolean }) {
  const socialCount = [profile.linkedin_url, profile.instagram_url, profile.facebook_url, profile.x_url].filter(Boolean).length;
  const bookmarked = Boolean(profile.selected_for_outreach);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-md border bg-white p-4 text-left transition-colors ${selected ? "border-primary bg-primary/5" : "hover:bg-muted/40"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">{profile.company_name}</h3>
          <p className="mt-1 truncate text-xs text-muted-foreground">{profile.country_or_region || profile.customer_type || "未标注地区"}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            role="button"
            tabIndex={0}
            className={`rounded p-1 transition-colors ${bookmarked ? "text-red-600 hover:bg-red-50" : "text-muted-foreground/40 hover:bg-muted hover:text-red-600"}`}
            title="标记为邮件重点客户"
            onClick={(event) => {
              event.stopPropagation();
              if (!disabled) onToggleBookmark();
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              event.stopPropagation();
              if (!disabled) onToggleBookmark();
            }}
          >
            <Bookmark className={`h-4 w-4 ${bookmarked ? "fill-red-600" : "fill-transparent"}`} />
          </span>
          {statusBadge(profile.send_eligibility)}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <p className="truncate">邮箱：{profile.recipient_email || "-"}</p>
        <p>社媒：{socialCount || "-"}</p>
        <p className="truncate">电话：{profile.phone || "-"}</p>
        <p className="truncate">产品：{compactList(profile.matched_product_keywords)}</p>
      </div>
    </button>
  );
}

export function IntegrationCenterPage() {
  const queryClient = useQueryClient();
  const [selectedHuntId, setSelectedHuntId] = useState("");
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("profiles");
  const [profileFilter, setProfileFilter] = useState<ProfileFilter>("all");
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [emailInput, setEmailInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [titleInput, setTitleInput] = useState("");
  const [enrichResult, setEnrichResult] = useState<{ profileId: string; candidates: EmailCandidateSuggestion[]; checkedUrls: string[]; errors: string[] } | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [subjectTemplate, setSubjectTemplate] = useState(DEFAULT_SUBJECT);
  const [bodyTemplate, setBodyTemplate] = useState(DEFAULT_BODY);
  const [bodyHtmlTemplate, setBodyHtmlTemplate] = useState("");
  const [preview, setPreview] = useState<OneClickEmailPreviewResponse | null>(null);
  const [startResult, setStartResult] = useState<OneClickEmailStartResponse | null>(null);
  const [sendRequestId, setSendRequestId] = useState("");
  const [sendStatusModalOpen, setSendStatusModalOpen] = useState(false);
  const [selectedRecordId, setSelectedRecordId] = useState("");
  const [editedPreviewMap, setEditedPreviewMap] = useState<Record<string, OneClickEmailOverride>>({});
  const [editingPreview, setEditingPreview] = useState<OneClickEmailPreview | null>(null);
  const [editingSubject, setEditingSubject] = useState("");
  const [editingBody, setEditingBody] = useState("");
  const [editingBodyHtml, setEditingBodyHtml] = useState("");
  const [taskOptionsHuntId, setTaskOptionsHuntId] = useState("");
  const [taskDisplayNameInput, setTaskDisplayNameInput] = useState("");
  const [taskNoteInput, setTaskNoteInput] = useState("");
  const [templateSearch, setTemplateSearch] = useState("");
  const [editingTemplateId, setEditingTemplateId] = useState("");
  const [pendingProfileSelectionIds, setPendingProfileSelectionIds] = useState<Set<string>>(new Set());
  const [libraryName, setLibraryName] = useState("");
  const [libraryCategory, setLibraryCategory] = useState("development");
  const [libraryLanguage, setLibraryLanguage] = useState("en");
  const [libraryProductTags, setLibraryProductTags] = useState("");
  const [libraryCustomerTypeTags, setLibraryCustomerTypeTags] = useState("");
  const [librarySubject, setLibrarySubject] = useState("");
  const [libraryBody, setLibraryBody] = useState("");
  const [libraryBodyHtml, setLibraryBodyHtml] = useState("");

  const { data: automationStatus } = useQuery({
    queryKey: ["automation-status"],
    queryFn: api.getAutomationStatus,
    refetchInterval: 10000,
  });
  const { data: tasks = [], isLoading: tasksLoading, error: tasksError } = useQuery({
    queryKey: ["email-tasks"],
    queryFn: api.listEmailTasks,
    refetchInterval: 15000,
  });
  const { data: templateLibrary = [], isLoading: templatesLoading } = useQuery({
    queryKey: ["email-template-library"],
    queryFn: api.listEmailTemplates,
  });

  useEffect(() => {
    if (!selectedHuntId && tasks.length > 0) setSelectedHuntId(tasks[0].hunt_id);
  }, [selectedHuntId, tasks]);

  const { data: selectedTask, isLoading: taskLoading } = useQuery({
    queryKey: ["email-task", selectedHuntId],
    queryFn: () => api.getEmailTask(selectedHuntId),
    enabled: !!selectedHuntId,
    refetchInterval: 10000,
  });
  const { data: sendStatus } = useQuery({
    queryKey: ["email-send-request", sendRequestId],
    queryFn: () => api.getEmailSendRequest(sendRequestId),
    enabled: Boolean(sendRequestId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 2000;
    },
  });
  const { data: sendRecords = [], isLoading: sendRecordsLoading } = useQuery({
    queryKey: ["email-send-requests", selectedHuntId],
    queryFn: () => api.listEmailSendRequests(selectedHuntId),
    enabled: Boolean(selectedHuntId),
    refetchInterval: 10000,
  });

  useEffect(() => {
    if (!selectedTask?.workspace) return;
    setSubjectTemplate(selectedTask.workspace.subject_template || DEFAULT_SUBJECT);
    setBodyTemplate(selectedTask.workspace.body_template || DEFAULT_BODY);
    setBodyHtmlTemplate(selectedTask.workspace.body_html_template || "");
  }, [selectedTask?.workspace?.subject_template, selectedTask?.workspace?.body_template, selectedTask?.workspace?.body_html_template]);

  useEffect(() => {
    setEditedPreviewMap({});
    setEditingPreview(null);
    setPreview(null);
    setSendRequestId("");
    setBodyHtmlTemplate("");
  }, [selectedHuntId]);

  const filteredProfiles = useMemo(() => {
    const rows = selectedTask?.profiles || [];
    if (profileFilter === "bookmarked") return rows.filter((item) => Boolean(item.selected_for_outreach));
    if (profileFilter === "sendable") return rows.filter((item) => item.send_eligibility === "sendable");
    if (profileFilter === "missing_email") return rows.filter((item) => item.send_eligibility === "missing_email");
    if (profileFilter === "blocked") return rows.filter((item) => item.send_eligibility !== "sendable");
    return rows;
  }, [profileFilter, selectedTask?.profiles]);

  const selectedProfile = useMemo(() => {
    const rows = selectedTask?.profiles || [];
    return rows.find((item) => item.id === selectedProfileId) || filteredProfiles[0] || rows[0] || null;
  }, [filteredProfiles, selectedProfileId, selectedTask?.profiles]);

  useEffect(() => {
    if (!selectedProfile) return;
    if (!selectedProfileId || selectedProfile.id !== selectedProfileId) setSelectedProfileId(selectedProfile.id);
    setEmailInput(selectedProfile.recipient_email || "");
    setNameInput(selectedProfile.recipient_name || "");
    setTitleInput(selectedProfile.recipient_title || "");
  }, [selectedProfile?.id]);

  const invalidateSelectedTask = async () => {
    await queryClient.invalidateQueries({ queryKey: ["email-task", selectedHuntId] });
    await queryClient.invalidateQueries({ queryKey: ["email-tasks"] });
  };

  const updateProfileMutation = useMutation({
    mutationFn: ({ profileId, email, name, title }: { profileId: string; email: string; name: string; title: string }) => api.updateEmailContactProfile(profileId, {
      recipient_email: email,
      recipient_name: name,
      recipient_title: title,
    }),
    onSuccess: async (data) => {
      setSelectedProfileId(data.profile.id);
      setEmailInput(data.profile.recipient_email || "");
      setNameInput(data.profile.recipient_name || "");
      setTitleInput(data.profile.recipient_title || "");
      setEnrichResult(null);
      setPreview(null);
      await invalidateSelectedTask();
    },
  });

  const sendListMutation = useMutation({
    mutationFn: ({ profileId, action }: { profileId: string; action: "exclude" | "restore" }) => action === "exclude"
      ? api.excludeEmailContactProfileFromSend(profileId)
      : api.restoreEmailContactProfileToSend(profileId),
    onSuccess: async (data) => {
      setSelectedProfileId(data.profile.id);
      setEmailInput(data.profile.recipient_email || "");
      setNameInput(data.profile.recipient_name || "");
      setTitleInput(data.profile.recipient_title || "");
      setPreview(null);
      await invalidateSelectedTask();
    },
  });

  const profileSelectionMutation = useMutation({
    mutationFn: ({ profileId, selected }: { profileId: string; selected: boolean }) =>
      api.setEmailContactProfileOutreachSelection(profileId, selected),
    onMutate: async ({ profileId, selected }) => {
      setPendingProfileSelectionIds((current) => new Set(current).add(profileId));
      await queryClient.cancelQueries({ queryKey: ["email-task", selectedHuntId] });
      const previousTask = queryClient.getQueryData(["email-task", selectedHuntId]);
      queryClient.setQueryData(["email-task", selectedHuntId], (current: unknown) => updateProfileSelectionInTask(current, profileId, selected));
      return { previousTask, profileId };
    },
    onError: (_error, _variables, context) => {
      if (context?.previousTask) queryClient.setQueryData(["email-task", selectedHuntId], context.previousTask);
    },
    onSuccess: (data, variables) => {
      setSelectedProfileId(data.profile.id);
      queryClient.setQueryData(["email-task", selectedHuntId], (current: unknown) => updateProfileSelectionInTask(current, variables.profileId, Boolean(data.profile.selected_for_outreach)));
      queryClient.invalidateQueries({ queryKey: ["email-tasks"] });
    },
    onSettled: (_data, _error, variables) => {
      if (!variables?.profileId) return;
      setPendingProfileSelectionIds((current) => {
        const next = new Set(current);
        next.delete(variables.profileId);
        return next;
      });
    },
  });

  const enrichProfileMutation = useMutation({
    mutationFn: (profileId: string) => api.enrichEmailContactProfile(profileId),
    onSuccess: (data) => {
      setEnrichResult({ profileId: data.profile_id, candidates: data.candidates, checkedUrls: data.checked_urls, errors: data.errors });
    },
  });

  const chatMutation = useMutation({
    mutationFn: () => api.chatEmailTemplate(selectedHuntId, chatInput),
    onSuccess: async (data) => {
      setSubjectTemplate(data.subject_template || DEFAULT_SUBJECT);
      setBodyTemplate(data.body_template || DEFAULT_BODY);
      setBodyHtmlTemplate(data.body_html_template || "");
      setChatInput("");
      await invalidateSelectedTask();
    },
  });
  const previewMutation = useMutation({
    mutationFn: () => api.previewOneClickEmail(selectedHuntId, { subject_template: subjectTemplate, body_template: bodyTemplate, body_html_template: bodyHtmlTemplate, overrides: editedPreviewMap }),
    onSuccess: (data) => {
      setPreview(data);
      setStartResult(null);
      setSendRequestId("");
    },
  });
  const startMutation = useMutation({
    mutationFn: () => {
      if (!preview?.preview_id) throw new Error("请先预览代发，生成发送快照");
      const idempotencyKey = `one-click-${selectedHuntId}-${preview.preview_id}`;
      return api.startOneClickEmail(selectedHuntId, { preview_id: preview.preview_id, subject_template: subjectTemplate, body_template: bodyTemplate, body_html_template: bodyHtmlTemplate, overrides: editedPreviewMap }, idempotencyKey);
    },
    onSuccess: async (data) => {
      setStartResult(data);
      setSendRequestId(data.send_request_id || "");
      setSelectedRecordId(data.send_request_id || "");
      setSendStatusModalOpen(true);
      queryClient.setQueryData(["email-send-request", data.send_request_id], {
        send_request_id: data.send_request_id,
        hunt_id: data.hunt_id,
        campaign_id: data.campaign_id,
        status: data.status || "queued",
        queued_count: data.queued_count || 0,
        duplicate_count: data.duplicate_count || 0,
        skipped_count: data.skipped_count || 0,
        summary: {
          queued: data.queued_count || 0,
          sending: 0,
          smtp_accepted: 0,
          retry_wait: 0,
          failed: 0,
          unknown: 0,
          cancelled: 0,
        },
        messages: [],
      });
      await invalidateSelectedTask();
      await queryClient.invalidateQueries({ queryKey: ["email-send-requests", selectedHuntId] });
      await queryClient.invalidateQueries({ queryKey: ["automation-status"] });
    },
  });

  const hideTaskMutation = useMutation({
    mutationFn: (huntId: string) => api.hideEmailTask(huntId),
    onSuccess: async (_data, huntId) => {
      if (selectedHuntId === huntId) {
        const nextTask = tasks.find((task) => task.hunt_id !== huntId);
        setSelectedHuntId(nextTask?.hunt_id || "");
        setSelectedProfileId("");
        setPreview(null);
        setStartResult(null);
        setSendRequestId("");
        setSelectedRecordId("");
      }
      await queryClient.invalidateQueries({ queryKey: ["email-tasks"] });
    },
  });

  const taskPreferencesMutation = useMutation({
    mutationFn: ({ huntId, displayName, note }: { huntId: string; displayName: string; note: string }) => api.updateEmailTaskPreferences(huntId, { display_name: displayName, note }),
    onSuccess: async () => {
      setTaskOptionsHuntId("");
      await queryClient.invalidateQueries({ queryKey: ["email-tasks"] });
      await queryClient.invalidateQueries({ queryKey: ["email-task", selectedHuntId] });
    },
  });

  const resetTemplateForm = () => {
    setEditingTemplateId("");
    setLibraryName("");
    setLibraryCategory("development");
    setLibraryLanguage("en");
    setLibraryProductTags("");
    setLibraryCustomerTypeTags("");
    setLibrarySubject("");
    setLibraryBody("");
    setLibraryBodyHtml("");
  };

  const editTemplate = (template: EmailTemplateLibraryItem) => {
    setEditingTemplateId(template.id);
    setLibraryName(template.name || "");
    setLibraryCategory(template.category || "custom");
    setLibraryLanguage(template.language || "en");
    setLibraryProductTags((template.product_tags || []).join("，"));
    setLibraryCustomerTypeTags((template.customer_type_tags || []).join("，"));
    setLibrarySubject(template.subject_template || "");
    setLibraryBody(template.body_template || "");
    setLibraryBodyHtml(template.body_html_template || "");
    setWorkspaceTab("library");
  };

  const templatePayload = () => ({
    name: libraryName.trim(),
    category: libraryCategory,
    language: libraryLanguage.trim() || "en",
    product_tags: splitTags(libraryProductTags),
    customer_type_tags: splitTags(libraryCustomerTypeTags),
    subject_template: librarySubject.trim(),
    body_template: libraryBody.trim(),
    body_html_template: libraryBodyHtml.trim(),
  });

  const saveLibraryMutation = useMutation({
    mutationFn: () => editingTemplateId
      ? api.updateEmailTemplate(editingTemplateId, templatePayload())
      : api.createEmailTemplate(templatePayload()),
    onSuccess: async (template) => {
      await queryClient.invalidateQueries({ queryKey: ["email-template-library"] });
      editTemplate(template);
    },
  });

  const deleteLibraryMutation = useMutation({
    mutationFn: (templateId: string) => api.deleteEmailTemplate(templateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["email-template-library"] });
      resetTemplateForm();
    },
  });

  const applyTemplateMutation = useMutation({
    mutationFn: (templateId: string) => api.applyEmailTemplate(selectedHuntId, templateId),
    onSuccess: async (data) => {
      setSubjectTemplate(data.subject_template || DEFAULT_SUBJECT);
      setBodyTemplate(data.body_template || DEFAULT_BODY);
      setBodyHtmlTemplate(data.body_html_template || "");
      setPreview(null);
      setEditedPreviewMap({});
      setWorkspaceTab("template");
      await invalidateSelectedTask();
      await queryClient.invalidateQueries({ queryKey: ["email-template-library"] });
    },
  });

  const emailQueue = automationStatus?.email_queue;
  const filteredTemplateLibrary = useMemo(() => {
    const keyword = templateSearch.trim().toLowerCase();
    if (!keyword) return templateLibrary;
    return templateLibrary.filter((item) => [
      item.name,
      categoryLabel(item.category),
      item.language,
      item.subject_template,
      ...(item.product_tags || []),
      ...(item.customer_type_tags || []),
    ].join(" ").toLowerCase().includes(keyword));
  }, [templateLibrary, templateSearch]);
  const canSend = Boolean(selectedHuntId && subjectTemplate.trim() && bodyTemplate.trim() && preview?.sendable_count);
  const activeSendStatus = sendStatus || (startResult ? {
    send_request_id: startResult.send_request_id,
    hunt_id: startResult.hunt_id,
    campaign_id: startResult.campaign_id,
    campaign_name: "一键代发",
    from_email: "",
    status: startResult.status || "queued",
    queued_count: startResult.queued_count || 0,
    duplicate_count: startResult.duplicate_count || 0,
    skipped_count: startResult.skipped_count || 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    send_limits: {},
    summary: {
      queued: startResult.queued_count || 0,
      sending: 0,
      smtp_accepted: 0,
      retry_wait: 0,
      failed: 0,
      unknown: 0,
      cancelled: 0,
    },
    messages: [],
  } : null);
  const sendSummary = activeSendStatus?.summary || {};
  const selectedSendRecord = sendRecords.find((item) => item.send_request_id === selectedRecordId) || activeSendStatus;
  const taskOptionsTask = tasks.find((task) => task.hunt_id === taskOptionsHuntId) || null;
  const activeSendTotals = sendRequestTotals(activeSendStatus);
  const selectedRecordTotals = sendRequestTotals(selectedSendRecord);
  const previewNeedsReview = Boolean(preview?.previews.some((item) => item.render_status === "missing_variables" || item.render_status === "invalid_variables"));
  const openPreviewEditor = (item: OneClickEmailPreview) => {
    const override = editedPreviewMap[item.profile_id];
    setEditingPreview(item);
    setEditingSubject(override?.subject || item.subject || "");
    setEditingBody(override?.body_text || item.body_text || "");
    setEditingBodyHtml(override?.body_html || item.body_html || "");
  };
  const savePreviewEditor = () => {
    if (!editingPreview) return;
    const nextOverride = { subject: editingSubject, body_text: editingBody, body_html: editingBodyHtml };
    setEditedPreviewMap((current) => ({ ...current, [editingPreview.profile_id]: nextOverride }));
    setPreview((current) => current ? {
      ...current,
      previews: current.previews.map((item) => item.profile_id === editingPreview.profile_id ? { ...item, ...nextOverride, edited: true } : item),
      skipped: current.skipped.map((item) => item.profile_id === editingPreview.profile_id ? { ...item, ...nextOverride, edited: true } : item),
    } : current);
    setEditingPreview(null);
  };
  const openTaskOptions = (task: typeof tasks[number]) => {
    setTaskOptionsHuntId(task.hunt_id);
    setTaskDisplayNameInput(task.display_name || "");
    setTaskNoteInput(task.note || "");
  };
  const activeEnrichCandidates = useMemo(() => {
    if (!enrichResult || !selectedProfile) return [] as EmailCandidateSuggestion[];
    if (enrichResult.profileId !== selectedProfile.id) return [] as EmailCandidateSuggestion[];
    return Array.isArray(enrichResult.candidates) ? enrichResult.candidates : [];
  }, [enrichResult, selectedProfile]);

  return (
    <div className="space-y-5">
      <section className="rounded-md border bg-white px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary"><Mail className="h-5 w-5" /></div>
              <Badge variant="outline">Email Outreach</Badge>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">邮件发送</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">先补全客户邮件资料，再填写邮件模板；系统只映射变量并进入受控队列。</p>
          </div>
        </div>
      </section>

      {tasksError ? <Card className="rounded-md border-amber-300"><CardContent className="py-4 text-sm text-amber-700">任务加载失败：{tasksError instanceof Error ? tasksError.message : "请稍后刷新"}</CardContent></Card> : null}
      {startMutation.isError ? <Card className="rounded-md border-amber-300"><CardContent className="py-4 text-sm text-amber-700">代发未启动：{startMutation.error instanceof Error ? startMutation.error.message : "请检查 SMTP 配置"}</CardContent></Card> : null}
      {updateProfileMutation.isError ? <Card className="rounded-md border-amber-300"><CardContent className="py-4 text-sm text-amber-700">邮箱保存失败：{updateProfileMutation.error instanceof Error ? updateProfileMutation.error.message : "请检查邮箱格式"}</CardContent></Card> : null}
      {updateProfileMutation.isSuccess && updateProfileMutation.data?.profile?.sync_result?.synced ? <Card className="rounded-md border-emerald-200 bg-emerald-50"><CardContent className="py-4 text-sm text-emerald-800"><CheckCircle2 className="mr-2 inline h-4 w-4" />邮箱已保存，并同步回原任务客户信息。</CardContent></Card> : null}
      {sendListMutation.isError ? <Card className="rounded-md border-amber-300"><CardContent className="py-4 text-sm text-amber-700">发送名单更新失败：{sendListMutation.error instanceof Error ? sendListMutation.error.message : "请稍后重试"}</CardContent></Card> : null}
      {saveLibraryMutation.isError ? <Card className="rounded-md border-amber-300"><CardContent className="py-4 text-sm text-amber-700">模板保存失败：{saveLibraryMutation.error instanceof Error ? saveLibraryMutation.error.message : "请检查模板内容"}</CardContent></Card> : null}
      {applyTemplateMutation.isError ? <Card className="rounded-md border-amber-300"><CardContent className="py-4 text-sm text-amber-700">模板选择失败：{applyTemplateMutation.error instanceof Error ? applyTemplateMutation.error.message : "请稍后重试"}</CardContent></Card> : null}

      <section className="grid gap-4 md:grid-cols-4">
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">邮件任务</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{tasks.length}</div></CardContent></Card>
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">待发送</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{emailQueue?.pending || 0}</div></CardContent></Card>
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">已发送</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{emailQueue?.sent || 0}</div></CardContent></Card>
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">已回复</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{emailQueue?.replied_sequences || 0}</div></CardContent></Card>
      </section>

      <section className="grid min-h-[720px] gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="overflow-hidden rounded-md">
          <CardHeader className="border-b"><CardTitle className="text-base">任务分组</CardTitle></CardHeader>
          <CardContent className="max-h-[660px] space-y-2 overflow-y-auto p-3">
            {tasksLoading ? <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />加载任务中</div> : null}
            {tasks.map((task) => (
              <div key={task.hunt_id} className={`rounded-md border text-sm transition-colors ${selectedHuntId === task.hunt_id ? "border-primary bg-primary/5" : "bg-white hover:bg-muted/40"}`}>
                <div className="flex items-start gap-2 px-3 py-3">
                  <button
                    type="button"
                    onClick={() => { setSelectedHuntId(task.hunt_id); setPreview(null); setStartResult(null); setSendRequestId(""); setSelectedRecordId(""); setEditedPreviewMap({}); setEditingPreview(null); setSelectedProfileId(""); setWorkspaceTab("profiles"); }}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="flex items-center justify-between gap-2"><span className="font-medium">{task.display_name || task.target_regions.join("、") || task.hunt_id.slice(0, 8)}</span><Badge variant="outline">{task.sendable_count}/{task.profile_count}</Badge></div>
                    <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{task.note || task.product_keywords.join("、") || task.target_customer_profile || "未标注产品"}</p>
                  </button>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded border px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted"
                    title="任务选项"
                    onClick={() => openTaskOptions(task)}
                  >
                    <MoreHorizontal className="h-4 w-4" />选项
                  </button>
                </div>
              </div>
            ))}
            {!tasksLoading && tasks.length === 0 ? <div className="rounded-md border border-dashed p-5 text-center text-sm text-muted-foreground">暂无邮件任务，请先在任务详情页提取邮件信息。</div> : null}
          </CardContent>
        </Card>

        <Card className="min-w-0 overflow-hidden rounded-md">
          <CardHeader className="border-b">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <CardTitle className="text-base">{workspaceTab === "profiles" ? "客户邮件资料" : workspaceTab === "template" ? "一键代发模板" : workspaceTab === "library" ? "邮件模板库" : "发送记录"}</CardTitle>
              <div className="flex rounded-md border bg-muted/30 p-1">
                {([[
                  "profiles", "客户邮件资料"], ["template", "一键代发模板"], ["library", "邮件模板库"], ["records", "发送记录"],
                ] as const).map(([value, label]) => (
                  <button key={value} type="button" onClick={() => setWorkspaceTab(value)} className={`rounded px-3 py-1.5 text-sm font-medium ${workspaceTab === value ? "bg-white text-primary shadow-sm" : "text-muted-foreground"}`}>{label}</button>
                ))}
              </div>
            </div>
          </CardHeader>

          {workspaceTab === "profiles" ? (
            <CardContent className="grid min-h-[650px] gap-4 p-4 2xl:grid-cols-[minmax(0,1fr)_420px]">
              <section className="min-w-0 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {([[
                    "all", `全部 (${selectedTask?.profile_count || 0})`], ["bookmarked", `书签客户 (${(selectedTask?.profiles || []).filter((item) => Boolean(item.selected_for_outreach)).length})`], ["sendable", `可发送 (${selectedTask?.sendable_count || 0})`], ["missing_email", "缺邮箱"], ["blocked", `待补全 (${selectedTask?.blocked_count || 0})`],
                  ] as const).map(([value, label]) => <Button key={value} type="button" size="sm" variant={profileFilter === value ? "default" : "outline"} onClick={() => setProfileFilter(value)}>{label}</Button>)}
                </div>
                {taskLoading ? <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />加载客户资料</div> : null}
                {!taskLoading && filteredProfiles.length === 0 ? <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">当前筛选下没有客户资料。</div> : null}
                <div className="grid max-h-[560px] gap-3 overflow-y-auto pr-1 xl:grid-cols-2">
                  {filteredProfiles.map((profile) => <ProfileListItem key={profile.id} profile={profile} selected={selectedProfile?.id === profile.id} onSelect={() => { setSelectedProfileId(profile.id); setEnrichResult(null); }} disabled={pendingProfileSelectionIds.has(profile.id)} onToggleBookmark={() => profileSelectionMutation.mutate({ profileId: profile.id, selected: !profile.selected_for_outreach })} />)}
                </div>
              </section>

              <aside className="rounded-md border bg-white p-4">
                {selectedProfile ? (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="truncate text-base font-semibold">{selectedProfile.company_name}</h3>
                        <p className="mt-1 text-xs text-muted-foreground">{selectedProfile.country_or_region || selectedProfile.customer_type || "未标注地区"}</p>
                      </div>
                      {statusBadge(selectedProfile.send_eligibility)}
                    </div>
                    <p className="text-sm leading-6 text-muted-foreground">{selectedProfile.company_summary || selectedProfile.evidence_summary || "暂无企业介绍"}</p>
                    <div className="rounded-md bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
                      <p className="font-medium text-foreground">证据与变量</p>
                      <p>产品：{compactList(selectedProfile.matched_product_keywords)}</p>
                      <p>证据：{selectedProfile.evidence_summary || "-"}</p>
                    </div>
                    <div className="grid gap-3">
                      <div className="space-y-1.5"><label className="text-sm font-medium">收件邮箱</label><Input value={emailInput} onChange={(event) => setEmailInput(event.target.value)} placeholder="info@example.com" /></div>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="space-y-1.5"><label className="text-sm font-medium">联系人</label><Input value={nameInput} onChange={(event) => setNameInput(event.target.value)} placeholder="可选" /></div>
                        <div className="space-y-1.5"><label className="text-sm font-medium">职位</label><Input value={titleInput} onChange={(event) => setTitleInput(event.target.value)} placeholder="可选" /></div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" className="gap-2" disabled={!emailInput.trim() || updateProfileMutation.isPending} onClick={() => updateProfileMutation.mutate({ profileId: selectedProfile.id, email: emailInput, name: nameInput, title: titleInput })}>
                        {updateProfileMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        保存邮箱
                      </Button>
                      <Button type="button" variant="outline" className="gap-2" disabled={!selectedProfile.website} onClick={() => openWebsite(selectedProfile.website)}><ExternalLink className="h-4 w-4" />打开官网</Button>
                      <Button type="button" variant="outline" className="gap-2" disabled={!selectedProfile.website || enrichProfileMutation.isPending} onClick={() => enrichProfileMutation.mutate(selectedProfile.id)}>
                        {enrichProfileMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                        AI 查找邮箱
                      </Button>
                    </div>
                    <div className="flex justify-end border-t pt-3">
                      {selectedProfile.send_eligibility === "manually_excluded" ? (
                        <Button
                          type="button"
                          variant="outline"
                          className="gap-2"
                          disabled={sendListMutation.isPending}
                          onClick={() => {
                            if (!window.confirm("确认恢复该客户进入发送名单？")) return;
                            sendListMutation.mutate({ profileId: selectedProfile.id, action: "restore" });
                          }}
                        >
                          {sendListMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                          恢复发送
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          className="gap-2 border-amber-300 text-amber-800 hover:bg-amber-50"
                          disabled={sendListMutation.isPending}
                          onClick={() => {
                            if (!window.confirm("确认将该客户移出本次发送名单？客户仍会保留在“全部”里。")) return;
                            sendListMutation.mutate({ profileId: selectedProfile.id, action: "exclude" });
                          }}
                        >
                          {sendListMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                          移出发送名单
                        </Button>
                      )}
                    </div>
                    {selectedProfile.skip_reason ? <p className="text-xs text-amber-700">{selectedProfile.skip_reason}</p> : null}
                    {activeEnrichCandidates.length > 0 ? (
                      <div className="space-y-2 rounded-md border p-3">
                        <p className="text-sm font-medium">发现的邮箱</p>
                        {activeEnrichCandidates.map((candidate) => (
                          <button key={`${candidate.email}-${candidate.source_url}`} type="button" className="w-full rounded-md border bg-muted/20 p-2 text-left text-xs hover:bg-muted" onClick={() => updateProfileMutation.mutate({ profileId: selectedProfile.id, email: candidate.email, name: nameInput, title: titleInput })}>
                            <p className="font-medium text-foreground">{candidate.email} · {Math.round(candidate.confidence * 100)}%</p>
                            <p className="mt-1 truncate text-muted-foreground">{candidate.reason}：{candidate.source_url}</p>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {enrichProfileMutation.isSuccess && enrichResult && selectedProfile && enrichResult.profileId === selectedProfile.id && activeEnrichCandidates.length === 0 ? <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">未在官网常见页面发现邮箱，可以点击“打开官网”人工查找后手动填写。</p> : null}
                  </div>
                ) : <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">请选择一个客户。</div>}
              </aside>
            </CardContent>
          ) : workspaceTab === "template" ? (
            <CardContent className="grid min-h-[650px] gap-4 p-4 2xl:grid-cols-[420px_minmax(0,1fr)]">
              <section className="space-y-4 rounded-md border bg-white p-4">
                <div className="rounded-md bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
                  <p className="font-medium text-foreground">变量格式：{"{{变量名}}"}</p>
                  <p>{SAFE_TEMPLATE_VARIABLES.join("、")}</p>
                  <p className="mt-1 text-amber-700">系统只替换变量，不自动写邮件正文；未列出的变量会保留原样并提示检查。</p>
                </div>
                <div className="space-y-1.5"><label className="text-sm font-medium">主题模板</label><Input value={subjectTemplate} onChange={(event) => { setSubjectTemplate(event.target.value); setPreview(null); setStartResult(null); setSendRequestId(""); }} /></div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">正文模板</label>
                  <RichEmailEditor
                    html={bodyHtmlTemplate}
                    text={bodyTemplate}
                    onChange={(html, text) => { setBodyHtmlTemplate(html); setBodyTemplate(text); setPreview(null); setStartResult(null); setSendRequestId(""); }}
                  />
                </div>
                <div className="space-y-2 rounded-md border p-3">
                  <p className="text-sm font-medium">模板助手</p>
                  <div className="max-h-[160px] space-y-2 overflow-y-auto text-xs text-muted-foreground">
                    {(selectedTask?.workspace.messages || []).slice(-6).map((message, index) => <div key={`${message.role}-${index}`} className="rounded-md bg-muted/40 p-2"><span className="font-medium text-foreground">{message.role === "user" ? "我" : "AI"}：</span>{message.content}</div>)}
                  </div>
                  <textarea className="min-h-[100px] w-full rounded-md border px-3 py-2 text-sm" placeholder={"把你的邮件模板粘贴到这里，例如：\nSubject: Hi {{company_name}}\nBody: Hi {{recipient_name}}, ..."} value={chatInput} onChange={(event) => setChatInput(event.target.value)} />
                  <Button type="button" className="w-full gap-2" disabled={!selectedHuntId || !chatInput.trim() || chatMutation.isPending} onClick={() => chatMutation.mutate()}>{chatMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}识别模板变量</Button>
                </div>
              </section>

              <section className="space-y-4 rounded-md border bg-white p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h3 className="text-base font-semibold">代发预览</h3>
                    <p className="mt-1 text-sm text-muted-foreground">当前可发送 {selectedTask?.sendable_count || 0}，待补全 {selectedTask?.blocked_count || 0}。</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" className="gap-2" onClick={() => setWorkspaceTab("library")}><BookOpen className="h-4 w-4" />选择模板</Button>
                    <Button type="button" variant="outline" className="gap-2" disabled={!selectedHuntId || previewMutation.isPending} onClick={() => previewMutation.mutate()}>{previewMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}预览代发</Button>
                    <Button
                      type="button"
                      className="gap-2"
                      disabled={!preview?.preview_id || !canSend || startMutation.isPending}
                      onClick={() => {
                        if (!preview) return;
                        const ok = window.confirm(`确认进入发送队列？\n可发送：${preview.sendable_count}\n跳过：${preview.skipped_count}\n\n确认后系统会异步发送，并在页面展示状态。`);
                        if (ok) startMutation.mutate();
                      }}
                    >{startMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{preview?.preview_id ? "确认进入队列" : "请先预览代发"}</Button>
                  </div>
                </div>
                {selectedTask?.blocked_count ? <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">还有 {selectedTask.blocked_count} 个客户缺少邮箱或不可发送，本次只会发送可发送客户。</div> : null}
                {preview ? <div className="rounded-md border bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 className="mr-2 inline h-4 w-4" />可发送 {preview.sendable_count}，跳过 {preview.skipped_count}。快照 15 分钟有效。</div> : null}
                {startMutation.isPending ? (
                  <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
                    <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />正在创建发送队列，请稍候。
                  </div>
                ) : null}
                {activeSendStatus ? (
                  <div className="rounded-md border bg-white p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium">发送状态：{activeSendStatus.status === "completed" ? "已完成" : activeSendStatus.status === "queued" ? "已进入队列" : activeSendStatus.status}</p>
                      <Badge variant="outline">请求 {String(activeSendStatus.send_request_id || "").slice(0, 8)}</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs md:grid-cols-4">
                      <div className="rounded-md bg-muted/40 px-3 py-2">排队 {sendSummary.queued || 0}</div>
                      <div className="rounded-md bg-muted/40 px-3 py-2">发送中 {sendSummary.sending || 0}</div>
                      <div className="rounded-md bg-emerald-50 px-3 py-2 text-emerald-800">SMTP 已接收 {sendSummary.smtp_accepted || 0}</div>
                      <div className="rounded-md bg-amber-50 px-3 py-2 text-amber-800">等待重试 {sendSummary.retry_wait || 0}</div>
                      <div className="rounded-md bg-red-50 px-3 py-2 text-red-800">失败 {sendSummary.failed || 0}</div>
                      <div className="rounded-md bg-slate-50 px-3 py-2 text-slate-700">结果不确定 {sendSummary.unknown || 0}</div>
                    </div>
                    {activeSendStatus.messages?.some((item) => item.status === "failed" || item.status === "unknown") ? (
                      <div className="mt-3 max-h-32 overflow-y-auto rounded-md border bg-muted/20 p-2 text-xs text-muted-foreground">
                        {activeSendStatus.messages.filter((item) => item.status === "failed" || item.status === "unknown").map((item) => (
                          <p key={String(item.message_id)} className="mb-1 last:mb-0">{String(item.recipient_email || "")}：{String(item.last_error_type || item.failure_reason || "发送失败")} {item.last_error_message ? `· ${String(item.last_error_message)}` : ""}</p>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {previewNeedsReview ? <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">部分客户存在缺失变量或无效变量，客户不会因此减少；建议点击客户预览确认。</div> : null}
                {preview?.previews.length ? (
                  <div className="max-h-[470px] space-y-2 overflow-y-auto pr-1">
                    {preview.previews.map((item) => (
                      <button key={item.profile_id} type="button" onClick={() => openPreviewEditor(item)} className="w-full rounded-md border bg-white p-3 text-left text-sm transition-colors hover:border-primary/50 hover:bg-primary/5">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate font-medium">{item.company_name} · {item.recipient_email}</p>
                            <p className="mt-1 truncate text-muted-foreground">{item.subject}</p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            {item.edited ? <Badge variant="success">已修改</Badge> : null}
                            {item.render_status === "missing_variables" ? <Badge variant="warning">缺少变量</Badge> : null}
                            {item.render_status === "invalid_variables" ? <Badge variant="destructive">无效变量</Badge> : null}
                            {item.render_status === "ready" ? <Badge variant="outline">变量完整</Badge> : null}
                            <span className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground"><Pencil className="h-3.5 w-3.5" />查看/编辑</span>
                          </div>
                        </div>
                        {item.body_html ? <div className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground" dangerouslySetInnerHTML={{ __html: item.body_html }} /> : <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{item.body_text}</p>}
                      </button>
                    ))}
                  </div>
                ) : <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">先点击“预览代发”，确认客户数量和邮件内容。</div>}
              </section>
            </CardContent>
          ) : workspaceTab === "library" ? (
            <CardContent className="grid min-h-[650px] gap-4 p-4 2xl:grid-cols-[minmax(0,1fr)_460px]">
              <section className="min-w-0 space-y-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h3 className="text-base font-semibold">可复用模板</h3>
                    <p className="mt-1 text-sm text-muted-foreground">选择后会填入当前任务的一键代发模板，不会直接发送。</p>
                  </div>
                  <Button type="button" variant="outline" className="gap-2" onClick={resetTemplateForm}><Plus className="h-4 w-4" />新建模板</Button>
                </div>
                <Input value={templateSearch} onChange={(event) => setTemplateSearch(event.target.value)} placeholder="按名称、类型、语言、产品搜索模板" />
                {templatesLoading ? <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />加载模板库</div> : null}
                {!templatesLoading && filteredTemplateLibrary.length === 0 ? <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">暂无模板。可以在右侧新建开发信、节日祝福信或跟进信模板。</div> : null}
                <div className="grid max-h-[560px] gap-3 overflow-y-auto pr-1 xl:grid-cols-2">
                  {filteredTemplateLibrary.map((template) => (
                    <div key={template.id} className={`rounded-md border bg-white p-4 ${editingTemplateId === template.id ? "border-primary bg-primary/5" : ""}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h4 className="truncate text-sm font-semibold">{template.name}</h4>
                          <p className="mt-1 text-xs text-muted-foreground">{categoryLabel(template.category)} · {template.language || "en"} · 使用 {template.usage_count || 0}</p>
                        </div>
                        {template.invalid_variables?.length ? <Badge variant="warning">变量需检查</Badge> : <Badge variant="outline">可用</Badge>}
                      </div>
                      <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">{template.subject_template || "无主题"}</p>
                      {template.body_html_template ? <div className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground" dangerouslySetInnerHTML={{ __html: template.body_html_template }} /> : <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{template.body_template}</p>}
                      <div className="mt-3 flex flex-wrap gap-1">
                        {[...(template.product_tags || []), ...(template.customer_type_tags || [])].slice(0, 4).map((tag) => <Badge key={tag} variant="secondary">{tag}</Badge>)}
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button type="button" size="sm" className="gap-2" disabled={!selectedHuntId || applyTemplateMutation.isPending} onClick={() => applyTemplateMutation.mutate(template.id)}>{applyTemplateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <BookOpen className="h-4 w-4" />}使用模板</Button>
                        <Button type="button" size="sm" variant="outline" className="gap-2" onClick={() => editTemplate(template)}><Pencil className="h-4 w-4" />编辑</Button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <aside className="space-y-4 rounded-md border bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold">{editingTemplateId ? "编辑模板" : "新建模板"}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">模板保存到全局模板库，可跨任务复用。</p>
                  </div>
                  {editingTemplateId ? <Badge variant="outline">已选中</Badge> : null}
                </div>
                <div className="grid gap-3">
                  <div className="space-y-1.5"><label className="text-sm font-medium">模板名称</label><Input value={libraryName} onChange={(event) => setLibraryName(event.target.value)} placeholder="例如：牙科教学设备英文开发信" /></div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-1.5"><label className="text-sm font-medium">类型</label><select className="h-10 w-full rounded-md border bg-white px-3 text-sm" value={libraryCategory} onChange={(event) => setLibraryCategory(event.target.value)}>{TEMPLATE_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
                    <div className="space-y-1.5"><label className="text-sm font-medium">语言</label><Input value={libraryLanguage} onChange={(event) => setLibraryLanguage(event.target.value)} placeholder="en / zh / th" /></div>
                  </div>
                  <div className="space-y-1.5"><label className="text-sm font-medium">产品标签</label><Input value={libraryProductTags} onChange={(event) => setLibraryProductTags(event.target.value)} placeholder="dental simulator，phantom head" /></div>
                  <div className="space-y-1.5"><label className="text-sm font-medium">客户类型标签</label><Input value={libraryCustomerTypeTags} onChange={(event) => setLibraryCustomerTypeTags(event.target.value)} placeholder="牙科学校，经销商" /></div>
                  <div className="space-y-1.5"><label className="text-sm font-medium">主题模板</label><Input value={librarySubject} onChange={(event) => setLibrarySubject(event.target.value)} placeholder="JPS dental training products for {{company_name}}" /></div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">正文模板</label>
                    <RichEmailEditor html={libraryBodyHtml} text={libraryBody} onChange={(html, text) => { setLibraryBodyHtml(html); setLibraryBody(text); }} />
                  </div>
                </div>
                <div className="rounded-md bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
                  <p className="font-medium text-foreground">可用变量</p>
                  <p>{SAFE_TEMPLATE_VARIABLES.join("、")}</p>
                </div>
                <div className="flex flex-wrap justify-between gap-2 border-t pt-3">
                  <div>
                    {editingTemplateId ? <Button type="button" variant="outline" className="gap-2 border-destructive/40 text-destructive hover:bg-destructive/5" disabled={deleteLibraryMutation.isPending} onClick={() => { if (!window.confirm("确认删除这个模板？删除后不可恢复。")) return; deleteLibraryMutation.mutate(editingTemplateId); }}>{deleteLibraryMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}删除</Button> : null}
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" onClick={resetTemplateForm}>清空</Button>
                    <Button type="button" className="gap-2" disabled={!libraryName.trim() || !libraryBody.trim() || saveLibraryMutation.isPending} onClick={() => saveLibraryMutation.mutate()}>{saveLibraryMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}{editingTemplateId ? "保存修改" : "保存模板"}</Button>
                  </div>
                </div>
              </aside>
            </CardContent>
          ) : (
            <CardContent className="grid min-h-[650px] gap-4 p-4 2xl:grid-cols-[minmax(0,1fr)_460px]">
              <section className="min-w-0 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold">发送记录</h3>
                    <p className="mt-1 text-sm text-muted-foreground">记录每次一键代发的队列、成功、失败和跳过情况。</p>
                  </div>
                  <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => queryClient.invalidateQueries({ queryKey: ["email-send-requests", selectedHuntId] })}><RefreshCw className="h-4 w-4" />刷新</Button>
                </div>
                {sendRecordsLoading ? <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />加载发送记录</div> : null}
                {!sendRecordsLoading && sendRecords.length === 0 ? <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">暂无发送记录。完成一次“确认进入队列”后会出现在这里。</div> : null}
                <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
                  {sendRecords.map((record) => {
                    const totals = sendRequestTotals(record);
                    return (
                      <button key={record.send_request_id} type="button" onClick={() => { setSelectedRecordId(record.send_request_id); setSendRequestId(record.send_request_id); }} className={`w-full rounded-md border bg-white p-4 text-left text-sm transition-colors hover:border-primary/50 hover:bg-primary/5 ${selectedRecordId === record.send_request_id ? "border-primary bg-primary/5" : ""}`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-2"><History className="h-4 w-4 text-muted-foreground" /><span className="truncate font-medium">请求 {record.send_request_id.slice(0, 8)}</span></div>
                          <Badge variant="outline">{sendStatusLabel(record.status)}</Badge>
                        </div>
                        <p className="mt-2 truncate text-xs text-muted-foreground">{record.campaign_name || "一键代发"} · {formatDateTime(record.created_at)}</p>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground md:grid-cols-4">
                          <span>SMTP 已接收 {totals.accepted}</span>
                          <span>失败 {totals.failed}</span>
                          <span>跳过 {totals.skipped}</span>
                          <span>重复统计 {totals.duplicate}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>

              <aside className="rounded-md border bg-white p-4">
                {selectedSendRecord ? (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="truncate text-base font-semibold">请求 {selectedSendRecord.send_request_id.slice(0, 8)}</h3>
                        <p className="mt-1 text-sm text-muted-foreground">{sendStatusLabel(selectedSendRecord.status)} · {formatDateTime(selectedSendRecord.created_at)}</p>
                      </div>
                      <Badge variant="outline">{selectedSendRecord.messages.length} 封</Badge>
                    </div>
                    <div className="rounded-md border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                      <p><span className="font-medium text-foreground">发件邮箱：</span>{selectedSendRecord.from_email || "-"}</p>
                      <p><span className="font-medium text-foreground">Campaign：</span>{selectedSendRecord.campaign_name || "-"}</p>
                      <p><span className="font-medium text-foreground">更新时间：</span>{formatDateTime(selectedSendRecord.updated_at)}</p>
                      {selectedSendRecord.send_limits ? <p><span className="font-medium text-foreground">额度：</span>本小时剩余 {String(selectedSendRecord.send_limits.hour_remaining ?? "-")} / 今日剩余 {String(selectedSendRecord.send_limits.day_remaining ?? "-")}</p> : null}
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-md bg-emerald-50 px-3 py-2 text-emerald-800">SMTP 已接收 {selectedRecordTotals.accepted}</div>
                      <div className="rounded-md bg-red-50 px-3 py-2 text-red-800">失败 {selectedRecordTotals.failed}</div>
                      <div className="rounded-md bg-muted/40 px-3 py-2">跳过 {selectedRecordTotals.skipped}</div>
                      <div className="rounded-md bg-muted/40 px-3 py-2">重复统计 {selectedRecordTotals.duplicate}</div>
                    </div>
                    <div className="max-h-[500px] space-y-2 overflow-y-auto pr-1">
                      {selectedSendRecord.messages.map((message) => (
                        <div key={String(message.message_id)} className="rounded-md border p-3 text-xs">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0"><p className="truncate font-medium text-foreground">{String(message.company_name || "未命名客户")}</p><p className="mt-1 truncate text-muted-foreground">{String(message.recipient_email || "-")}</p></div>
                            <Badge variant={message.status === "smtp_accepted" ? "success" : message.status === "failed" || message.status === "unknown" ? "destructive" : "outline"}>{sendStatusLabel(String(message.status || ""))}</Badge>
                          </div>
                          <p className="mt-2 truncate text-muted-foreground">{String(message.subject || "")}</p>
                          {message.last_error_type || message.failure_reason ? <p className="mt-2 text-red-700">{String(message.last_error_type || message.failure_reason)} {message.last_error_message ? `· ${String(message.last_error_message)}` : ""}</p> : null}
                          {message.rfc_message_id ? <p className="mt-2 truncate text-muted-foreground">Message-ID：{String(message.rfc_message_id)}</p> : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">请选择一条发送记录。</div>}
              </aside>
            </CardContent>
          )}
        </Card>
      </section>

      {sendStatusModalOpen && activeSendStatus ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
          <div className="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-md border bg-white shadow-xl">
            <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-lg font-semibold">发送进度</h3>
                  <Badge variant="outline">请求 {String(activeSendStatus.send_request_id || "").slice(0, 8)}</Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{sendStatusLabel(activeSendStatus.status)}。SMTP 已接收表示服务器已接受邮件，不代表客户最终已读。</p>
              </div>
              <Button type="button" variant="ghost" size="icon" onClick={() => setSendStatusModalOpen(false)} aria-label="关闭发送进度"><X className="h-4 w-4" /></Button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
              <div className="grid gap-2 text-xs md:grid-cols-4">
                <div className={`rounded-md border px-3 py-3 ${Number(sendSummary.queued || 0) ? "border-blue-200 bg-blue-50 text-blue-800" : "bg-muted/30 text-muted-foreground"}`}>排队 {sendSummary.queued || 0}</div>
                <div className={`rounded-md border px-3 py-3 ${Number(sendSummary.sending || 0) ? "border-blue-200 bg-blue-50 text-blue-800" : "bg-muted/30 text-muted-foreground"}`}>发送中 {sendSummary.sending || 0}</div>
                <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-3 text-emerald-800">SMTP 已接收 {sendSummary.smtp_accepted || 0}</div>
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-3 text-red-800">失败 {activeSendTotals.failed}</div>
              </div>

              <div className="rounded-md border bg-muted/20 p-4 text-sm">
                <div className="grid gap-3 md:grid-cols-4">
                  <div><p className="text-xs text-muted-foreground">成功发送</p><p className="mt-1 text-2xl font-semibold text-emerald-700">{activeSendTotals.accepted}</p></div>
                  <div><p className="text-xs text-muted-foreground">发送失败</p><p className="mt-1 text-2xl font-semibold text-red-700">{activeSendTotals.failed}</p></div>
                  <div><p className="text-xs text-muted-foreground">跳过客户</p><p className="mt-1 text-2xl font-semibold">{activeSendTotals.skipped}</p></div>
                  <div><p className="text-xs text-muted-foreground">重复统计</p><p className="mt-1 text-2xl font-semibold">{activeSendTotals.duplicate}</p></div>
                </div>
              </div>

              {activeSendTotals.failedMessages.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-sm font-medium">发送失败的客户</p>
                  <div className="max-h-[260px] space-y-2 overflow-y-auto rounded-md border bg-white p-2">
                    {activeSendTotals.failedMessages.map((item) => (
                      <div key={String(item.message_id)} className="rounded-md border bg-muted/20 p-3 text-xs">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0"><p className="truncate font-medium text-foreground">{String(item.company_name || "未命名客户")}</p><p className="mt-1 truncate text-muted-foreground">{String(item.recipient_email || "-")}</p></div>
                          <Badge variant="destructive">{sendStatusLabel(String(item.status || ""))}</Badge>
                        </div>
                        <p className="mt-2 text-red-700">{String(item.last_error_type || item.failure_reason || "发送失败")} {item.last_error_message ? `· ${String(item.last_error_message)}` : ""}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">当前没有失败客户。发送过程中这里会自动刷新。</div>}
            </div>

            <div className="flex justify-between gap-2 border-t px-5 py-4">
              <Button type="button" variant="outline" className="gap-2" onClick={() => { setWorkspaceTab("records"); setSelectedRecordId(String(activeSendStatus.send_request_id || "")); setSendStatusModalOpen(false); }}><History className="h-4 w-4" />查看发送记录</Button>
              <Button type="button" onClick={() => setSendStatusModalOpen(false)}>关闭</Button>
            </div>
          </div>
        </div>
      ) : null}

      {editingPreview ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
          <div className="flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-md border bg-white shadow-xl">
            <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="truncate text-lg font-semibold">{editingPreview.company_name}</h3>
                  {editedPreviewMap[editingPreview.profile_id] || editingPreview.edited ? <Badge variant="success">已修改</Badge> : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{editingPreview.recipient_email || "未填写邮箱"}{editingPreview.recipient_name ? ` · ${editingPreview.recipient_name}` : ""}{editingPreview.recipient_title ? ` · ${editingPreview.recipient_title}` : ""}</p>
              </div>
              <Button type="button" variant="ghost" size="icon" onClick={() => setEditingPreview(null)} aria-label="关闭邮件预览"><X className="h-4 w-4" /></Button>
            </div>

            <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto p-5 lg:grid-cols-[300px_minmax(0,1fr)]">
              <aside className="space-y-3 rounded-md border bg-muted/20 p-4 text-sm">
                <div><p className="text-xs text-muted-foreground">地区 / 类型</p><p className="mt-1 font-medium">{editingPreview.country_or_region || "-"} · {editingPreview.customer_type || editingPreview.target_type || "-"}</p></div>
                <div><p className="text-xs text-muted-foreground">官网 / 电话</p><p className="mt-1 break-all">{editingPreview.website || "-"}</p><p className="mt-1">{editingPreview.phone || "-"}</p></div>
                <div><p className="text-xs text-muted-foreground">企业介绍</p><p className="mt-1 leading-5 text-muted-foreground">{editingPreview.company_summary || "暂无企业介绍"}</p></div>
                <div><p className="text-xs text-muted-foreground">内部证据</p><p className="mt-1 leading-5 text-muted-foreground">{editingPreview.jps_fit_reason || editingPreview.evidence_summary || "-"}</p><p className="mt-1 text-xs text-amber-700">仅供业务员判断，不会自动写入邮件。</p></div>
                <div className="space-y-1"><p className="text-xs text-muted-foreground">变量状态</p><p className="text-xs">已用：{editingPreview.used_variables?.join("、") || "-"}</p><p className="text-xs text-amber-700">缺失：{editingPreview.missing_variables?.join("、") || "-"}</p><p className="text-xs text-destructive">无效：{editingPreview.invalid_variables?.join("、") || "-"}</p></div>
                <div className="space-y-1"><p className="text-xs text-muted-foreground">社媒</p>{[
                  ["LinkedIn", editingPreview.linkedin_url], ["Instagram", editingPreview.instagram_url], ["Facebook", editingPreview.facebook_url], ["X", editingPreview.x_url],
                ].map(([label, url]) => url ? <p key={label} className="truncate text-xs"><span className="font-medium text-foreground">{label}：</span>{url}</p> : null)}</div>
              </aside>

              <section className="flex min-h-0 flex-col gap-3">
                <div className="space-y-1.5"><label className="text-sm font-medium">邮件主题</label><Input value={editingSubject} onChange={(event) => setEditingSubject(event.target.value)} /></div>
                <div className="flex min-h-0 flex-1 flex-col space-y-1.5">
                  <label className="text-sm font-medium">邮件正文</label>
                  <RichEmailEditor
                    html={editingBodyHtml}
                    text={editingBody}
                    minHeightClass="min-h-[300px]"
                    onChange={(html, text) => { setEditingBodyHtml(html); setEditingBody(text); }}
                  />
                </div>
              </section>
            </div>

            <div className="flex justify-end gap-2 border-t px-5 py-4">
              <Button type="button" variant="outline" onClick={() => setEditingPreview(null)}>取消</Button>
              <Button type="button" className="gap-2" disabled={!editingSubject.trim() || !editingBody.trim()} onClick={savePreviewEditor}><Save className="h-4 w-4" />保存并退出</Button>
            </div>
          </div>
        </div>
      ) : null}

      {taskOptionsTask ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-lg overflow-hidden rounded-md border bg-white shadow-xl">
            <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
              <div className="min-w-0">
                <h3 className="truncate text-lg font-semibold">任务选项</h3>
                <p className="mt-1 text-sm text-muted-foreground">修改邮件模块内的备注名称，或从邮件发送页移除该任务。</p>
              </div>
              <Button type="button" variant="ghost" size="icon" onClick={() => setTaskOptionsHuntId("")} aria-label="关闭任务选项"><X className="h-4 w-4" /></Button>
            </div>
            <div className="space-y-4 p-5">
              <div className="rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
                <p className="font-medium text-foreground">原始任务</p>
                <p className="mt-1">{taskOptionsTask.target_regions.join("、") || taskOptionsTask.hunt_id.slice(0, 8)} · {taskOptionsTask.product_keywords.join("、") || taskOptionsTask.target_customer_profile || "未标注产品"}</p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">显示名称</label>
                <Input value={taskDisplayNameInput} onChange={(event) => setTaskDisplayNameInput(event.target.value)} placeholder="例如：泰国牙科学校 7月开发信" />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">备注</label>
                <textarea className="h-28 w-full resize-none rounded-md border px-3 py-2 text-sm leading-6" value={taskNoteInput} onChange={(event) => setTaskNoteInput(event.target.value)} placeholder="给业务员看的任务说明，可留空" />
              </div>
            </div>
            <div className="flex flex-wrap justify-between gap-2 border-t px-5 py-4">
              <Button
                type="button"
                variant="outline"
                className="gap-2 border-destructive/40 text-destructive hover:bg-destructive/5"
                disabled={hideTaskMutation.isPending}
                onClick={() => {
                  if (!window.confirm("确认从邮件发送模块移除此任务？原始搜索任务和客户信息不会被删除。")) return;
                  hideTaskMutation.mutate(taskOptionsTask.hunt_id);
                  setTaskOptionsHuntId("");
                }}
              >
                {hideTaskMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}删除
              </Button>
              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={() => setTaskOptionsHuntId("")}>取消</Button>
                <Button
                  type="button"
                  className="gap-2"
                  disabled={taskPreferencesMutation.isPending}
                  onClick={() => taskPreferencesMutation.mutate({ huntId: taskOptionsTask.hunt_id, displayName: taskDisplayNameInput, note: taskNoteInput })}
                >
                  {taskPreferencesMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}保存
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <section className="flex items-center gap-3 rounded-md border border-dashed bg-white px-4 py-3 text-sm text-muted-foreground"><AlertTriangle className="h-4 w-4 shrink-0" /><span>一键代发会进入后端发送队列，仍受 SMTP 测试、限速和回复检测规则保护；同一客户是否重复发送由业务员确认。</span></section>
    </div>
  );
}
