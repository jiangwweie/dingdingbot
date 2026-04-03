-- Migration 004: Add is_active field to custom_strategies table
-- Date: 2026-04-03
-- Description: Add is_active column to support strategy activation/deactivation

-- Add is_active column with default value 0 (inactive)
ALTER TABLE custom_strategies ADD COLUMN is_active INTEGER DEFAULT 0;

-- Create index on is_active for faster active strategy lookup
CREATE INDEX IF NOT EXISTS idx_custom_strategies_is_active ON custom_strategies(is_active);
