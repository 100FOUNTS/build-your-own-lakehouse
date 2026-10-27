-- silver.assets: one row per pump, with the right types (bronze stores everything as text).
select
    asset_id,
    plant,
    model,
    cast(install_date as date) as install_date,
    criticality,
    cast(rated_flow_m3h as double) as rated_flow_m3h,
    cast(rated_kw as double) as rated_kw
from read_parquet('{{ env_var("LH_BRONZE_DIR", "data/bronze") }}/assets/*.parquet')
