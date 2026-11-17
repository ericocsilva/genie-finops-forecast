-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 8 — What-if ao vivo: altere premissas e veja o dashboard mudar (botão Refresh)
SELECT * FROM forecast_assumptions;
SELECT * FROM forecast_scenarios ORDER BY scenario_order;

-- Ex. 1: aplicar o desconto contratual do cliente no SKU SRTI (ex.: 30%)
-- UPDATE forecast_assumptions SET contract_discount_srti = 0.30;

-- Ex. 2: aplicar adicional ESC de 15%
-- UPDATE forecast_assumptions SET addon_uplift = 0.15;

-- Ex. 3: cenário Base com mais adoção (5%/mês) e novos casos de uso (US$/mês, acumulativo após a promoção)
-- UPDATE forecast_scenarios SET human_usage_growth_m = 0.05, new_uc_usd_m = <valor> WHERE scenario = 'Base';

-- Voltar ao padrão
-- Ou rode o job com reset_assumptions=true para restaurar os valores padrão
