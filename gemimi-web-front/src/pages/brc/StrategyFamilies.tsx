import { useEffect, useMemo, useState } from 'react';
import { GitBranch, ShieldCheck } from 'lucide-react';
import {
  AdmissionDecision,
  AdmissionTrialBinding,
  brcApi,
  Mi001SolReadinessResponse,
  StrategyFamily,
} from '@/src/services/api';
import { Badge } from '@/src/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';

type LoadState = {
  families: StrategyFamily[];
  decisions: AdmissionDecision[];
  bindings: AdmissionTrialBinding[];
  currentCampaign: Record<string, unknown> | null;
  mi001: Mi001SolReadinessResponse | null;
  gaps: string[];
};

type CandidateRow = {
  id: string;
  name: string;
  status: string;
  symbol: string;
  side: string;
  evidenceSummary: string;
  ownerAcceptance: string;
  pgRefs: string[];
  admissionRef: string;
  bindingRef: string;
  campaignRef: string;
  readiness: string;
  terminalBlocker: string;
  executionBoundary: string;
  raw: Record<string, unknown>;
};

export default function StrategyFamilies() {
  const [state, setState] = useState<LoadState | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const gaps: string[] = [];
      const [families, decisions, bindings, currentCampaign, mi001] = await Promise.all([
        brcApi.listStrategyFamilies().catch(() => {
          gaps.push('strategy families API not reported');
          return [] as StrategyFamily[];
        }),
        brcApi.listAdmissionDecisions().catch(() => {
          gaps.push('admission decisions API not reported');
          return [] as AdmissionDecision[];
        }),
        brcApi.listTrialBindings().catch(() => {
          gaps.push('trial bindings API not reported');
          return [] as AdmissionTrialBinding[];
        }),
        brcApi.currentCampaign().then((payload) => payload.campaign || null).catch(() => {
          gaps.push('current campaign API not reported');
          return null;
        }),
        brcApi.mi001SolReadiness().catch(() => {
          gaps.push('MI-001 readiness API not reported');
          return null;
        }),
      ]);
      if (!cancelled) {
        setState({ families, decisions, bindings, currentCampaign, mi001, gaps });
      }
    }
    load().catch(setError);
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo(() => buildRows(state), [state]);

  if (error) return <ErrorState error={error} />;
  if (!state) return <div className="text-xs text-zinc-500">Loading strategy-family facts...</div>;

  return (
    <div className="space-y-4">
      <StageStrip
        current="Strategy Families"
        next="Review candidate readiness, evidence summaries, and PG registration references without opening execution authority."
        global="Read-only / no execution. Strategy-family status is not order permission."
      />
      <OwnerSummary
        conclusion={rows.length ? `当前可读 ${rows.length} 条候选状态；Strategy Families 是候选状态工作台，不是交易入口。` : '当前没有 strategy-family 候选行；页面保持只读空态，不发明候选。'}
        why={state.gaps.length ? state.gaps.join('; ') : '只读 strategy/admission APIs 已返回。'}
        canDo="查看 families、candidates、admission decisions、trial bindings、Owner acceptance 和 campaign refs。"
        cannotDo="不能启动 trial、下单、创建 execution intent、启用 live trading 或修改 execution permission。"
        accountImpact="Read-only display only. No exchange write, order, transfer, withdrawal, or runtime start is called."
        next="继续在 Command Center 和 Review/Evidence 中核对 MI-001 SOL blocker 与 evidence chain。"
        tone={rows.length ? 'info' : 'warning'}
      />

      <Card>
        <CardHeader>
          <CardTitle>Candidate Status Table</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-zinc-200 text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:border-zinc-800">
                    <th className="py-2 pr-3">Candidate</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3">Owner acceptance</th>
                    <th className="py-2 pr-3">PG registration</th>
                    <th className="py-2 pr-3">Readiness</th>
                    <th className="py-2 pr-3">Terminal blocker</th>
                    <th className="py-2 pr-3">Execution boundary</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b border-zinc-100 align-top last:border-0 dark:border-zinc-800">
                      <td className="py-3 pr-3 font-semibold text-zinc-900 dark:text-zinc-100">
                        {row.name}
                        <div className="mt-1 text-[11px] font-normal text-zinc-500">{row.symbol} / {row.side}</div>
                      </td>
                      <td className="py-3 pr-3">{row.status}</td>
                      <td className="py-3 pr-3">{row.ownerAcceptance}</td>
                      <td className="py-3 pr-3">{row.pgRefs.join(', ') || 'not reported yet'}</td>
                      <td className="py-3 pr-3">{row.readiness}</td>
                      <td className="py-3 pr-3">
                        <Badge variant="outline">{row.terminalBlocker}</Badge>
                      </td>
                      <td className="py-3 pr-3">{row.executionBoundary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-sm border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700">
              Empty state: no strategy families or MI-001 fallback data were reported. Candidate table remains read-only and no execution action is exposed.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5 text-blue-500" />
            Families / Candidates
          </CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length ? (
            <div className="space-y-3">
              {rows.map((row) => (
                <div key={row.id} className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">{row.name}</p>
                      <p className="text-xs text-zinc-500">{row.id} / {row.symbol} / {row.side}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <StatusBadge state={row.status} />
                      <Badge variant="outline">read-only</Badge>
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-3">
                    <Fact label="Evidence summary" value={row.evidenceSummary} />
                    <Fact label="Owner acceptance" value={row.ownerAcceptance} />
                    <Fact label="PG registration refs" value={row.pgRefs.join(', ') || 'not reported yet'} />
                    <Fact label="Latest admission" value={row.admissionRef} />
                    <Fact label="Latest binding" value={row.bindingRef} />
                    <Fact label="Campaign" value={row.campaignRef} />
                  </div>
                  <p className="mt-3 rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-2 text-xs leading-5 text-amber-800 dark:text-amber-200">
                    strategy_active、signal_generated 或 trial_trade_intent evidence 不等于可交易授权，也不会创建 execution intent 或 order。
                  </p>
                  <JsonDetails data={row.raw} label="Candidate source JSON" />
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-sm border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700">
              Empty state: no strategy families or MI-001 fallback data were reported. The page remains read-only and does not invent candidates.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
            Boundary
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs leading-5 text-zinc-700 dark:text-zinc-300">
          <p>Read-only / no execution。候选可见性不会创建 execution intent、order、live permission、leverage change、transfer、withdrawal 或 runtime start。</p>
          {state.gaps.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-amber-700 dark:text-amber-300">
              {state.gaps.map((gap) => <li key={gap}>{gap}</li>)}
            </ul>
          )}
        </CardContent>
      </Card>

      <DeveloperDetails data={state} />
    </div>
  );
}

function buildRows(state: LoadState | null): CandidateRow[] {
  if (!state) return [];
  const latestDecision = state.decisions[0];
  const latestBinding = state.bindings[0];
  const familyRows = state.families.map((family) => ({
    id: family.family_key || family.strategy_family_id,
    name: family.name || family.family_key,
    status: candidateStatusText(state.mi001, family.status || 'unknown'),
    symbol: state.mi001?.candidate.symbol || 'not reported yet',
    side: state.mi001?.candidate.side || 'not reported yet',
    evidenceSummary: evidenceSummary(state.mi001),
    ownerAcceptance: ownerAcceptanceText(latestDecision?.owner_risk_acceptance_id || state.mi001?.source_refs.find((ref) => ref.includes('owner')) || ''),
    pgRefs: state.mi001?.source_refs || [],
    admissionRef: latestDecision?.admission_decision_id || 'not reported yet',
    bindingRef: latestBinding?.binding_id || 'not reported yet',
    campaignRef: latestBinding?.campaign_id || stringAt(state.currentCampaign, 'campaign_id', 'not reported yet'),
    readiness: readinessText(state.mi001),
    terminalBlocker: terminalBlockerText(state.mi001),
    executionBoundary: executionBoundaryText(),
    raw: { family, latestDecision, latestBinding, mi001: state.mi001 },
  }));
  if (familyRows.length > 0) return familyRows;
  if (!state.mi001) return [];
  return [{
    id: state.mi001.candidate.candidate_id,
    name: `${state.mi001.candidate.id} ${state.mi001.candidate.strategy_family}`,
    status: candidateStatusText(state.mi001, state.mi001.candidate.status),
    symbol: state.mi001.candidate.symbol,
    side: state.mi001.candidate.side,
    evidenceSummary: evidenceSummary(state.mi001),
    ownerAcceptance: ownerAcceptanceText(state.mi001.source_refs.find((ref) => ref.includes('owner')) || ''),
    pgRefs: state.mi001.source_refs,
    admissionRef: latestDecision?.admission_decision_id || 'MI-001-SOL-LONG-admission-request-v1',
    bindingRef: latestBinding?.binding_id || 'not reported yet',
    campaignRef: latestBinding?.campaign_id || stringAt(state.currentCampaign, 'campaign_id', 'not reported yet'),
    readiness: readinessText(state.mi001),
    terminalBlocker: terminalBlockerText(state.mi001),
    executionBoundary: executionBoundaryText(),
    raw: { latestDecision, latestBinding, mi001: state.mi001 },
  }];
}

function evidenceSummary(mi001: Mi001SolReadinessResponse | null) {
  if (!mi001) return 'not reported yet';
  return `${mi001.evidence.signal_count} signals; 72h mean ${mi001.evidence.mean_72h}; 7d mean ${mi001.evidence.mean_7d}`;
}

function stringAt(source: Record<string, unknown> | null, key: string, fallback: string) {
  const value = source?.[key];
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function ownerAcceptanceText(ref: string) {
  return ref ? 'ready' : 'not reported yet';
}

function readinessText(mi001: Mi001SolReadinessResponse | null) {
  if (!mi001) return 'not reported yet';
  if (mi001.readiness.verdict === 'blocked_startup_guard_runtime_coupled') {
    return 'final review complete, blocked by startup guard';
  }
  return mi001.readiness.verdict || 'not reported yet';
}

function terminalBlockerText(mi001: Mi001SolReadinessResponse | null) {
  return mi001?.readiness.verdict || mi001?.terminal_state || 'not reported yet';
}

function executionBoundaryText() {
  return 'live read-only / intent recording / no order';
}

function candidateStatusText(mi001: Mi001SolReadinessResponse | null, fallback: string) {
  if (!mi001) return fallback || 'not reported yet';
  if (mi001.candidate.id === 'MI-001') return 'pre-start / accepted / registered';
  return mi001.candidate.status || fallback || 'not reported yet';
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <p className="mt-1 break-words text-xs font-medium text-zinc-800 dark:text-zinc-200">{value}</p>
    </div>
  );
}
