-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 2 — DBUs mensais de LLM do Genie por superfície, humano vs service principal, gratuito vs cobrado
SELECT
  DATE_TRUNC('MONTH', usage_date)                                   AS month,
  usage_metadata.genie.surface                                      AS surface,
  usage_metadata.genie.channel                                      AS channel,
  CASE WHEN identity_metadata.run_as LIKE '%@%'
       THEN 'HUMAN' ELSE 'SERVICE_PRINCIPAL' END                    AS identity_type,
  COUNT(DISTINCT identity_metadata.run_as)                          AS identities,
  SUM(CASE WHEN sku_name =  'GENIE_FREE_USAGE' THEN usage_quantity ELSE 0 END) AS free_dbus,
  SUM(CASE WHEN sku_name <> 'GENIE_FREE_USAGE' THEN usage_quantity ELSE 0 END) AS billed_dbus
FROM system.billing.usage
WHERE billing_origin_product = 'GENIE'
  AND usage_date >= '2026-08-01'
GROUP BY ALL
ORDER BY month, surface, identity_type;
