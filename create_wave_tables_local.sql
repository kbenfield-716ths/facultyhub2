-- Create wave draft tables locally for testing
-- Run this to initialize tables before deployment

CREATE TABLE IF NOT EXISTS draft_wave_configs (
    id TEXT PRIMARY KEY,
    year INTEGER NOT NULL UNIQUE,
    close_date DATETIME NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    activated_at DATETIME,
    closed_at DATETIME
);

CREATE TABLE IF NOT EXISTS draft_waves (
    id TEXT PRIMARY KEY,
    config_id TEXT NOT NULL,
    name TEXT NOT NULL,
    open_date DATETIME NOT NULL,
    wave_order INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id)
);

CREATE TABLE IF NOT EXISTS wave_faculty_assignments (
    id TEXT PRIMARY KEY,
    wave_id TEXT NOT NULL,
    faculty_id TEXT NOT NULL,
    notified_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wave_id) REFERENCES draft_waves(id),
    FOREIGN KEY (faculty_id) REFERENCES faculty(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_wave_faculty_unique
ON wave_faculty_assignments(wave_id, faculty_id);

CREATE TABLE IF NOT EXISTS week_draft_status (
    id TEXT PRIMARY KEY,
    config_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    unavailable_count INTEGER DEFAULT 0,
    volunteer_count INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id),
    FOREIGN KEY (week_id) REFERENCES service_weeks(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_week_status_config_week
ON week_draft_status(config_id, week_id);

CREATE TABLE IF NOT EXISTS draft_week_requests (
    id TEXT PRIMARY KEY,
    config_id TEXT NOT NULL,
    faculty_id TEXT NOT NULL,
    week_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (config_id) REFERENCES draft_wave_configs(id),
    FOREIGN KEY (faculty_id) REFERENCES faculty(id),
    FOREIGN KEY (week_id) REFERENCES service_weeks(id)
);

CREATE INDEX IF NOT EXISTS idx_draft_request_faculty_week
ON draft_week_requests(faculty_id, week_id);

CREATE INDEX IF NOT EXISTS idx_draft_request_config
ON draft_week_requests(config_id);
