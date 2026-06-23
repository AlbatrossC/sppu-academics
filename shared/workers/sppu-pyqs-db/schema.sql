CREATE TABLE IF NOT EXISTS contact_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  message TEXT NOT NULL,
  ip_address TEXT,
  user_agent TEXT,
  source_url TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS download_clients (
  client_id TEXT PRIMARY KEY,
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  user_agent TEXT,
  download_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_download_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id TEXT NOT NULL,
  subject_link TEXT NOT NULL,
  subject_name TEXT NOT NULL,
  exam_type TEXT NOT NULL,
  file_count INTEGER NOT NULL DEFAULT 0,
  branch TEXT,
  pattern TEXT,
  semester TEXT,
  ip_address TEXT,
  user_agent TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (client_id) REFERENCES download_clients(client_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_download_events_subject
  ON paper_download_events(subject_name);

CREATE INDEX IF NOT EXISTS idx_paper_download_events_exam_type
  ON paper_download_events(exam_type);

CREATE INDEX IF NOT EXISTS idx_paper_download_events_created_at
  ON paper_download_events(created_at);

CREATE INDEX IF NOT EXISTS idx_paper_download_events_branch_pattern
  ON paper_download_events(branch, pattern);
