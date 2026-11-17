-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 5 — Rateio do custo dos SQL warehouses para o Genie pelo tempo de task (query_source.genie_space_id)
WITH q AS (
  SELECT DATE_TRUNC('MONTH', start_time)                    AS month,
         compute.warehouse_id                               AS warehouse_id,
         SUM(CASE WHEN query_source.genie_space_id IS NOT NULL
                  THEN total_task_duration_ms ELSE 0 END)   AS genie_task_ms,
         SUM(total_task_duration_ms)                        AS all_task_ms,
         COUNT_IF(query_source.genie_space_id IS NOT NULL)  AS genie_queries
  FROM system.query.history
  WHERE start_time >= '2026-08-01'
    AND compute.warehouse_id IS NOT NULL
  GROUP BY ALL
),
wh_cost AS (
  SELECT DATE_TRUNC('MONTH', u.usage_date)        AS month,
         u.usage_metadata.warehouse_id            AS warehouse_id,
         SUM(u.usage_quantity * lp.pricing.effective_list.default) AS list_cost_usd
  FROM system.billing.usage u
  JOIN system.billing.list_prices lp
    ON  u.sku_name = lp.sku_name
    AND u.usage_end_time >= lp.price_start_time
    AND (lp.price_end_time IS NULL OR u.usage_end_time < lp.price_end_time)
  WHERE u.usage_metadata.warehouse_id IS NOT NULL
    AND u.usage_date >= '2026-08-01'
  GROUP BY ALL
)
SELECT q.month, q.warehouse_id, q.genie_queries,
       ROUND(q.genie_task_ms / NULLIF(q.all_task_ms, 0), 3)                   AS genie_share,
       ROUND(w.list_cost_usd, 2)                                              AS warehouse_list_cost_usd,
       ROUND(w.list_cost_usd * q.genie_task_ms / NULLIF(q.all_task_ms, 0), 2) AS genie_attributed_cost_usd
FROM q JOIN wh_cost w USING (month, warehouse_id)
WHERE q.genie_queries > 0
ORDER BY q.month, genie_attributed_cost_usd DESC;
