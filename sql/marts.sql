-- Витрины поверх reports и operations.

-- Операции с классификацией времени.
--   productive — работа по программе;
--   npt        — НПВ: операция из группы interruption (кроме погоды), операция с отметкой
--                state = fail или с отметкой stateDetailActivity, отличной от success
--                (отказ оборудования, операция не выполнена, поглощение, прихват, травма);
--   weather    — простой по метеоусловиям (на шельфе учитывается отдельно).
CREATE OR REPLACE VIEW ops_clean AS
SELECT
    o.*,
    r.hole_in,
    r.rig,
    CASE
        WHEN o.activity_group = 'interruption' AND o.activity = 'waiting on weather' THEN 'weather'
        WHEN o.activity_group = 'interruption' OR o.state = 'fail' OR o.state_detail <> 'success' THEN 'npt'
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
    CASE WHEN min(day_start) < DATE '2000-01-01' THEN 'разведочное бурение' ELSE 'эксплуатационное бурение' END AS scope
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
