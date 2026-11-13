import type { components } from '../api/schema';

type Feed = components['schemas']['ManagementFeedReadiness'];

export function mapManagementHealth(feed: Feed | null | undefined, observedAtMs: number) {
  if (!feed?.required) return { blocked: false, summary: '', details: '' };
  if (feed.ready) return { blocked: false, summary: '管理采集已就绪', details: '管理采集已就绪；其他准入门禁仍独立核验' };
  const elapsed = feed.blocked_since_ms == null ? '持续时间未知' :
    `本连接已持续 ${Math.max(0, Math.floor((observedAtMs - feed.blocked_since_ms) / 60000))} 分钟`;
  return { blocked: true, summary: '管理采集受限 · 新开仓受阻',
    details: `原因：${feed.blocker_code ?? 'management_receiver_not_ready'} · ${elapsed} · 接收 / 应用水位：${feed.persisted_watermark ?? '未知'} / ${feed.applied_watermark ?? '未知'}。普通自动管理受限，已有交易所保护单仍需逐票核验。` };
}
