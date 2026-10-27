-- Grain test: there cannot be two rows with the same (pump, sensor, instant).
-- It returns rows only if there is an error.
select asset_id, sensor, ts_utc, count(*) as n_rows
from {{ ref('sensor_readings') }}
group by asset_id, sensor, ts_utc
having count(*) > 1
