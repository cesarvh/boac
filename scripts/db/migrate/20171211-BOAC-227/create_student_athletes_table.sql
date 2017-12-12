BEGIN;

CREATE TABLE athletics (
  group_code VARCHAR(80) PRIMARY KEY,
  group_name VARCHAR(255) NOT NULL,
  team_code VARCHAR(80) NOT NULL,
  team_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE students (
  sid VARCHAR(80) PRIMARY KEY,
  uid VARCHAR(80),
  first_name VARCHAR(255) NOT NULL,
  last_name VARCHAR(255) NOT NULL,
  in_intensive_cohort BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE student_athletes (
  group_code VARCHAR(80) NOT NULL REFERENCES athletics (group_code) ON DELETE CASCADE,
  sid VARCHAR(80) NOT NULL REFERENCES students (sid) ON DELETE CASCADE,

  PRIMARY KEY (group_code, sid)
);

COMMIT;
