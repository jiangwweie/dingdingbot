import { useEffect, useState } from 'react';
import { PlayCircle, RefreshCw, ShieldAlert } from 'lucide-react';
import { brcApi, OperationCapability, ReadinessResponse } from '@/src/services/api';
import { Badge } from '@/src/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import {
  CapabilityBadge,
  DeveloperDetails,
  EmptyState,
  ErrorState,
  OwnerSummary,
  StageStrip,
  StatusBadge,
} from './ConsolePrimitives';
import { actionDisabledReason, isActionEnabled } from './readiness';
import { OperationPreflightModal, OperationPreflightState } from './CommandCenter';

const FIXED_REHEARSAL_TEXT = '准备下一轮 testnet rehearsal';

export default function FixedTestnetRehearsal() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [operationCapability, setOperationCapability] = useState<OperationCapability | null>(null);
  const [operationModal, setOperationModal] = useState<OperationPreflightState | null>(null);
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const ready = await brcApi.readiness();
      const capabilityPayload = await brcApi.operationCapabilities();
      setReadiness(ready);
      setOperationCapability(
        capabilityPayload.capabilities.find((item) => item.operation_type === 'run_fixed_testnet_rehearsal') || null,
      );
      if (isActionEnabled(ready, 'create_workflow')) {
        const list = await brcApi.listWorkflows();
        setItems(list.workflows);
      } else {
        setItems([]);
      }
    } catch (err) {
      setError(err);
    }
  }

  async function openOperationPreflight() {
    if (!operationCapability?.executable_through_operation) return;
    setOperationModal({ loading: true, phrase: '', error: null, preflight: null, result: null });
    setError(null);
    try {
      const preflight = await brcApi.preflightOperation({
        operation_type: 'run_fixed_testnet_rehearsal',
        input_params: {
          source: 'fixed_testnet_rehearsal_page',
          fixed_request_text: FIXED_REHEARSAL_TEXT,
        },
        source: { kind: 'fixed_testnet_rehearsal_page' },
      });
      setOperationModal({ loading: false, phrase: '', error: null, preflight, result: null });
    } catch (err) {
      setOperationModal({ loading: false, phrase: '', error: String((err as { message?: unknown }).message || err), preflight: null, result: null });
    }
  }

  if (!readiness && !error) return <div className="text-xs text-zinc-500">Loading fixed testnet rehearsal...</div>;
  if (!readiness && error) return <ErrorState error={error} />;

  const canRunTestnet = isActionEnabled(readiness, 'run_controlled_testnet_workflow');
  const testnetDisabledReason = actionDisabledReason(readiness, 'run_controlled_testnet_workflow');
  const operationExecutable = Boolean(operationCapability?.executable_through_operation);
  const loading = operationModal?.loading === true;

  return (
    <div className="space-y-4">
      <StageStrip
        current="Fixed Testnet Rehearsal"
        next="Use Operation Preflight when readiness allows the controlled fixed testnet path."
        global="Runs the fixed BRC ETH/BTC testnet rehearsal through Operation authorization. Any workflow run id is only a technical reference."
      />
      <OwnerSummary
        conclusion={operationExecutable ? 'Fixed testnet rehearsal is Operation-backed' : 'Fixed testnet rehearsal Operation is not available now'}
        why={canRunTestnet ? readiness?.current_conclusion || 'Readiness allows the controlled testnet workflow.' : testnetDisabledReason}
        canDo={operationExecutable ? 'Open Operation Preflight and confirm through the Operation Layer.' : 'Inspect the unavailable Operation capability and technical carrier state without treating it as authorization.'}
        cannotDo="Cannot run arbitrary symbols, arbitrary order parameters, generic LLM trades, real live, withdrawal, transfer, or strategy-pool execution."
        accountImpact="Only the fixed Binance testnet rehearsal may be affected after confirmation. Real accounts remain out of scope."
        next={operationExecutable ? 'Use Operation Preflight.' : 'Do not run the technical carrier as the authorization source.'}
        tone={operationExecutable ? 'success' : 'warning'}
      />
      {error && <ErrorState error={error} />}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2">
              Operation Authorization
              <CapabilityBadge status={operationExecutable ? 'Operation Preflight available' : 'Unavailable'} />
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <div className="rounded-sm border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-950">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Fixed request text</p>
              <p className="mt-1 font-mono">{FIXED_REHEARSAL_TEXT}</p>
            </div>
            <p>
              Operation Layer is the authorization source. The legacy workflow carrier is shown only as implementation history
              and must not be used as a standalone authorization path.
            </p>
            {operationCapability?.current_reason && (
              <p className="rounded-sm border border-zinc-200 bg-zinc-50 p-2 text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
                {operationCapability.current_reason}
              </p>
            )}
            <button
              type="button"
              onClick={openOperationPreflight}
              disabled={loading || !operationExecutable}
              title={operationExecutable ? 'Open Operation Preflight' : operationCapability?.current_reason || 'Operation capability unavailable'}
              className="inline-flex min-h-10 items-center gap-2 rounded-sm border border-emerald-600 bg-emerald-600 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              <PlayCircle className="h-3.5 w-3.5" />
              Operation Preflight
            </button>
            {!operationExecutable && (
              <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-2 text-amber-700 dark:text-amber-300">
                Operation unavailable: {operationCapability?.current_reason || 'Capability not returned by backend.'}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
              Technical Carrier Boundary
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <Metric label="Authorization" value="Operation Layer" />
              <Metric label="Carrier role" value="Internal ref only" />
              <Metric label="Readiness" value={<StatusBadge state={canRunTestnet ? 'allowed' : 'blocked'} />} />
              <Metric label="Live ready" value={<StatusBadge state="false" />} />
            </div>
            {!canRunTestnet && (
              <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-2 text-amber-700 dark:text-amber-300">
                Testnet rehearsal unavailable: {testnetDisabledReason}
              </p>
            )}
            <EmptyState
              title="No direct workflow confirmation"
              body="Operation confirm is the only Owner Console authorization entry. workflow_run_id appears only after a confirmed Operation result."
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-3.5 w-3.5 text-blue-500" />
            Recent Fixed Workflow Runs
          </CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <EmptyState title="No workflow runs" body="Recent workflow carrier runs will appear here." />
          ) : (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {items.slice(0, 8).map((item) => (
                <div key={String(item.workflow_run_id)} className="rounded-sm border border-zinc-200 p-3 text-xs leading-5 dark:border-zinc-800">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-zinc-800 dark:text-zinc-200">{String(item.workflow_run_id)}</span>
                    <StatusBadge state={item.status} />
                  </div>
                  <p className="mt-1 text-zinc-500">{String(item.action || 'unknown')}</p>
                  <Badge variant={item.mutation_executed ? 'warning' : 'outline'}>
                    {item.mutation_executed ? 'testnet mutation recorded' : 'no mutation'}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <DeveloperDetails data={{ readiness, recent_workflows: items, operation_capability: operationCapability }} />
      <OperationPreflightModal
        state={operationModal}
        onClose={() => setOperationModal(null)}
        onStateChange={setOperationModal}
        onRefresh={load}
      />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-2 dark:border-zinc-800">
      <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}
