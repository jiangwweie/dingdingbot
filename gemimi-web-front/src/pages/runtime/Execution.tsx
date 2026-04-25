import React, { useEffect, useState } from 'react';
import { getRuntimeExecutionIntents, getRuntimeOrders } from '@/src/services/api';
import { ExecutionIntent, Order } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2 } from 'lucide-react';
import { format } from 'date-fns';

export default function Execution() {
  const { refreshCount } = useRefreshContext();
  const [intents, setIntents] = useState<ExecutionIntent[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getRuntimeExecutionIntents(), getRuntimeOrders()]).then(([int, ord]) => {
      if (active) {
        setIntents(int);
        setOrders(ord);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && intents.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">执行情况 (Execution View)</h2>

      <Card>
        <CardHeader><CardTitle>执行意图 (Execution Intents)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>意图 ID</TableHead>
                <TableHead>信号引用</TableHead>
                <TableHead>交易对</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead>状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {intents.map(intent => (
                <TableRow key={intent.intent_id}>
                  <TableCell className="font-mono text-xs">{intent.intent_id}</TableCell>
                  <TableCell className="font-mono text-xs text-zinc-500">{intent.signal_id}</TableCell>
                  <TableCell className="font-medium text-zinc-700 dark:text-zinc-300">{intent.symbol}</TableCell>
                  <TableCell className="font-mono text-xs text-zinc-600 dark:text-zinc-400">{format(new Date(intent.created_at), 'HH:mm:ss')}</TableCell>
                  <TableCell>
                    <Badge variant={intent.status === 'COMPLETED' ? 'success' : intent.status === 'FAILED' ? 'danger' : 'info'}>
                      {intent.status === 'COMPLETED' ? '已完成' : intent.status === 'FAILED' ? '失败' : intent.status}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>交易所订单 (Exchange Orders)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>订单 ID</TableHead>
                <TableHead>角色 (Role)</TableHead>
                <TableHead>数量 (Qty)</TableHead>
                <TableHead>价格 (Price)</TableHead>
                <TableHead>状态 (Status)</TableHead>
                <TableHead>最近更新</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map(order => (
                <TableRow key={order.order_id}>
                  <TableCell className="font-mono text-xs text-zinc-500">{order.order_id}</TableCell>
                  <TableCell><Badge variant="default">{order.role}</Badge></TableCell>
                  <TableCell className="font-mono">{order.quantity}</TableCell>
                  <TableCell className="font-mono text-blue-400">{order.price?.toFixed(2) || '市价 (MARKET)'}</TableCell>
                  <TableCell>
                    <Badge variant={order.status === 'FILLED' ? 'success' : order.status === 'REJECTED' || order.status === 'CANCELED' ? 'danger' : 'warning'}>
                      {order.status === 'FILLED' ? '已成交' : order.status === 'NEW' ? '新建' : order.status === 'CANCELED' ? '已取消' : order.status === 'REJECTED' ? '已拒绝' : order.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-zinc-600 dark:text-zinc-400">{format(new Date(order.updated_at), 'HH:mm:ss')}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
