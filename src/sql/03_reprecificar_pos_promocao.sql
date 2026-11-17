-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 3 — Simula cada mês como se as regras de fev/2027 já valessem
-- Regras: humanos = max(0, DBUs de todas as superfícies − 150); SPs = 100%; DBUs cobrados hoje ÷ 0,75 (remove a promoção)
-- Defina o parâmetro :p_net_usd_per_dbu com o preço líquido retornado no Passo 1.3 (srti_net_price_with_addon)
WITH per_identity_month AS (
  SELECT
    DATE_TRUNC('MONTH', usage_date)           AS month,
    identity_metadata.run_as                  AS run_as,
    CASE WHEN identity_metadata.run_as LIKE '%@%'
         THEN 'HUMAN' ELSE 'SERVICE_PRINCIPAL' END AS identity_type,
    SUM(CASE WHEN sku_name <> 'GENIE_FREE_USAGE'
             THEN usage_quantity / 0.75
             ELSE usage_quantity END)         AS full_rate_dbus
  FROM system.billing.usage
  WHERE billing_origin_product = 'GENIE'
    AND usage_date >= '2026-08-01'
    AND usage_date <  DATE_TRUNC('MONTH', CURRENT_DATE)
  GROUP BY ALL
)
SELECT
  month, identity_type,
  COUNT(*)                                                     AS identities,
  ROUND(SUM(full_rate_dbus), 1)                                AS gross_dbus,
  ROUND(SUM(CASE WHEN identity_type = 'HUMAN'
                 THEN GREATEST(full_rate_dbus - 150, 0)
                 ELSE full_rate_dbus END), 1)                  AS billable_dbus_post_promo,
  ROUND(SUM(CASE WHEN identity_type = 'HUMAN'
                 THEN GREATEST(full_rate_dbus - 150, 0)
                 ELSE full_rate_dbus END) * :p_net_usd_per_dbu, 2) AS est_llm_cost_usd,
  COUNT_IF(identity_type = 'HUMAN' AND full_rate_dbus > 150)   AS humans_above_allowance
FROM per_identity_month
GROUP BY ALL
ORDER BY month, identity_type;
