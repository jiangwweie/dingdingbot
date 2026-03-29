-- Migration 003: Add evaluation_summary and trace_tree fields to signal_attempts table
-- Date: 2026-03-29
-- Description: Add support for evaluation report and trace tree visualization

-- Add evaluation_summary field
ALTER TABLE signal_attempts
ADD COLUMN evaluation_summary TEXT DEFAULT NULL;

-- Add trace_tree field
ALTER TABLE signal_attempts
ADD COLUMN trace_tree JSON DEFAULT NULL;
