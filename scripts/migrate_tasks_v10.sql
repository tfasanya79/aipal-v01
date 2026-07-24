-- AiPal v10: Today planner task columns
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parent_task_id INTEGER REFERENCES tasks(id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS estimated_minutes INTEGER;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS category VARCHAR(32);

CREATE INDEX IF NOT EXISTS ix_tasks_parent_task_id ON tasks(parent_task_id);
