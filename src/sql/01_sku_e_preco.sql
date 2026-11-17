-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 1.1 — Em quais SKUs SRTI o Genie já é faturado?
SELECT DISTINCT cloud, sku_name
FROM system.billing.usage
WHERE billing_origin_product = 'GENIE'
  AND sku_name <> 'GENIE_FREE_USAGE';

-- Passo 1.2 — Preço de lista atual (US$/DBU)
SELECT cloud, sku_name, currency_code, usage_unit,
       pricing.effective_list.default AS list_price_per_dbu, price_start_time
FROM system.billing.list_prices
WHERE sku_name LIKE '%SERVERLESS_REAL_TIME_INFERENCE%'
  AND price_end_time IS NULL
ORDER BY sku_name;

-- Passo 1.3 — Preço líquido usado na previsão (lista × (1 − desconto) × (1 + adicional))
SELECT srti_sku, srti_list_price, contract_discount_srti, addon_uplift, srti_net_price_with_addon FROM v_price;
