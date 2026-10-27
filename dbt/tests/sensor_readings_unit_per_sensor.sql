-- Each sensor must come in its standard unit. If a new sensor arrives tomorrow, or a unit we do not know
-- (another pump that switches to °F, for example), this test fails and warns instead of silently mixing scales.
select sensor, unit, count(*) as n_rows
from {{ ref('sensor_readings') }}
where (sensor, unit) not in (
    ('VIB_MM_S', 'mm/s'), ('TEMP_BEARING', 'degC'), ('PRESS_DISCH', 'kPa'), ('CURRENT_A', 'A'), ('RUN_STATE', 'bool')
)
group by sensor, unit
