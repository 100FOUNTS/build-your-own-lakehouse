-- silver.work_orders: one row per work order, with the right types.
-- wo_type arrives written in six ways (CORRECTIVE, Corrective, corrective...): it is normalized to three. Otherwise a
-- "wo_type = 'CORRECTIVE'" filter would lose 8 of the 30 failures, which are the label the model must learn.
select
    wo_id,
    asset_id,
    upper(trim(wo_type)) as wo_type,
    -- The dates arrive as text with "Z" (UTC): timestamptz understands them and they are written as UTC time with no zone.
    cast(cast(opened_at as timestamptz) at time zone 'UTC' as timestamp) as opened_at,
    cast(cast(closed_at as timestamptz) at time zone 'UTC' as timestamp) as closed_at,
    nullif(trim(failure_mode), '') as failure_mode,
    cast(cost_usd as double) as cost_usd,
    cast(downtime_hours as double) as downtime_hours,
    description
from read_parquet('{{ env_var("LH_BRONZE_DIR", "data/bronze") }}/work_orders/*.parquet')
