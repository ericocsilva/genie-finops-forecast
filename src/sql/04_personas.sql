-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 4 — Percentis de DBUs por usuário humano (base para definir faixas de persona e limites de budget)
WITH per_user_month AS (
  SELECT DATE_TRUNC('MONTH', usage_date) AS month,
         identity_metadata.run_as        AS run_as,
         SUM(CASE WHEN sku_name <> 'GENIE_FREE_USAGE' THEN usage_quantity / 0.75 ELSE usage_quantity END) AS dbus
  FROM system.billing.usage
  WHERE billing_origin_product = 'GENIE'
    AND identity_metadata.run_as LIKE '%@%'
    AND usage_date >= '2026-08-01'
    AND usage_date <  DATE_TRUNC('MONTH', CURRENT_DATE)
  GROUP BY ALL
)
SELECT month,
       COUNT(*)                              AS active_users,
       PERCENTILE_APPROX(dbus, 0.50)         AS p50_dbus,
       PERCENTILE_APPROX(dbus, 0.75)         AS p75_dbus,
       PERCENTILE_APPROX(dbus, 0.90)         AS p90_dbus,
       PERCENTILE_APPROX(dbus, 0.99)         AS p99_dbus,
       MAX(dbus)                             AS max_dbus,
       COUNT_IF(dbus <= 150)                 AS users_within_free,
       COUNT_IF(dbus >  150 AND dbus <= 450) AS users_150_450,
       COUNT_IF(dbus >  450)                 AS users_above_450
FROM per_user_month
GROUP BY month
ORDER BY month;

-- Passo 4b — Top 20 identidades (humanos e SPs) do último mês completo
SELECT identity_metadata.run_as AS run_as,
       ROUND(SUM(CASE WHEN sku_name <> 'GENIE_FREE_USAGE' THEN usage_quantity / 0.75 ELSE usage_quantity END), 1) AS dbus
FROM system.billing.usage
WHERE billing_origin_product = 'GENIE'
  AND usage_date >= add_months(DATE_TRUNC('MONTH', CURRENT_DATE), -1)
  AND usage_date <  DATE_TRUNC('MONTH', CURRENT_DATE)
GROUP BY 1 ORDER BY dbus DESC LIMIT 20;
