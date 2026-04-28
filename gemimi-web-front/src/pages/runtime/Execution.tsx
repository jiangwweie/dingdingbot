import React, { useEffect, useState, useMemo } from 'react';
import { getRuntimeExecutionIntents, getRuntimeOrders } from '@/src/services/api';
import { ExecutionIntent, Order } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Loader2, AlertCircle, Link2 } from 'lucide-react';
import { DASH, fmtDash, fmtDateTime, fmtDec } from '@/src/lib/console-utils';
import {
  intentStatusLabel,
  orderStatusLabel,
  directionLabel,
  truncateId,
} from '@/src/lib/runtime-format';
import {
  useTableSort,
  compareTimestamp,
  comparePrimitive,
  FilterSelect,
  EmptyFilterRow,
  emptyDataCard,
} from '@/src/lib/table-utils';

// ── Intent status → Badge variant ─────────────────────────────
const intentStatusVariant = (
  s: string,
): 'success' | 'warning' | 'danger' | 'info' | 'default' => {
  switch (s.toLowerCase()) {
    case 'filled':
    case 'completed':
      return 'success';
    case 'rejected':
    case 'failed':
    case 'blocked':
      return 'danger';
    case 'pending':
      return 'warning';
    case 'submitted':
    case 'executing':
    case 'open':
    case 'protecting':
    case 'partially_protected':
    case 'partially_filled':
      return 'info';
    case 'cancelled':
    case 'canceled':
      return 'default';
    default:
      return 'default';
  }
};

// ── Order status → Badge variant ──────────────────────────────
const orderStatusVariant = (
  s: string,
): 'success' | 'warning' | 'danger' | 'info' | 'default' => {
  switch (s.toUpperCase()) {
    case 'FILLED':
      return 'success';
    case 'REJECTED':
    case 'FAILED':
      return 'danger';
    case 'PENDING':
    case 'SUBMITTED':
    case 'OPEN':
    case 'NEW':
    case 'PARTIALLY_FILLED':
      return 'info';
    case 'CANCELED':
    case 'CANCELLED':
    case 'EXPIRED':
      return 'default';
    default:
      return 'default';
  }
};

// ── Order role → Badge variant ────────────────────────────────
const orderRoleVariant = (
  role: string,
): 'success' | 'warning' | 'danger' | 'info' | 'default' => {
  switch (role) {
    case 'ENTRY':
      return 'info';
    case 'TP':
      return 'success';
    case 'SL':
      return 'danger';
    default:
      return 'default';
  }
};

// ── Intent filter options (Chinese labels) ────────────────────
const INTENT_STATUS_OPTIONS = [
  { value: 'ALL', label: '全部状态' },
  { value: 'PENDING', label: '等待中' },
  { value: 'SUBMITTED', label: '已提交' },
  { value: 'EXECUTING', label: '执行中' },
  { value: 'PARTIALLY_PROTECTED', label: '部分保护' },
  { value: 'COMPLETED', label: '已完成' },
  { value: 'BLOCKED', label: '已阻断' },
  { value: 'FAILED', label: '失败' },
  { value: 'CANCELLED', label: '已撤销' },
  { value: 'CANCELED', label: '已撤销' },
];

// ── Order type display ────────────────────────────────────────
function orderTypeLabel(type: string | undefined, price: number | null): string {
  if (!type) return DASH;
  if (type === 'MARKET' && price === null) return '市价 (MARKET)';
  return type;
}

// ── Price display for orders ──────────────────────────────────
function orderPriceDisplay(price: number | null, type: string | undefined): string {
  if (price !== null && price !== undefined) return fmtDec(price);
  if (type === 'MARKET') return '市价';
  return DASH;
}

// ── Order role display ────────────────────────────────────────
function orderRoleDisplay(order: Order): string {
  if (order.raw_role && order.raw_role !== order.role) return order.raw_role;
  return order.role;
}

// ── Row highlight for rejected/failed intents ─────────────────
function intentRowClass(intent: ExecutionIntent): string {
  const status = intent.status.toLowerCase();
  if (status === 'rejected' || status === 'failed' || status === 'blocked') {
    return 'bg-rose-500/5';
  }
  return '';
}

// ── Row highlight for rejected orders ─────────────────
function orderRowClass(order: Order): string {
  if (order.status === 'REJECTED') {
    return 'bg-rose-500/5';
  }
  return '';
}

export default function Execution() {
  const { refreshCount } = useRefreshContext();
  const [intents, setIntents] = useState<ExecutionIntent[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [intentStatusFilter, setIntentStatusFilter] = useState('ALL');

  const intentSort = useTableSort<ExecutionIntent>('created_at', 'desc');
  const orderSort = useTableSort<Order>('updated_at', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);

    Promise.all([getRuntimeExecutionIntents(), getRuntimeOrders()])
      .then(([intentRes, orderRes]) => {
        if (active) {
          setIntents(intentRes);
          setOrders(orderRes);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [refreshCount]);

  // ── Filtered + sorted intents ─────────────────────────────
  const filteredIntents = useMemo(() => {
    let rows = intents;
    if (intentStatusFilter !== 'ALL') {
      rows = rows.filter((e) => e.status?.toUpperCase() === intentStatusFilter);
    }
    return [...rows].sort((a, b) => {
      switch (intentSort.sortField) {
        case 'created_at':
          return compareTimestamp(a.created_at, b.created_at, intentSort.sortOrder);
        case 'symbol':
          return comparePrimitive(a.symbol, b.symbol, intentSort.sortOrder);
        case 'direction':
          return comparePrimitive(a.direction, b.direction, intentSort.sortOrder);
        case 'status':
          return comparePrimitive(a.status, b.status, intentSort.sortOrder);
        default:
          return 0;
      }
    });
  }, [intents, intentStatusFilter, intentSort.sortField, intentSort.sortOrder]);

  // ── Sorted orders ─────────────────────────────────────────
  const sortedOrders = useMemo(() => {
    return [...orders].sort((a, b) => {
      switch (orderSort.sortField) {
        case 'updated_at':
          return compareTimestamp(a.updated_at, b.updated_at, orderSort.sortOrder);
        case 'symbol':
          return comparePrimitive(a.symbol, b.symbol, orderSort.sortOrder);
        case 'status':
          return comparePrimitive(a.status, b.status, orderSort.sortOrder);
        case 'role':
          return comparePrimitive(orderRoleDisplay(a), orderRoleDisplay(b), orderSort.sortOrder);
        default:
          return 0;
      }
    });
  }, [orders, orderSort.sortField, orderSort.sortOrder]);

  // ── Loading / Error states ────────────────────────────────
  const noData = intents.length === 0 && orders.length === 0;

  if (loading && noData) {
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  if (error && noData) {
    return (
      <div className="flex h-32 items-center justify-center text-rose-400 gap-2">
        <AlertCircle className="w-5 h-5" />
        <span>执行链数据加载失败</span>
      </div>
    );
  }

  // ── Intent column count for EmptyFilterRow ────────────────
  // Columns: 创建时间, 交易对, 方向, 类型, 状态, 对应信号, 金额, 建议价, (reject_reason conditional)
  const intentColSpan = 8;

  return (
    <div className="space-y-6">
      {/* Page title */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Link2 className="w-5 h-5 text-blue-400" />
          <h2 className="text-xl font-bold tracking-tight">
            {'执行链 (Execution)'}
          </h2>
        </div>
        <span className="text-sm text-zinc-500">
          {intents.length} 条意图 / {orders.length} 条订单
        </span>
      </div>

      {/* Stale data warning */}
      {error && !noData && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      {/* ── Section A: Execution Intents ──────────────────── */}
      {intents.length === 0 ? (
        <Card>
          <CardContent>
            {emptyDataCard('暂无执行意图记录')}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>
              {'信号 → 意图'}
            </CardTitle>
            <span className="text-[10px] text-zinc-500 font-mono">
              {filteredIntents.length} / {intents.length}
            </span>
          </CardHeader>
          <CardContent className="p-0">
            {/* Intent status filter */}
            <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-200 dark:border-zinc-800">
              <span className="text-xs text-zinc-500">{'状态'}</span>
              <FilterSelect
                value={intentStatusFilter}
                onChange={setIntentStatusFilter}
                options={INTENT_STATUS_OPTIONS}
              />
            </div>

            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => intentSort.toggleSort('created_at')}
                  >
                    {'创建时间'}
                    {intentSort.sortIndicator('created_at')}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => intentSort.toggleSort('symbol')}
                  >
                    {'交易对'}
                    {intentSort.sortIndicator('symbol')}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => intentSort.toggleSort('direction')}
                  >
                    {'方向'}
                    {intentSort.sortIndicator('direction')}
                  </TableHead>
                  <TableHead>{'类型'}</TableHead>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => intentSort.toggleSort('status')}
                  >
                    {'状态'}
                    {intentSort.sortIndicator('status')}
                  </TableHead>
                  <TableHead>{'对应信号'}</TableHead>
                  <TableHead className="text-right">{'金额'}</TableHead>
                  <TableHead className="text-right">{'建议价'}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredIntents.length === 0 ? (
                  <EmptyFilterRow colSpan={intentColSpan} />
                ) : (
                  filteredIntents.map((e, idx) => {
                    const isRejected = e.status.toLowerCase() === 'rejected' || e.status.toLowerCase() === 'blocked';
                    return (
                      <React.Fragment key={idx}>
                        <TableRow className={intentRowClass(e)}>
                          <TableCell className="font-mono text-xs">
                            {fmtDateTime(e.created_at)}
                          </TableCell>
                          <TableCell className="font-mono font-medium text-blue-400">
                            {fmtDash(e.symbol)}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                e.direction === 'LONG' ? 'success' : 'danger'
                              }
                            >
                              {directionLabel(e.direction)}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {fmtDash(e.intent_type)}
                          </TableCell>
                          <TableCell>
                            <Badge variant={intentStatusVariant(e.status)}>
                              {intentStatusLabel(e.status)}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs text-zinc-500">
                            {e.signal_id ? truncateId(e.signal_id) : DASH}
                          </TableCell>
                          <TableCell className="font-mono text-right">
                            {e.amount != null ? fmtDec(e.amount) : DASH}
                          </TableCell>
                          <TableCell className="font-mono text-right">
                            {e.entry_price != null
                              ? fmtDec(e.entry_price)
                              : DASH}
                          </TableCell>
                        </TableRow>
                        {/* Reject reason row — only for rejected intents */}
                        {isRejected && e.reject_reason && (
                          <TableRow className="bg-rose-500/5">
                            <TableCell colSpan={4} />
                            <TableCell
                              colSpan={4}
                              className="text-xs text-rose-500 italic"
                            >
                              {'拒绝原因: ' + e.reject_reason}
                            </TableCell>
                          </TableRow>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ── Section B: Orders ─────────────────────────────── */}
      {orders.length === 0 ? (
        <Card>
          <CardContent>
            {emptyDataCard('暂无订单记录')}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>
              {'订单链'}
            </CardTitle>
            <span className="text-[10px] text-zinc-500 font-mono">
              {sortedOrders.length} 条
            </span>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => orderSort.toggleSort('role')}
                  >
                    {'订单角色'}
                    {orderSort.sortIndicator('role')}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => orderSort.toggleSort('symbol')}
                  >
                    {'交易对'}
                    {orderSort.sortIndicator('symbol')}
                  </TableHead>
                  <TableHead>{'订单类型'}</TableHead>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => orderSort.toggleSort('status')}
                  >
                    {'状态'}
                    {orderSort.sortIndicator('status')}
                  </TableHead>
                  <TableHead className="text-right">{'数量'}</TableHead>
                  <TableHead className="text-right">{'委托价'}</TableHead>
                  <TableHead
                    className="cursor-pointer select-none"
                    onClick={() => orderSort.toggleSort('updated_at')}
                  >
                    {'更新时间'}
                    {orderSort.sortIndicator('updated_at')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedOrders.map((o, idx) => (
                  <TableRow key={idx} className={orderRowClass(o)}>
                    <TableCell>
                      <Badge variant={orderRoleVariant(o.role)}>
                        {orderRoleDisplay(o)}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono font-medium text-blue-400">
                      {fmtDash(o.symbol)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {orderTypeLabel(o.type, o.price)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={orderStatusVariant(o.status)}>
                        {orderStatusLabel(o.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-right">
                      {fmtDec(o.quantity)}
                    </TableCell>
                    <TableCell className="font-mono text-right">
                      {orderPriceDisplay(o.price, o.type)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {fmtDateTime(o.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
