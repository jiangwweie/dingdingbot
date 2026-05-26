const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export type ApiError = {
  status: number;
  message: string;
  payload?: unknown;
};

export type SessionResponse = {
  authenticated: boolean;
  username?: string | null;
  expires_at_ms?: number | null;
  current_stage: string;
  next_recommended_step: string;
  global_planning_stage: string;
  live_ready: false;
};

export type DashboardResponse = {
  current_stage: string;
  next_recommended_step: string;
  global_planning_stage: string;
  terminology: Record<string, string>;
  owner_questions: string[];
  live_ready: false;
};

export type RuntimeSafetyResponse = {
  runtime_bound: boolean;
  profile?: string | null;
  testnet?: boolean | null;
  gks_active?: boolean | null;
  startup_guard_armed?: boolean | null;
  flatness_known: boolean;
  current_stage: string;
  next_recommended_step: string;
  global_planning_stage: string;
  human_summary: string;
  live_ready: false;
};

export type OperatorPlanResponse = {
  plan: Record<string, unknown>;
  action: Record<string, unknown>;
  live_ready: false;
  access_boundary: string;
};

export type OperatorRunResponse = {
  run: Record<string, unknown>;
  action?: Record<string, unknown> | null;
  inventory: Record<string, unknown>;
  live_ready: false;
  access_boundary: string;
};

export type WorkflowResponse = {
  workflow: Record<string, unknown>;
  intent?: Record<string, unknown> | null;
  live_ready: false;
  access_boundary: string;
};

export type ReviewDecisionResponse = {
  review_decision: Record<string, unknown>;
  live_ready: false;
  access_boundary?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers || {}),
    },
  });

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === 'object' && payload && 'message' in payload
      ? String((payload as { message?: unknown }).message)
      : typeof payload === 'object' && payload && 'detail' in payload
        ? String((payload as { detail?: unknown }).detail)
        : `API request failed: ${response.status}`;
    throw { status: response.status, message: detail, payload } satisfies ApiError;
  }
  return payload as T;
}

export const brcApi = {
  login(username: string, password: string, totpCode: string) {
    return request<SessionResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, totp_code: totpCode }),
    });
  },
  logout() {
    return request<SessionResponse>('/api/auth/logout', { method: 'POST' });
  },
  session() {
    return request<SessionResponse>('/api/auth/session');
  },
  dashboard() {
    return request<DashboardResponse>('/api/brc/dashboard');
  },
  runtimeSafety() {
    return request<RuntimeSafetyResponse>('/api/runtime/safety');
  },
  reviewPacket() {
    return request<Record<string, unknown>>('/api/brc/review-packet');
  },
  nextEligibility() {
    return request<Record<string, unknown>>('/api/brc/next-eligibility');
  },
  evidence() {
    return request<Record<string, unknown>>('/api/brc/evidence');
  },
  planOperator(text: string) {
    return request<OperatorPlanResponse>('/api/brc/operator/plan', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  },
  runOperatorAction(actionId: string, confirmationPhrase: string) {
    return request<OperatorRunResponse>(`/api/brc/operator/actions/${encodeURIComponent(actionId)}/run`, {
      method: 'POST',
      body: JSON.stringify({ confirmation_phrase: confirmationPhrase, confirmed_by: 'owner' }),
    });
  },
  listActions(limit = 20) {
    return request<{ actions: Array<Record<string, unknown>>; live_ready: false }>(`/api/brc/operator/actions?limit=${limit}`);
  },
  createWorkflow(text: string) {
    return request<WorkflowResponse>('/api/brc/llm/workflows', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  },
  confirmWorkflow(workflowRunId: string, confirmationPhrase: string) {
    return request<WorkflowResponse>(`/api/brc/llm/workflows/${encodeURIComponent(workflowRunId)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ confirmation_phrase: confirmationPhrase, confirmed_by: 'owner' }),
    });
  },
  listWorkflows(limit = 20) {
    return request<{ workflows: Array<Record<string, unknown>>; live_ready: false }>(`/api/brc/llm/workflows?limit=${limit}`);
  },
  listReviewDecisions(limit = 20) {
    return request<{ review_decisions: Array<Record<string, unknown>>; live_ready: false }>(`/api/brc/review-decisions?limit=${limit}`);
  },
  createReviewDecision(input: {
    campaign_id: string;
    source_action_id?: string;
    decision: string;
    reason_text: string;
    next_recommended_task: string;
  }) {
    return request<ReviewDecisionResponse>('/api/brc/review-decisions', {
      method: 'POST',
      body: JSON.stringify({ ...input, created_by: 'owner', metadata: { source: 'brc_operator_console' } }),
    });
  },
};
