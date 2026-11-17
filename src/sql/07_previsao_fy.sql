-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 7 — Previsão do ano fiscal por cenário
-- Base da previsão (último mês completo)
SELECT * FROM v_forecast_baseline;

-- Totais por cenário
SELECT scenario, ROUND(SUM(human_llm_usd)) AS llm_humanos, ROUND(SUM(sp_llm_usd)) AS llm_sps,
       ROUND(SUM(genie_warehouse_usd)) AS warehouse, ROUND(SUM(new_use_cases_usd)) AS novos_ucs,
       ROUND(SUM(total_usd)) AS total, ROUND(SUM(total_with_headroom_usd)) AS total_com_margem
FROM v_fy_forecast_total GROUP BY scenario ORDER BY MIN(scenario_order);

-- Série mensal (preenche o Apêndice A do guia)
SELECT * FROM v_fy_forecast_total WHERE scenario = 'Base' ORDER BY month;

-- Tendência indicativa com ai_forecast (histórico curto: use apenas como referência)
SELECT * FROM ai_forecast(
  TABLE(SELECT month, total_post_promo_usd FROM v_monthly_cost_components WHERE is_complete_month AND month >= '2026-08-01'),
  horizon => '2027-12-01', time_col => 'month', value_col => 'total_post_promo_usd');
