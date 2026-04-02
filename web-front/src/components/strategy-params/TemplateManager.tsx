import React, { useState, useCallback } from 'react';
import { Save, FolderOpen, Trash2, Clock, User, FileText, X } from 'lucide-react';
import type { StrategyParamTemplate } from '../../lib/api';

interface TemplateManagerProps {
  templates: StrategyParamTemplate[];
  onLoadTemplate: (templateId: number) => void;
  onSaveTemplate: (name: string, description?: string) => Promise<void>;
  onDeleteTemplate: (templateId: number) => Promise<void>;
  isLoading?: boolean;
}

/**
 * 策略参数模板管理器
 * 支持保存、加载、删除参数模板
 */
export default function TemplateManager({
  templates,
  onLoadTemplate,
  onSaveTemplate,
  onDeleteTemplate,
  isLoading = false,
}: TemplateManagerProps) {
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [templateDescription, setTemplateDescription] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<StrategyParamTemplate | null>(null);

  const handleSaveClick = () => {
    setShowSaveDialog(true);
  };

  const handleSaveConfirm = async () => {
    if (!templateName.trim()) return;
    await onSaveTemplate(templateName, templateDescription || undefined);
    setShowSaveDialog(false);
    setTemplateName('');
    setTemplateDescription('');
  };

  const handleSaveCancel = () => {
    setShowSaveDialog(false);
    setTemplateName('');
    setTemplateDescription('');
  };

  const handleLoadClick = (template: StrategyParamTemplate) => {
    setSelectedTemplate(template);
  };

  const handleLoadConfirm = () => {
    if (selectedTemplate) {
      onLoadTemplate(selectedTemplate.id);
      setSelectedTemplate(null);
    }
  };

  const handleDeleteClick = async (template: StrategyParamTemplate) => {
    if (window.confirm(`确定要删除模板"${template.name}"吗？此操作不可恢复。`)) {
      await onDeleteTemplate(template.id);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-purple-500 rounded-full" />
          <h3 className="text-sm font-semibold text-gray-900">参数模板管理</h3>
        </div>
        <button
          onClick={handleSaveClick}
          disabled={isLoading}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-white bg-purple-500 rounded-lg hover:bg-purple-600 transition disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          保存为模板
        </button>
      </div>

      {/* 模板列表 */}
      <div className="space-y-2">
        {templates.length === 0 ? (
          <div className="text-center py-8 text-sm text-gray-400">
            暂无保存的模板
          </div>
        ) : (
          templates.map((template) => (
            <div
              key={template.id}
              className="flex items-center gap-3 p-3 border border-gray-100 rounded-lg hover:border-purple-200 hover:bg-purple-50/50 transition"
            >
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                <FolderOpen className="w-5 h-5 text-purple-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {template.name}
                </p>
                <div className="flex items-center gap-4 mt-1">
                  {template.description && (
                    <p className="text-xs text-gray-500 truncate">
                      {template.description}
                    </p>
                  )}
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    <span className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {template.created_by}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(template.created_at).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleLoadClick(template)}
                  className="px-3 py-1.5 text-xs font-medium text-purple-600 bg-purple-50 rounded-lg hover:bg-purple-100 transition"
                >
                  加载
                </button>
                <button
                  onClick={() => handleDeleteClick(template)}
                  className="p-1.5 hover:bg-red-50 rounded-lg transition"
                >
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 保存为模板对话框 */}
      {showSaveDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={handleSaveCancel}
          />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900">
                保存为模板
              </h3>
              <button
                onClick={handleSaveCancel}
                className="p-2 hover:bg-gray-100 rounded-lg transition"
              >
                <X className="w-5 h-5 text-gray-400" />
              </button>
            </div>
            <div className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  模板名称 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="例如：激进策略、保守策略"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  描述（可选）
                </label>
                <textarea
                  value={templateDescription}
                  onChange={(e) => setTemplateDescription(e.target.value)}
                  placeholder="描述此模板的特点和适用场景"
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                />
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
              <button
                onClick={handleSaveCancel}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition"
              >
                取消
              </button>
              <button
                onClick={handleSaveConfirm}
                disabled={!templateName.trim() || isLoading}
                className="px-4 py-2 text-sm font-medium text-white bg-purple-500 rounded-lg hover:bg-purple-600 transition disabled:opacity-50"
              >
                {isLoading ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 加载模板确认对话框 */}
      {selectedTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setSelectedTemplate(null)}
          />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-purple-500 rounded-lg flex items-center justify-center">
                  <FolderOpen className="w-5 h-5 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900">
                  加载模板
                </h3>
              </div>
              <button
                onClick={() => setSelectedTemplate(null)}
                className="p-2 hover:bg-gray-100 rounded-lg transition"
              >
                <X className="w-5 h-5 text-gray-400" />
              </button>
            </div>
            <div className="px-6 py-4">
              <p className="text-sm text-gray-600 mb-4">
                确定要加载模板 <span className="font-medium text-gray-900">"{selectedTemplate.name}"</span> 吗？
              </p>
              {selectedTemplate.description && (
                <div className="p-3 bg-gray-50 rounded-lg mb-4">
                  <div className="flex items-start gap-2">
                    <FileText className="w-4 h-4 text-gray-400 mt-0.5" />
                    <p className="text-xs text-gray-600">
                      {selectedTemplate.description}
                    </p>
                  </div>
                </div>
              )}
              <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-xs text-yellow-700">
                  注意：加载模板会覆盖当前的参数配置，请确保已保存重要更改。
                </p>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
              <button
                onClick={() => setSelectedTemplate(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition"
              >
                取消
              </button>
              <button
                onClick={handleLoadConfirm}
                className="px-4 py-2 text-sm font-medium text-white bg-purple-500 rounded-lg hover:bg-purple-600 transition"
              >
                确认加载
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
