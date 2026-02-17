from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from entity.settings import Settings

SCHEMA_SQL = r'''
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY,
  username TEXT,
  display_name TEXT,
  timezone TEXT,
  pd_consent BOOLEAN NOT NULL DEFAULT FALSE,
  pd_consent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_state (
  user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  step TEXT,
  payload_json JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Admins allowed to access the admin panel.
CREATE TABLE IF NOT EXISTS admins (
  user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS enrollments (
  user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  delivery_time TEXT NOT NULL,
  enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS lessons (
  id SERIAL PRIMARY KEY,
  day_index INT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  video_url TEXT NOT NULL,
  points_viewed INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quests (
  id SERIAL PRIMARY KEY,
  day_index INT NOT NULL UNIQUE,
  prompt TEXT NOT NULL,
  points INT NOT NULL DEFAULT 1,
  photo_file_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS progress (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day_index INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'sent',
  done_at TIMESTAMPTZ,
  UNIQUE(user_id, day_index)
);

CREATE TABLE IF NOT EXISTS quest_answers (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day_index INT NOT NULL,
  answer_text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS points_ledger (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  source_key TEXT,
  points INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questionnaires (
  id SERIAL PRIMARY KEY,
  question TEXT NOT NULL,
  qtype TEXT NOT NULL DEFAULT 'manual',
  use_in_charts BOOLEAN NOT NULL DEFAULT FALSE,
  points INT NOT NULL DEFAULT 1,
  created_by BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questionnaire_responses (
  id SERIAL PRIMARY KEY,
  questionnaire_id INT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  score INT NOT NULL,
  comment TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outbox_jobs (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  run_at TIMESTAMPTZ NOT NULL,
  payload_json JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending_runat ON outbox_jobs(status, run_at);

-- Tracks which items were delivered to a user (separate from completion/progress).
CREATE TABLE IF NOT EXISTS deliveries (
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day_index INT NOT NULL,
  item_type TEXT NOT NULL, -- 'lesson' | 'quest'
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, day_index, item_type)
);


-- Idempotency guard for daily deliveries (prevents duplicates).
CREATE TABLE IF NOT EXISTS sent_jobs (
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_type TEXT NOT NULL, -- 'lesson' | 'quest' | 'questionnaire' etc
  day_index INT NOT NULL,
  for_date DATE NOT NULL,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, content_type, day_index, for_date)
);

-- Daily content packs (generated once per UTC day, optionally regenerated when a new lesson is added).
CREATE TABLE IF NOT EXISTS daily_sets (
  id SERIAL PRIMARY KEY,
  utc_date DATE NOT NULL,
  lesson_day_index INT,
  topic TEXT NOT NULL,
  trigger TEXT NOT NULL, -- 'midnight' | 'lesson_added'
  status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'ready' | 'failed' | 'superseded'
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_sets_date_status ON daily_sets(utc_date, status, created_at);

CREATE TABLE IF NOT EXISTS daily_items (
  id SERIAL PRIMARY KEY,
  set_id INT NOT NULL REFERENCES daily_sets(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, -- 'quote' | 'tip' | 'image' | 'film' | 'book'
  title TEXT,
  content_text TEXT NOT NULL,
  payload_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(set_id, kind)
);

-- User habits (personal reminders)
CREATE TABLE IF NOT EXISTS habits (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  remind_time TEXT NOT NULL, -- 'HH:MM' in user's local timezone
  frequency TEXT NOT NULL DEFAULT 'daily', -- 'daily' | 'weekdays' | 'weekends'
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_habits_user_active ON habits(user_id, is_active);

-- Planned occurrences (one row per habit reminder time)
CREATE TABLE IF NOT EXISTS habit_occurrences (
  id SERIAL PRIMARY KEY,
  habit_id INT NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  scheduled_at TIMESTAMPTZ NOT NULL, -- stored in UTC
  status TEXT NOT NULL DEFAULT 'planned', -- planned|sent|done|skipped|cancelled
  action_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(habit_id, scheduled_at)
);

CREATE INDEX IF NOT EXISTS idx_habit_occ_user_sched ON habit_occurrences(user_id, scheduled_at, status);

'''

MIGRATIONS_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pd_consent BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pd_consent_at TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    "ALTER TABLE quests ADD COLUMN IF NOT EXISTS photo_file_id TEXT",
    "ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0",
    "ALTER TABLE outbox_jobs ADD COLUMN IF NOT EXISTS last_error TEXT",
    "CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
    "CREATE TABLE IF NOT EXISTS deliveries (user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, day_index INT NOT NULL, item_type TEXT NOT NULL, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (user_id, day_index, item_type))",
    "CREATE TABLE IF NOT EXISTS sent_jobs (user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, content_type TEXT NOT NULL, day_index INT NOT NULL, for_date DATE NOT NULL, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (user_id, content_type, day_index, for_date))",

    # Daily packs
    "CREATE TABLE IF NOT EXISTS daily_sets (id SERIAL PRIMARY KEY, utc_date DATE NOT NULL, lesson_day_index INT, topic TEXT NOT NULL, trigger TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS idx_daily_sets_date_status ON daily_sets(utc_date, status, created_at)",
    "CREATE TABLE IF NOT EXISTS daily_items (id SERIAL PRIMARY KEY, set_id INT NOT NULL REFERENCES daily_sets(id) ON DELETE CASCADE, kind TEXT NOT NULL, title TEXT, content_text TEXT NOT NULL, payload_json JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(set_id, kind))",

    # Habits
    "CREATE TABLE IF NOT EXISTS habits (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL, remind_time TEXT NOT NULL, frequency TEXT NOT NULL DEFAULT 'daily', is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS idx_habits_user_active ON habits(user_id, is_active)",
    "CREATE TABLE IF NOT EXISTS habit_occurrences (id SERIAL PRIMARY KEY, habit_id INT NOT NULL REFERENCES habits(id) ON DELETE CASCADE, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, scheduled_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL DEFAULT 'planned', action_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(habit_id, scheduled_at))",
    "CREATE INDEX IF NOT EXISTS idx_habit_occ_user_sched ON habit_occurrences(user_id, scheduled_at, status)",
]

class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    def connect(self):
        return psycopg.connect(
            host=self.settings.db_host,
            port=self.settings.db_port,
            dbname=self.settings.db_name,
            user=self.settings.db_user,
            password=self.settings.db_password,
            row_factory=dict_row,
        )

    @contextmanager
    def session(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def cursor(self):
        with self.session() as conn:
            cur = conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def init_schema(self):
        with self.session() as conn:
            cur = conn.cursor()
            cur.execute(SCHEMA_SQL)
            for stmt in MIGRATIONS_SQL:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass
            cur.close()
