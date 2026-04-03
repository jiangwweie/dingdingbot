/**
 * Tooltip 组件
 *
 * 为配置项提供悬停提示功能
 */

import React from 'react';
import { Info } from 'lucide-react';
import { cn } from '../lib/utils';

interface ConfigTooltipProps {
  content: string;
  children?: React.ReactNode;
  className?: string;
  position?: 'top' | 'right' | 'bottom' | 'left';
}

export default function ConfigTooltip({
  content,
  children,
  className,
  position = 'top',
}: ConfigTooltipProps) {
  const [isVisible, setIsVisible] = React.useState(false);

  // Position classes
  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
  };

  // Arrow position classes
  const arrowPositionClasses = {
    top: 'bottom-[-6px] left-1/2 -translate-x-1/2',
    right: 'left-[-6px] top-1/2 -translate-y-1/2',
    bottom: 'top-[-6px] left-1/2 -translate-x-1/2',
    left: 'right-[-6px] top-1/2 -translate-y-1/2',
  };

  return (
    <div
      className={cn('relative inline-flex items-center', className)}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {/* Trigger */}
      {children || (
        <Info className="w-4 h-4 text-gray-400 hover:text-gray-600 cursor-help" />
      )}

      {/* Tooltip Content */}
      {isVisible && (
        <>
          {/* Backdrop for better visibility */}
          <div
            className={cn(
              'fixed inset-0 z-40',
              'cursor-default'
            )}
            onMouseEnter={() => setIsVisible(true)}
            onMouseLeave={() => setIsVisible(false)}
          />

          {/* Tooltip */}
          <div
            className={cn(
              'absolute z-50 px-3 py-2',
              'bg-gray-900 text-white text-xs rounded-lg shadow-lg',
              'max-w-xs whitespace-normal break-words',
              'animate-in fade-in duration-200',
              positionClasses[position]
            )}
            style={{ minWidth: '200px', maxWidth: '300px' }}
          >
            {content}

            {/* Arrow */}
            <div
              className={cn(
                'absolute w-3 h-3 bg-gray-900 rotate-45',
                arrowPositionClasses[position]
              )}
            />
          </div>
        </>
      )}
    </div>
  );
}

/**
 * ConfigLabel 组件
 *
 * 带 Tooltip 的配置标签
 */
interface ConfigLabelProps {
  label: string;
  tooltip: string;
  required?: boolean;
  className?: string;
}

export function ConfigLabel({ label, tooltip, required, className }: ConfigLabelProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <span className="text-sm font-medium text-gray-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </span>
      <ConfigTooltip content={tooltip} />
    </div>
  );
}
