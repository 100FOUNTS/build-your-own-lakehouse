-- silver.sensor_readings: one reading of one sensor of one pump at one UTC instant.
-- Built in pieces, one CTE per problem found in step 1.

with base as (

    -- Identifiers and time. Everything else passes as is from bronze (all text).
    select
        -- "PLT01.P111.RUN_STATE" -> asset_id "PLT01-P111" (as in assets.csv) and sensor "RUN_STATE"
        split_part(tag, '.', 1) || '-' || split_part(tag, '.', 2) as asset_id,
        split_part(tag, '.', 3) as sensor,

        -- The text arrives with "-05:00" (until August 3rd) or with "Z" (from the 4th). timestamptz understands both
        -- and stores an absolute instant; "at time zone 'UTC'" writes it as UTC time with no zone.
        cast(cast("timestamp" as timestamptz) at time zone 'UTC' as timestamp) as ts_utc,

        value,
        unit,
        quality,
        _source_file
    from read_parquet('{{ env_var("LH_BRONZE_DIR", "data/bronze") }}/readings/**/*.parquet')

),

cleaned as (

    -- Quality normalized and value as a number. try_cast returns NULL if the text is not a number (empties already
    -- arrive as NULL); nullif turns the -9999 sentinel into NULL. This goes BEFORE converting units: otherwise
    -- -9999 °F would turn into another number that is no longer recognized as a sentinel.
    select
        asset_id,
        sensor,
        ts_utc,
        nullif(try_cast(value as double), -9999) as value,
        unit,
        upper(trim(quality)) as quality,
        _source_file
    from base

),

without_bad as (

    -- "The system itself says these are not measurements": out with the BAD ones and those left without a value.
    -- (Today they are exactly the same rows; both conditions are asked for safety.)
    -- UNCERTAIN is KEPT with its quality: flag, do not destroy; gold will decide whether to use them.
    select *
    from cleaned
    where quality <> 'BAD'
      and value is not null

),

standard_units as (

    -- Conversion according to the `unit` column (not according to the sensor or the pump), to the standard unit of each sensor.
    select
        asset_id,
        sensor,
        ts_utc,
        case unit
            when 'degF' then (value - 32) * 5.0 / 9.0   -- °F -> °C
            when 'bar'  then value * 100.0              -- bar -> kPa
            else value
        end as value,
        case unit
            when 'degF' then 'degC'
            when 'bar'  then 'kPa'
            else unit
        end as unit,
        quality,
        _source_file
    from without_bad

),

deduplicated as (

    -- One single row per reading. The key is the INSTANT (ts_utc, already converted) and not the text of the time:
    -- so the same reading written with "-05:00" in one file and with "Z" in another, or repeated in the next day's
    -- file, counts as the same. It goes AFTER removing BAD: if it went before, we might keep a BAD copy and lose the good one.
    -- Among copies: first the GOOD one (more trustworthy than UNCERTAIN) and, if tied, the one from the file that sorts
    -- first, so the result is always the same (deterministic). Today the copies are identical.
    select *
    from standard_units
    qualify row_number() over (
        partition by asset_id, sensor, ts_utc
        order by case quality when 'GOOD' then 0 else 1 end, _source_file
    ) = 1

),

with_neighbors as (

    -- Spurious spikes (GOOD quality but absurd relative to their neighborhood). They are FLAGGED, not deleted: maybe
    -- tomorrow it turns out to be a real failure. For each reading we compute:
    --   median_dev:  how far it is from the median of its 7 surrounding readings (3 before, itself, 3 after) of the
    --                same pump and sensor. The median ignores an isolated spike, unlike the mean.
    --   d_prev / d_next: how far it is from the previous and the next reading.
    select
        *,
        abs(value - median(value) over (
            partition by asset_id, sensor order by ts_utc rows between 3 preceding and 3 following
        )) as median_dev,
        abs(value - lag(value)  over (partition by asset_id, sensor order by ts_utc)) as d_prev,
        abs(value - lead(value) over (partition by asset_id, sensor order by ts_utc)) as d_next
    from deduplicated

),

flagged_spikes as (

    -- A spike is a reading that is MUCH further from its neighborhood and also from its previous and next readings
    -- (it is isolated). The isolation condition is key: when a pump stops or starts, the value jumps and stays at
    -- the new level; that is a real regime change, not a spike, and must not be flagged.
    -- Thresholds depend on the sensor (mm/s is not kPa) and come from the data: between these values the number of
    -- isolated spikes does not change (a plateau), so they are not fragile. RUN_STATE (0/1) has no spikes.
    select
        asset_id,
        ts_utc,
        sensor,
        value,
        unit,
        coalesce(
            sensor <> 'RUN_STATE'
            and median_dev > threshold
            and d_prev > threshold
            and d_next > threshold,
            false
        ) as is_outlier,
        quality,
        _source_file
    from (
        select
            *,
            case sensor
                when 'VIB_MM_S'     then 3     -- mm/s
                when 'TEMP_BEARING' then 10    -- °C
                when 'PRESS_DISCH'  then 75    -- kPa (noisy sensor: the median deviation is ~1.6)
                when 'CURRENT_A'    then 10    -- A
            end as threshold
        from with_neighbors
    )

)

select * from flagged_spikes
