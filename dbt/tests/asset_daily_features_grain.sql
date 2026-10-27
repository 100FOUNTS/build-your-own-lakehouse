-- Grain test of gold: there cannot be two rows with the same (pump, day).
-- It returns rows only if there is an error.
select asset_id, feature_date, count(*) as n_rows
from {{ ref('asset_daily_features') }}
group by asset_id, feature_date
having count(*) > 1
