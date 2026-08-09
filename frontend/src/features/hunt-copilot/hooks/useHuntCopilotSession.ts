import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { huntCopilotApi } from "../api";
import { fieldLabels } from "../constants";
import { HuntCopilotMessage, HuntCopilotSession, HuntCopilotStrategy } from "../types";

export function useHuntCopilotSession({ onExecuted }: { onExecuted: (jobId: string) => void }) {
  const queryClient = useQueryClient();
  const [input, setInput] = useState("");
  const [session, setSession] = useState<HuntCopilotSession | null>(null);
  const historyQuery = useQuery({
    queryKey: ["hunt-copilot-sessions"],
    queryFn: huntCopilotApi.listSessions,
  });

  const startMutation = useMutation({
    mutationFn: huntCopilotApi.start,
    onSuccess: (data) => {
      setSession(data.session);
      void queryClient.invalidateQueries({ queryKey: ["hunt-copilot-sessions"] });
    },
  });
  const sendMutation = useMutation({
    mutationFn: ({ sessionId, message }: { sessionId: string; message: string }) => huntCopilotApi.sendMessage(sessionId, message),
    onSuccess: (data) => {
      setSession(data.session);
      void queryClient.invalidateQueries({ queryKey: ["hunt-copilot-sessions"] });
    },
  });
  const updateStrategyMutation = useMutation({
    mutationFn: ({ sessionId, strategy }: { sessionId: string; strategy: HuntCopilotStrategy }) => huntCopilotApi.updateStrategy(sessionId, strategy),
    onSuccess: (data) => {
      setSession(data.session);
      void queryClient.invalidateQueries({ queryKey: ["hunt-copilot-sessions"] });
    },
  });
  const confirmStrategyMutation = useMutation({
    mutationFn: huntCopilotApi.confirmStrategy,
    onSuccess: (data) => {
      setSession(data.session);
      void queryClient.invalidateQueries({ queryKey: ["hunt-copilot-sessions"] });
    },
  });
  const checkChannelsMutation = useMutation({
    mutationFn: huntCopilotApi.checkChannels,
    onSuccess: (data) => {
      setSession(data.session);
      void queryClient.invalidateQueries({ queryKey: ["hunt-copilot-sessions"] });
    },
  });
  const executeMutation = useMutation({
    mutationFn: huntCopilotApi.execute,
    onSuccess: (data) => {
      setSession(data.session);
      void queryClient.invalidateQueries({ queryKey: ["hunt-copilot-sessions"] });
      onExecuted(data.job.job_id);
    },
  });
  const loadSessionMutation = useMutation({
    mutationFn: huntCopilotApi.getSession,
    onSuccess: (data) => setSession(data.session),
  });
  const duplicateSessionMutation = useMutation({
    mutationFn: huntCopilotApi.duplicateSession,
    onSuccess: (data) => {
      setSession(data.session);
      void queryClient.invalidateQueries({ queryKey: ["hunt-copilot-sessions"] });
    },
  });

  const busy = startMutation.isPending || sendMutation.isPending || updateStrategyMutation.isPending || confirmStrategyMutation.isPending || checkChannelsMutation.isPending || executeMutation.isPending || loadSessionMutation.isPending || duplicateSessionMutation.isPending;
  const strategy = session?.strategy;
  const allowedActions = session?.allowed_actions ?? [];
  const requiredLabels = useMemo(() => {
    if (!strategy) return [];
    return fieldLabels.filter(([key]) => strategy.hard_filters[key]).map(([, label]) => label);
  }, [strategy]);
  const error = startMutation.error || sendMutation.error || updateStrategyMutation.error || confirmStrategyMutation.error || checkChannelsMutation.error || executeMutation.error;

  const submitMessage = () => {
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    if (!session) {
      startMutation.mutate(message);
      return;
    }
    appendOptimisticUserMessage(message);
    sendMutation.mutate({ sessionId: session.session_id, message });
  };

  const submitSuggestedReply = (message: string) => {
    const clean = message.trim();
    if (!clean || busy) return;
    setInput("");
    if (!session) {
      startMutation.mutate(clean);
      return;
    }
    appendOptimisticUserMessage(clean);
    sendMutation.mutate({ sessionId: session.session_id, message: clean });
  };

  const appendOptimisticUserMessage = (message: string) => {
    const optimistic: HuntCopilotMessage = {
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };
    setSession((current) => (current ? { ...current, messages: [...current.messages, optimistic] } : current));
  };

  const updateStrategy = (patch: Partial<HuntCopilotStrategy>) => {
    if (!session || !strategy) return;
    updateStrategyMutation.mutate({ sessionId: session.session_id, strategy: { ...strategy, ...patch } });
  };

  const toggleRequiredField = (key: keyof HuntCopilotStrategy["hard_filters"]) => {
    if (!strategy) return;
    updateStrategy({ hard_filters: { ...strategy.hard_filters, [key]: !strategy.hard_filters[key] } });
  };

  const updateBudget = (key: keyof HuntCopilotStrategy["budget"], value: number) => {
    if (!strategy) return;
    const nextBudget = normalizeBudgetPatch(strategy.budget, key, value);
    updateStrategy({ budget: nextBudget });
  };

  return {
    input,
    setInput,
    session,
    history: historyQuery.data?.sessions ?? [],
    historyLoading: historyQuery.isLoading,
    strategy,
    busy,
    error,
    requiredLabels,
    canConfirmStrategy: allowedActions.includes("confirm_strategy"),
    canCheck: allowedActions.includes("check_channels"),
    canExecute: allowedActions.includes("confirm_execution"),
    isConfirmingStrategy: confirmStrategyMutation.isPending,
    isCheckingChannels: checkChannelsMutation.isPending,
    isExecuting: executeMutation.isPending,
    submitMessage,
    submitSuggestedReply,
    toggleRequiredField,
    updateBudget,
    confirmStrategy: () => session && confirmStrategyMutation.mutate(session.session_id),
    checkChannels: () => session && checkChannelsMutation.mutate(session.session_id),
    execute: () => session && executeMutation.mutate({
      sessionId: session.session_id,
      strategyVersion: session.strategy_version,
      strategyHash: session.strategy_hash,
    }),
    loadSession: (sessionId: string) => loadSessionMutation.mutate(sessionId),
    duplicateSession: (sessionId: string) => duplicateSessionMutation.mutate(sessionId),
  };
}

function normalizeBudgetPatch(
  budget: HuntCopilotStrategy["budget"],
  key: keyof HuntCopilotStrategy["budget"],
  value: number,
): HuntCopilotStrategy["budget"] {
  const next = { ...budget, [key]: value };
  next.preview_total_usd = Math.max(0, Number(next.preview_total_usd || 0));
  next.total_usd = Math.max(0.01, Number(next.total_usd || 0.01));
  next.apify_actor_max_items = Math.max(1, Math.round(Number(next.apify_actor_max_items || 1)));
  next.apify_actor_max_total_charge_usd = Math.max(0.01, Number(next.apify_actor_max_total_charge_usd || 0.01));
  next.apify_task_max_total_charge_usd = Math.max(0.01, Number(next.apify_task_max_total_charge_usd || 0.01));
  next.max_candidates = Math.max(1, Math.round(Number(next.max_candidates || 1)));
  next.final_leads = Math.max(1, Math.round(Number(next.final_leads || 1)));

  if (key === "final_leads" && next.final_leads > next.max_candidates) {
    next.max_candidates = Math.min(1000, Math.max(next.final_leads, next.final_leads * 4));
  }
  if (key === "max_candidates" && next.max_candidates < next.final_leads) {
    next.final_leads = next.max_candidates;
  }
  if (key === "preview_total_usd" && next.preview_total_usd > next.total_usd) {
    next.total_usd = next.preview_total_usd || 0.01;
  }
  if (key === "total_usd" && next.preview_total_usd > next.total_usd) {
    next.preview_total_usd = next.total_usd;
  }
  if (next.apify_task_max_total_charge_usd > next.total_usd) {
    next.apify_task_max_total_charge_usd = next.total_usd;
  }
  return next;
}
