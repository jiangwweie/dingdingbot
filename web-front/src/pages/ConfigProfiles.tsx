import { useState, useCallback, useEffect } from 'react';
import {
  FileText,
  Plus,
  Upload,
  Download,
  MoreHorizontal,
  Copy,
  Edit2,
  Trash2,
  Check,
  X,
  Search,
  Sliders,
  Database,
  Settings,
} from 'lucide-react';
import {
  fetchProfiles,
  createProfile,
  switchProfile,
  deleteProfile,
  downloadProfileYaml,
  importProfile,
  renameProfile,
} from '../lib/api';
import type { ConfigProfile } from '../types/config-profile';
import CreateProfileModal from '../components/profiles/CreateProfileModal';
import SwitchPreviewModal from '../components/profiles/SwitchPreviewModal';
import DeleteConfirmModal from '../components/profiles/DeleteConfirmModal';
import ImportProfileModal from '../components/profiles/ImportProfileModal';
import RenameProfileModal from '../components/profiles/RenameProfileModal';
import { StrategiesTab } from './config/StrategiesTab';
import { BackupTab } from './config/BackupTab';
import { SystemTab } from './config/SystemTab';
import { cn } from '../lib/utils';

export default function ConfigProfiles() {
  const [activeTab, setActiveTab] = useState<'profiles' | 'strategies' | 'backup' | 'system'>('profiles');
  // Data state
  const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // UI state
  const [searchQuery, setSearchQuery] = useState('');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [switchModalOpen, setSwitchModalOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<ConfigProfile | null>(null);
  const [notification, setNotification] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  // Load profiles
  const loadProfiles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchProfiles();
      setProfiles(data.profiles);
      setActiveProfile(data.active_profile);
      setError(null);
    } catch (err: any) {
      setError(err.message || '加载 Profile 列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  // Show notification
  const showNotification = (type: 'success' | 'error', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 3000);
  };

  // Handle create profile
  const handleCreate = useCallback(
    async (name: string, description?: string, switchAfterCreate?: boolean) => {
      try {
        await createProfile({
          name,
          description: description || null,
          copy_from: selectedProfile?.name || 'default',
          switch_immediately: switchAfterCreate,
        });
        const sourceText = selectedProfile ? `复制自 "${selectedProfile.name}"` : '创建';
        showNotification('success', `Profile "${name}" ${sourceText}成功`);
        setCreateModalOpen(false);
        setSelectedProfile(null);
        await loadProfiles();
      } catch (err: any) {
        showNotification('error', err.message || '创建失败');
        throw err;
      }
    },
    [selectedProfile, loadProfiles]
  );

  // Handle switch profile
  const handleSwitch = useCallback(
    async (name: string) => {
      setSelectedProfile(profiles.find((p) => p.name === name) || null);
      setSwitchModalOpen(true);
    },
    [profiles]
  );

  const confirmSwitch = useCallback(async () => {
    if (!selectedProfile) return;

    try {
      const result = await switchProfile(selectedProfile.name);
      showNotification('success', result.message);
      setSwitchModalOpen(false);
      setSelectedProfile(null);
      await loadProfiles();
    } catch (err: any) {
      showNotification('error', err.message || '切换失败');
      throw err;
    }
  }, [selectedProfile, loadProfiles]);

  // Handle delete profile
  const handleDelete = useCallback(
    (name: string) => {
      setSelectedProfile(profiles.find((p) => p.name === name) || null);
      setDeleteModalOpen(true);
    },
    [profiles]
  );

  const confirmDelete = useCallback(async () => {
    if (!selectedProfile) return;

    try {
      await deleteProfile(selectedProfile.name);
      showNotification('success', `Profile "${selectedProfile.name}" 已删除`);
      setDeleteModalOpen(false);
      setSelectedProfile(null);
      await loadProfiles();
    } catch (err: any) {
      showNotification('error', err.message || '删除失败');
      throw err;
    }
  }, [selectedProfile, loadProfiles]);

  // Handle export
  const handleExport = useCallback(async (name: string) => {
    try {
      await downloadProfileYaml(name);
      showNotification('success', `Profile "${name}" 导出成功`);
    } catch (err: any) {
      showNotification('error', `导出失败：${err.message}`);
    }
  }, []);

  // Handle import success
  const handleImportSuccess = useCallback(async () => {
    showNotification('success', '配置导入成功');
    setImportModalOpen(false);
    await loadProfiles();
  }, [loadProfiles]);

  // Handle rename success
  const handleRenameSuccess = useCallback(async (newName: string, newDescription?: string) => {
    if (!selectedProfile) return;

    try {
      await renameProfile(selectedProfile.name, {
        name: newName,
        description: newDescription || null,
      });
      showNotification('success', `Profile 已重命名为 "${newName}"`);
      setRenameModalOpen(false);
      setSelectedProfile(null);
      await loadProfiles();
    } catch (err: any) {
      showNotification('error', err.message || '重命名失败');
      throw err;
    }
  }, [selectedProfile, loadProfiles]);

  // Handle rename profile
  const handleRename = useCallback(
    (name: string) => {
      setSelectedProfile(profiles.find((p) => p.name === name) || null);
      setRenameModalOpen(true);
    },
    [profiles]
  );

  // Handle duplicate profile
  const handleDuplicate = useCallback(
    (name: string) => {
      // Open create modal with source profile set
      setSelectedProfile(profiles.find((p) => p.name === name) || null);
      setCreateModalOpen(true);
    },
    [profiles]
  );

  // Filter profiles by search query
  const filteredProfiles = profiles.filter((p) =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (p.description && p.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-600">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            配置 Profile 管理
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            管理多套配置档案，根据交易风格快速切换
          </p>
        </div>
        {activeTab === 'profiles' && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setImportModalOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              <Upload className="w-4 h-4" />
              导入
            </button>
            <button
              onClick={() => setCreateModalOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg font-medium hover:bg-gray-800 transition-colors"
            >
              <Plus className="w-4 h-4" />
              新建 Profile
            </button>
          </div>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b border-gray-200">
        <button
          onClick={() => setActiveTab('profiles')}
          className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2 ${
            activeTab === 'profiles'
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <FileText className="w-4 h-4" />
          配置 Profile
        </button>
        <button
          onClick={() => setActiveTab('strategies')}
          className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2 ${
            activeTab === 'strategies'
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Sliders className="w-4 h-4" />
          策略管理
        </button>
        <button
          onClick={() => setActiveTab('system')}
          className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2 ${
            activeTab === 'system'
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Settings className="w-4 h-4" />
          系统配置
        </button>
        <button
          onClick={() => setActiveTab('backup')}
          className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2 ${
            activeTab === 'backup'
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Database className="w-4 h-4" />
          备份恢复
        </button>
      </div>

      {/* Notification */}
      {notification && (
        <div
          className={cn(
            'p-4 rounded-xl flex items-center gap-3',
            notification.type === 'success'
              ? 'bg-green-50 text-green-700 border border-green-200'
              : 'bg-red-50 text-red-700 border border-red-200'
          )}
        >
          {notification.type === 'success' ? (
            <div className="w-2 h-2 bg-green-500 rounded-full" />
          ) : (
            <div className="w-2 h-2 bg-red-500 rounded-full" />
          )}
          {notification.message}
        </div>
      )}

      {/* Tab Content */}
      {activeTab === 'profiles' ? (
        <>
          {/* Search Bar */}
          <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="搜索 Profile 名称或描述..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-black focus:border-transparent"
        />
      </div>

      {/* Profile List */}
      <div className="grid gap-4">
        {filteredProfiles.map((profile) => (
          <div
            key={profile.name}
            className={cn(
              'bg-white rounded-2xl shadow-sm border transition-all',
              profile.is_active
                ? 'border-black shadow-md'
                : 'border-gray-100 hover:border-gray-300'
            )}
          >
            <div className="p-6">
              <div className="flex items-start justify-between">
                {/* Profile Info */}
                <div className="flex items-start gap-4 flex-1">
                  <div
                    className={cn(
                      'p-3 rounded-lg',
                      profile.is_active
                        ? 'bg-black text-white'
                        : 'bg-gray-100 text-gray-600'
                    )}
                  >
                    <FileText className="w-6 h-6" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold text-gray-900">
                        {profile.name}
                      </h3>
                      {profile.is_active && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-black text-white text-xs font-medium rounded-full">
                          <Check className="w-3 h-3" />
                          激活中
                        </span>
                      )}
                      {profile.name === 'default' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 text-gray-600 text-xs font-medium rounded-full">
                          默认
                        </span>
                      )}
                    </div>
                    {profile.description && (
                      <p className="text-sm text-gray-500 mt-1">
                        {profile.description}
                      </p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                      <span>{profile.config_count} 个配置项</span>
                      <span>创建于 {new Date(profile.created_at).toLocaleDateString('zh-CN')}</span>
                      {profile.created_from && (
                        <span>复制自 {profile.created_from}</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  {!profile.is_active && profile.name !== 'default' && (
                    <button
                      onClick={() => handleSwitch(profile.name)}
                      className="px-3 py-1.5 text-sm font-medium text-black hover:bg-gray-100 rounded-lg transition-colors"
                    >
                      切换
                    </button>
                  )}
                  {/* Copy button - available for all profiles */}
                  <button
                    onClick={() => handleDuplicate(profile.name)}
                    className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                    title="复制"
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                  {/* Edit button - not available for default */}
                  {profile.name !== 'default' && (
                    <button
                      onClick={() => handleRename(profile.name)}
                      className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                      title="编辑"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => handleExport(profile.name)}
                    className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                    title="导出"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                  {profile.name !== 'default' && !profile.is_active && (
                    <button
                      onClick={() => handleDelete(profile.name)}
                      className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="删除"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}

        {filteredProfiles.length === 0 && (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">没有找到匹配的 Profile</p>
          </div>
        )}
      </div>
      </>
      ) : activeTab === 'strategies' ? (
        /* 策略管理 Tab */
        <StrategiesTab />
      ) : activeTab === 'system' ? (
        /* 系统配置 Tab */
        <SystemTab />
      ) : (
        /* 备份恢复 Tab */
        <BackupTab />
      )}

      {/* Modals */}
      <CreateProfileModal
        open={createModalOpen}
        onClose={() => {
          setCreateModalOpen(false);
          setSelectedProfile(null);
        }}
        onCreate={handleCreate}
        existingNames={profiles.map((p) => p.name)}
        sourceProfile={selectedProfile?.name || null}
      />

      <SwitchPreviewModal
        open={switchModalOpen}
        onClose={() => {
          setSwitchModalOpen(false);
          setSelectedProfile(null);
        }}
        profileName={selectedProfile?.name || ''}
        onConfirm={confirmSwitch}
      />

      <DeleteConfirmModal
        open={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setSelectedProfile(null);
        }}
        profileName={selectedProfile?.name || ''}
        onConfirm={confirmDelete}
      />

      <ImportProfileModal
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onImportSuccess={handleImportSuccess}
      />

      <RenameProfileModal
        open={renameModalOpen}
        onClose={() => {
          setRenameModalOpen(false);
          setSelectedProfile(null);
        }}
        onRename={handleRenameSuccess}
        profileName={selectedProfile?.name || ''}
        profileDescription={selectedProfile?.description || ''}
        existingNames={profiles.map((p) => p.name)}
      />
    </div>
  );
}
