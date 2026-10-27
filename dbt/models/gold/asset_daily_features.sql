-- gold.asset_daily_features: one row per pump and day, with features and the label_failure_7d label.
-- Built in pieces: pivot to one row per instant, daily aggregation, backward windows, label.

with instants as (

    -- Go from "one row per sensor" (long format) to "one row per pump and instant" (wide format).
    -- max(case when ...) is the classic pivot trick: in each group (pump, instant) there is at most ONE reading per
    -- sensor (silver already guarantees the grain), so max() just "picks" that value.
    -- Spikes (is_outlier) are set to NULL instead of being deleted: a 916 kPa spike would ruin the day's maximum,
    -- but the instant's row is kept. Silver flagged them; here gold decides what to do with them.
    -- UNCERTAIN is let in for now (open question: compare the model with and without them, step 5).
    select
        asset_id,
        ts_utc,
        max(case when sensor = 'RUN_STATE' then value end) as run_state,
        max(case when sensor = 'VIB_MM_S' and not is_outlier then value end) as vib,
        max(case when sensor = 'TEMP_BEARING' and not is_outlier then value end) as temp,
        max(case when sensor = 'PRESS_DISCH' and not is_outlier then value end) as press,
        max(case when sensor = 'CURRENT_A' and not is_outlier then value end) as amps
    from {{ ref('sensor_readings') }}
    group by asset_id, ts_utc

),

daily as (

    -- One summary per pump and UTC day. `filter (where run_state = 1)` makes each aggregate look ONLY at the instants
    -- with the pump running: a stopped pump has vibration ~0 and pressure ~2 kPa, and if they entered the average the
    -- feature would measure how long it was stopped, not its health (the case of P115 on July 30th).
    -- A day on which the pump was stopped all day ends with NULL means (no 0 is invented), but the row is kept:
    -- frac_running = 0 is already information.
    -- avg(), max(), stddev_samp() ignore NULLs (spikes and BAD ones), so they need no separate treatment.
    select
        asset_id,
        cast(ts_utc as date) as feature_date,

        avg(vib) filter (where run_state = 1)             as vib_mean,
        max(vib) filter (where run_state = 1)             as vib_max,
        stddev_samp(vib) filter (where run_state = 1)     as vib_std,

        avg(temp) filter (where run_state = 1)            as temp_mean,
        max(temp) filter (where run_state = 1)            as temp_max,

        avg(press) filter (where run_state = 1)           as press_mean,
        min(press) filter (where run_state = 1)           as press_min,       -- pressure FALLS before a failure
        stddev_samp(press) filter (where run_state = 1)   as press_std,       -- cavitation makes it oscillate

        avg(amps) filter (where run_state = 1)            as amps_mean,
        max(amps) filter (where run_state = 1)            as amps_max,

        avg(run_state)                                    as frac_running,    -- share of the day's instants with the pump running
        count(*)                                          as n_readings       -- coverage: 144 instants in a complete day
    from instants
    group by asset_id, cast(ts_utc as date)

),

with_windows as (

    -- Historical context of each day. GOLDEN RULE: every window looks BACKWARDS. There is no `following` here:
    -- day D can only know what happened up to D. (tests/test_no_leakage.py checks it.)
    -- `range ... interval N days` (by date) is used and not `rows ... N` (by number of rows): if a day is missing, "7 days"
    -- are still 7 calendar days and not 7 rows that would cover more time.
    -- There are two different windows:
    --   w7:  the previous 6 days + today      -> recent trend (includes today: it is "how the week is going")
    --   w28: the previous 28 days WITHOUT today -> the pump's own baseline. It excludes today on purpose: if today entered
    --        its own baseline, a sudden rise would drag the baseline up and the difference would shrink.
    -- Differences are only computed if the baseline has at least 7 days with data (with 1 or 2 days it would be noise).
    select
        *,

        avg(vib_mean)  over w7 as vib_mean_7d,
        avg(temp_mean) over w7 as temp_mean_7d,

        case when count(vib_mean) over w28 >= 7
             then vib_mean - avg(vib_mean) over w28 end              as vib_delta_28d,
        case when count(temp_mean) over w28 >= 7
             then temp_mean - avg(temp_mean) over w28 end            as temp_delta_28d,
        case when count(press_mean) over w28 >= 7
             then press_mean - avg(press_mean) over w28 end          as press_delta_28d,
        case when count(amps_mean) over w28 >= 7
             then amps_mean - avg(amps_mean) over w28 end            as amps_delta_28d,

        -- RELATIVE delta: the same change, but as a proportion of the pump's own baseline (0.10 = 10 % above its usual).
        -- A 10 kPa drop weighs differently on a pump that works at 300 kPa than on one at 3000: in absolute kPa
        -- P113 hardly moved; in proportion it did. Same w28 window (backwards, without today): no leakage.
        case when count(vib_mean) over w28 >= 7
             then vib_mean / nullif(avg(vib_mean) over w28, 0) - 1 end                 as vib_delta_rel,
        case when count(press_mean) over w28 >= 7
             then press_mean / nullif(avg(press_mean) over w28, 0) - 1 end             as press_delta_rel,
        case when count(amps_mean) over w28 >= 7
             then amps_mean / nullif(avg(amps_mean) over w28, 0) - 1 end               as amps_delta_rel
    from daily
    window
        w7  as (partition by asset_id order by feature_date
                range between interval 6 days preceding and current row),
        w28 as (partition by asset_id order by feature_date
                range between interval 28 days preceding and interval 1 day preceding)

),

failures as (

    -- A "failure" is a CORRECTIVE order (repairing something that already failed; preventive ones are planned maintenance).
    -- silver already normalized wo_type to upper case, otherwise 'Corrective'/'corrective' would be lost here.
    -- The DAY the order was opened is used, which is when the failure became visible to maintenance.
    select distinct
        asset_id,
        cast(opened_at as date) as failure_date
    from {{ ref('work_orders') }}
    where wo_type = 'CORRECTIVE'

),

bounds as (

    -- Last day with data. For the final 7 days the future has not happened yet: we do not know whether there will be a failure.
    select max(feature_date) as last_day from daily

),

with_label as (

    -- label_failure_7d = 1 if there is a failure between the NEXT day and 7 days later (D+1 .. D+7).
    -- It excludes the same day D: that day the failure has already happened and there is nothing to anticipate (`>` and not `>=`).
    -- The label is the ONLY thing in this table that looks into the future, and it must: it is the answer the model learns.
    -- For feature_date > last_day - 7 the label is NULL (not 0): "I do not know yet" is not "it did not fail".
    -- Those rows are kept because they are the ones scored "today" in production.
    -- `exists` is used (not a join) so that two failures in the same window do not duplicate the row.
    select
        v.*,
        case
            when v.feature_date > b.last_day - 7 then null
            when exists (
                select 1
                from failures f
                where f.asset_id = v.asset_id
                  and f.failure_date >  v.feature_date
                  and f.failure_date <= v.feature_date + 7
            ) then 1
            else 0
        end as label_failure_7d
    from with_windows v
    cross join bounds b

)

select * from with_label
