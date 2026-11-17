-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 0 — Conhecer as fontes: o Genie já mede tudo (inclusive o uso gratuito) desde 20/07/2026
SELECT billing_origin_product, sku_name, usage_metadata.genie.surface AS surface,
       COUNT(*) AS linhas, MIN(usage_date) AS de, MAX(usage_date) AS ate, ROUND(SUM(usage_quantity), 1) AS dbus
FROM system.billing.usage
WHERE usage_date >= '2026-07-20'
  AND (billing_origin_product = 'GENIE' OR sku_name = 'GENIE_FREE_USAGE')
GROUP BY ALL
ORDER BY billing_origin_product, surface, sku_name;
