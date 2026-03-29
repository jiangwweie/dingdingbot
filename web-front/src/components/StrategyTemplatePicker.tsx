import { useState } from 'react';
import { X, Zap, Search } from 'lucide-react';
import { cn } from '../lib/utils';
import { StrategyDefinition } from '../lib/api';

interface StrategyTemplate {
  id: number;
  name: string;
  description: string | null;
}

interface StrategyTemplatePickerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (strategy: StrategyDefinition) => void;
  templates: StrategyTemplate[];
  isLoading?: boolean;
}

export default function StrategyTemplatePicker({
  open,
  onClose,
  onSelect,
  templates,
  isLoading = false,
}: StrategyTemplatePickerProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<StrategyTemplate | null>(null);

  if (!open) return null;

  const filteredTemplates = templates.filter((t) =>
    t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    t.description?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleConfirm = () => {
    if (selectedTemplate) {
      // Convert template to StrategyDefinition
      // The parent component will fetch full details and convert
      onSelect({
        id: selectedTemplate.id.toString(),
        name: selectedTemplate.name,
        trigger: {
          id: 'temp',
          type: 'pinbar',
          enabled: true,
          params: {},
        },
        filters: [],
        filter_logic: 'AND',
        is_global: true,
        apply_to: [],
      } as StrategyDefinition);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold">从策略工作台导入</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-gray-200">
          <div className="relative">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="搜索策略模板..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:border-black transition-colors"
            />
          </div>
        </div>

        {/* Template List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {isLoading ? (
            <div className="text-center py-8 text-gray-400">
              <div className="w-5 h-5 border-2 border-gray-300 border-t-black rounded-full animate-spin mx-auto" />
              <p className="mt-2 text-sm">加载中...</p>
            </div>
          ) : filteredTemplates.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <Zap className="w-10 h-10 mx-auto mb-2 opacity-20" />
              <p className="text-sm">暂无策略模板</p>
            </div>
          ) : (
            filteredTemplates.map((template) => (
              <div
                key={String(template.id)}
                onClick={() => setSelectedTemplate(template)}
                className={cn(
                  'p-3 border rounded-lg cursor-pointer transition-colors flex items-center gap-3',
                  selectedTemplate?.id === template.id
                    ? 'border-black bg-black/5'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                )}
              >
                <div className="w-10 h-10 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center flex-shrink-0">
                  <Zap className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{template.name}</p>
                  {template.description && (
                    <p className="text-xs text-gray-500 truncate">{template.description}</p>
                  )}
                </div>
                {selectedTemplate?.id === template.id && (
                  <div className="w-5 h-5 rounded-full bg-black text-white flex items-center justify-center flex-shrink-0">
                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-gray-200 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            disabled={!selectedTemplate}
            className="px-4 py-2 bg-black text-white text-sm rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            导入选中策略
          </button>
        </div>
      </div>
    </div>
  );
}
