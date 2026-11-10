-- Витрины поверх reports и operations.

-- Операции с классификацией времени.
--   productive — работа по программе;
--   npt        — непроизводительное время: операция из группы interruption (кроме погоды)
--                или операция, помеченная в рапорте как неуспешная (state = fail);
--   weather    — ожидание погоды (на шельфе считается отдельно: от подрядчика не зависит).
CREATE OR REPLACE VIEW ops_clean AS
SELECT
    o.*,
    r.hole_in,
    r.rig,
    CASE
        WHEN o.activity_group = 'interruption' AND o.activity = 'waiting on weather' THEN 'weather'
        WHEN o.activity_group = 'interruption' OR o.state = 'fail' THEN 'npt'
        ELSE 'productive'
    END AS time_class
FROM operations o
JOIN reports r USING (report_id)
WHERE o.hours > 0;

-- Паспорт ствола: период, станок, объём данных.
CREATE OR REPLACE TABLE wellbores AS
SELECT
    wellbore,
    any_value(rig)                              AS rig,
    min(day_start)                              AS first_report,
    max(day_end)                                AS last_report,
    count(*)                                    AS reports,
    max(md)                                     AS max_md,
    CASE WHEN min(day_start) < DATE '2000-01-01' THEN 'разведка 1992–1998' ELSE 'разработка 2007–2016' END AS era
FROM reports
GROUP BY wellbore;

-- Баланс времени по стволам.
CREATE OR REPLACE VIEW time_balance AS
SELECT
    wellbore,
    sum(hours)                                             AS hours_total,
    sum(hours) FILTER (WHERE time_class = 'productive')    AS hours_productive,
    sum(hours) FILTER (WHERE time_class = 'npt')           AS hours_npt,
    sum(hours) FILTER (WHERE time_class = 'weather')       AS hours_weather,
    sum(hours) FILTER (WHERE time_class = 'npt') / sum(hours) AS npt_share
FROM ops_clean
GROUP BY wellbore;

-- Причины непроизводительного времени.
CREATE OR REPLACE VIEW npt_causes AS
SELECT
    CASE WHEN activity_group = 'interruption' THEN activity ELSE 'сбой в плановой операции' END AS cause,
    state_detail,
    count(*)    AS operations,
    sum(hours)  AS hours
FROM ops_clean
WHERE time_class = 'npt'
GROUP BY ALL;
