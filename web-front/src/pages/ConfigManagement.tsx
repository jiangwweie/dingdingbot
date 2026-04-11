/**
 * 配置管理 - 统一页面（Ant Design Tabs 容器）
 *
 * 4 个 Tab:
 * - Tab 1: 策略管理 → <StrategyConfig />
 * - Tab 2: 系统设置 → <SystemSettings variant="tab" />
 * - Tab 3: 备份恢复 → <BackupTab />
 * - Tab 4: 生效配置总览 → <EffectiveConfigView />
 *
 * URL query string 同步: ?tab=strategies ↔ active tab
 *
 * @route /config
 */

import { Tabs } from 'antd';
import { useSearchParams } from 'react-router-dom';
import StrategyConfig from './config/StrategyConfig';
import SystemSettings from './config/SystemSettings';
import { BackupTab } from './config/BackupTab';
import EffectiveConfigView from './config/EffectiveConfigView';

// ============================================================
// Tab Key Mapping
// ============================================================

const TAB_ITEMS = [
  {
    key: 'strategies',
    label: '策略管理',
    children: <StrategyConfig />,
  },
  {
    key: 'system',
    label: '系统设置',
    children: <SystemSettings variant="tab" />,
  },
  {
    key: 'backup',
    label: '备份恢复',
    children: <BackupTab />,
  },
  {
    key: 'effective',
    label: '生效配置总览',
    children: <EffectiveConfigView />,
  },
];

// ============================================================
// Main Component
// ============================================================

export default function ConfigManagement() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'strategies';

  const handleChange = (key: string) => {
    setSearchParams({ tab: key });
  };

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight text-gray-900 mb-1">
        配置管理
      </h1>
      <p className="text-sm text-gray-500 mb-6">
        管理策略参数、系统配置、导入导出、版本快照
      </p>
      <Tabs
        activeKey={activeTab}
        onChange={handleChange}
        items={TAB_ITEMS}
        size="large"
      />
    </div>
  );
}
