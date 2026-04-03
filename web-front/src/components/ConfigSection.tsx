/**
 * ConfigSection 组件
 *
 * 通用的配置区块组件，用于渲染配置表单
 */

import React from 'react';
import { cn } from '../lib/utils';
import ConfigTooltip, { ConfigLabel } from './ConfigTooltip';
import { AlertCircle } from 'lucide-react';

interface FieldConfig {
  key: string;
  label: string;
  tooltip: string;
  type: 'number' | 'text' | 'switch' | 'readonly';
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  readonly?: boolean;
  requires_restart?: boolean;
  value?: any; // Optional override for external value control
}

interface ConfigSectionProps {
  title: string;
  description?: string;
  fields: FieldConfig[];
  values: Record<string, any>;
  onChange: (key: string, value: any) => void;
  errors?: Record<string, string>;
  className?: string;
}

export default function ConfigSection({
  title,
  description,
  fields,
  values,
  onChange,
  errors = {},
  className,
}: ConfigSectionProps) {
  const renderField = (field: FieldConfig) => {
    const value = field.value !== undefined ? field.value : values[field.key];
    const error = errors[field.key];
    const showRestartBadge = field.requires_restart;

    switch (field.type) {
      case 'number':
        return (
          <div key={field.key} className="space-y-1">
            <ConfigLabel label={field.label} tooltip={field.tooltip} />
            <div className="relative">
              <input
                type="number"
                step={field.step || 'any'}
                min={field.min}
                max={field.max}
                value={value ?? ''}
                onChange={(e) => onChange(field.key, e.target.value)}
                className={cn(
                  'w-full rounded-lg border px-3 py-2 text-sm outline-none transition-colors',
                  error
                    ? 'border-red-300 focus:border-red-500'
                    : 'border-gray-300 focus:border-black',
                  field.readonly && 'bg-gray-50 cursor-not-allowed'
                )}
                disabled={field.readonly}
              />
              {field.unit && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  {field.unit}
                </span>
              )}
            </div>
            {showRestartBadge && (
              <p className="text-xs text-apple-orange flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                修改此配置需要重启系统
              </p>
            )}
            {error && (
              <p className="text-xs text-red-500 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {error}
              </p>
            )}
          </div>
        );

      case 'text':
        return (
          <div key={field.key} className="space-y-1">
            <ConfigLabel label={field.label} tooltip={field.tooltip} />
            <input
              type="text"
              value={value ?? ''}
              onChange={(e) => onChange(field.key, e.target.value)}
              className={cn(
                'w-full rounded-lg border px-3 py-2 text-sm outline-none transition-colors',
                error
                  ? 'border-red-300 focus:border-red-500'
                  : 'border-gray-300 focus:border-black',
                field.readonly && 'bg-gray-50 cursor-not-allowed'
              )}
              disabled={field.readonly}
            />
            {showRestartBadge && (
              <p className="text-xs text-apple-orange flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                修改此配置需要重启系统
              </p>
            )}
            {error && (
              <p className="text-xs text-red-500 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {error}
              </p>
            )}
          </div>
        );

      case 'switch':
        return (
          <div key={field.key} className="space-y-1">
            <div className="flex items-center justify-between">
              <ConfigLabel label={field.label} tooltip={field.tooltip} />
              <button
                type="button"
                role="switch"
                aria-checked={!!value}
                disabled={field.readonly}
                onClick={() => onChange(field.key, !value)}
                className={cn(
                  'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none',
                  value ? 'bg-black' : 'bg-gray-200',
                  field.readonly && 'cursor-not-allowed opacity-50'
                )}
              >
                <span
                  className={cn(
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
                    value ? 'translate-x-5' : 'translate-x-0'
                  )}
                />
              </button>
            </div>
            {showRestartBadge && (
              <p className="text-xs text-apple-orange flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                修改此配置需要重启系统
              </p>
            )}
          </div>
        );

      case 'readonly':
      default:
        return (
          <div key={field.key} className="space-y-1">
            <ConfigLabel label={field.label} tooltip={field.tooltip} />
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700 font-mono">
              {value !== undefined ? String(value) : '-'}
            </div>
          </div>
        );
    }
  };

  return (
    <div className={cn('bg-white rounded-xl border border-gray-100 shadow-sm p-5', className)}>
      {/* Header */}
      <div className="mb-5 pb-4 border-b border-gray-100">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        {description && (
          <p className="text-sm text-gray-500 mt-1">{description}</p>
        )}
      </div>

      {/* Fields Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {fields.map(renderField)}
      </div>
    </div>
  );
}
