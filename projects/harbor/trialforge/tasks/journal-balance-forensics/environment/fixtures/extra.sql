-- journal-balance-forensics fixture.
-- Creates ONE NEW table. It does not read, alter or drop any of the eight
-- tables baked into the base image, which are shared with other tasks.
-- Column types follow the baked convention: TEXT unless every value parses
-- as INTEGER or REAL.
CREATE TABLE IF NOT EXISTS gl_period_close (
  period     TEXT,
  close_date TEXT,
  status     TEXT,
  closed_by  TEXT
);
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-01', '2024-02-06', 'CLOSED', 'm.okafor');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-02', '2024-03-07', 'CLOSED', 'm.okafor');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-03', '2024-04-05', 'CLOSED', 'm.okafor');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-04', '2024-05-08', 'CLOSED', 'm.okafor');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-05', '2024-06-07', 'CLOSED', 'd.vasquez');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-06', '2024-07-05', 'CLOSED', 'd.vasquez');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-07', '2024-08-06', 'CLOSED', 'd.vasquez');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-08', '', 'ADJUSTING', 'd.vasquez');
INSERT INTO gl_period_close (period, close_date, status, closed_by) VALUES ('2024-09', '', 'OPEN', '');
