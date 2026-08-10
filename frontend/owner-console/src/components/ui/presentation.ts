export type OwnerReason = {
  label: string;
  raw: string;
};

interface FormatMoneyOptions {
  sign?: boolean;
}

const STATUS_LABELS: Record<string, string> = {
  active: "进行中",
  blocked: "已阻断",
  claimed: "正在处理",
  complete: "已完成",
  completed: "已完成",
  current: "进行中",
  enabled: "已启用",
  exit_in_progress: "正在退出",
  exits_requested: "已请求退出",
  in_progress: "进行中",
  needs_intervention: "需要关注",
  paused: "已暂停",
  paused_by_global: "已被全局暂停",
  pending: "等待执行",
  reconciliation_pending: "正在核对",
  recovered_incident: "异常已恢复",
  review_pending: "正在复盘",
  running: "运行中",
  settlement_pending: "正在结算",
  terminal: "已结束",
  POSITION_PROTECTED: "持仓已受保护",
  TERMINAL: "已结束",
  ENTRY_PENDING: "等待开仓",
  ENTRY_SUBMITTED: "已提交开仓",
  unavailable: "暂不可用",
  waiting_for_review: "等待复盘",
  waiting_for_settlement: "等待结算",
};

function roundedDecimal(value: string, fractionDigits: number): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return value;

  const [, sign = "", whole = "0", fraction = ""] = match;
  const retained = fraction.slice(0, fractionDigits).padEnd(fractionDigits, "0");
  let atomic = BigInt(`${whole}${retained}`);
  if (fraction.charAt(fractionDigits) >= "5") atomic += 1n;
  if (atomic === 0n) return `0.${"0".repeat(fractionDigits)}`;

  const digits = atomic.toString().padStart(fractionDigits + 1, "0");
  const integer = digits.slice(0, -fractionDigits);
  const decimal = digits.slice(-fractionDigits);
  return `${sign}${integer}.${decimal}`;
}

export function formatMoney(
  value: string,
  unit: string,
  options: FormatMoneyOptions = {},
): string {
  const rounded = roundedDecimal(value, 2);
  const prefix = options.sign && !rounded.startsWith("-") && rounded !== "0.00" ? "+" : "";
  return `${prefix}${rounded} ${unit}`;
}

export function formatOwnerStatus(value: string): string {
  return STATUS_LABELS[value] ?? value;
}

export function formatOwnerReason(raw: string): OwnerReason {
  if (raw.startsWith("owner_flatten_all")) return { label: "Owner 受控平仓", raw };
  if (raw.startsWith("deployment_drain")) return { label: "部署前安全退出", raw };
  if (raw.startsWith("ticket_incident")) return { label: "交易执行需要核对", raw };
  if (raw.startsWith("exposure_family_cap")) return { label: "同类风险额度已占用", raw };
  if (raw === "budget_exhausted") return { label: "可用预算不足", raw };
  if (raw === "gross_stop_risk_capacity_exhausted") return { label: "总止损风险额度已占用", raw };
  if (raw === "incomplete_review_economics") return { label: "经济数据尚不完整", raw };
  if (raw === "monitor_limit_reached") return { label: "总览范围受限", raw };
  if (raw === "seed_enabled") return { label: "系统初始化启用", raw };
  if (raw === "owner_manual_control") return { label: "Owner 手动操作", raw };
  if (raw === "hard_safety_stop") return { label: "安全保护已阻断", raw };
  return { label: "技术原因待查看", raw };
}

export function formatTimestamp(value: number | null | undefined, options: Intl.DateTimeFormatOptions = {}): string {
  if (value === null || value === undefined) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...options,
  }).format(new Date(value));
}
