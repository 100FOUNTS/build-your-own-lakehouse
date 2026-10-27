-- Right-censoring test: the label must be NULL in the last 7 days of data and NOT null before.
-- (accepted_values lets NULLs through, so nobody else watches this.)
-- It returns rows only if there is an error.
with bounds as (
    select max(feature_date) as last_day from {{ ref('asset_daily_features') }}
)

select g.asset_id, g.feature_date, g.label_failure_7d
from {{ ref('asset_daily_features') }} g
cross join bounds b
where (g.feature_date >  b.last_day - 7 and g.label_failure_7d is not null)   -- the future does not exist: it should be NULL
   or (g.feature_date <= b.last_day - 7 and g.label_failure_7d is null)       -- the future already happened: it should be 0 or 1
