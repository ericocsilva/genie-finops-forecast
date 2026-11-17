# Databricks notebook source
# MAGIC %md
# MAGIC # Genie FinOps — build views over the system tables
# MAGIC
# MAGIC Creates views and small **monthly aggregates** derived only from the Databricks system tables (no data is generated), and two small
# MAGIC **assumption tables** that hold the forecast inputs (contract discount, uplift, headroom, scenario growth rates).
# MAGIC
# MAGIC | Layer | Objects |
# MAGIC |---|---|
# MAGIC | 1 — source views (filtered by account/workspace) | `src_billing_usage`, `src_list_prices`, `src_query_history`, `src_audit`, `dim_warehouses`, `dim_workspaces`, `dim_genie_agents` |
# MAGIC | 2 — forecast inputs (editable) | `forecast_assumptions`, `forecast_scenarios` |
# MAGIC | monthly aggregates refreshed by the job (daily) | `agg_genie_usage_monthly`, `agg_srti_skus` (billing), `agg_genie_warehouse_monthly` (query history + billing), `agg_genie_questions_monthly` (audit), `dim_genie_agents` |
# MAGIC | 3 — analytical views (guide steps 1–7) | `v_price`, `v_monthly_baseline`, `v_identity_month`, `v_post_promo_simulation`, `v_user_persona_month`, `v_persona_stats`, `v_warehouse_cost_month`, `v_warehouse_attribution`, `v_agent_activity`, `v_unit_costs`, `v_monthly_cost_components`, `v_forecast_baseline`, `v_fy_forecast`, `v_fy_forecast_total` |
# MAGIC
# MAGIC Source table names are parameters, so the same notebook works on `system.*` in a customer workspace or on
# MAGIC equivalent copies of system tables (e.g. a central analytics environment) filtered by `account_id`.

# COMMAND ----------

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "genie_finops")
dbutils.widgets.text("history_start", "2026-07-20")
dbutils.widgets.text("account_id", "")        # optional: filter one account (needed when the source holds many accounts)
dbutils.widgets.text("workspace_ids", "")     # optional: comma-separated workspace IDs; empty = all workspaces
dbutils.widgets.text("billing_usage_table", "system.billing.usage")
dbutils.widgets.text("list_prices_table", "system.billing.list_prices")
dbutils.widgets.text("query_history_table", "system.query.history")
dbutils.widgets.text("audit_table", "system.access.audit")
dbutils.widgets.text("warehouses_table", "system.compute.warehouses")
dbutils.widgets.text("workspaces_table", "system.access.workspaces_latest")
dbutils.widgets.dropdown("reset_assumptions", "false", ["false", "true"])

w = {k: dbutils.widgets.get(k).strip() for k in [
    "catalog", "schema", "history_start", "account_id", "workspace_ids", "billing_usage_table", "list_prices_table",
    "query_history_table", "audit_table", "warehouses_table", "workspaces_table", "reset_assumptions"]}
assert w["catalog"] and w["schema"], "catalog and schema are required"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{w['catalog']}`.`{w['schema']}` COMMENT 'Genie FinOps & forecast — views over system tables'")
spark.sql(f"USE `{w['catalog']}`.`{w['schema']}`")

ws_list = [x.strip() for x in w["workspace_ids"].split(",") if x.strip()]
ws_pred = "TRUE" if not ws_list else "CAST(workspace_id AS STRING) IN (" + ",".join(f"'{x}'" for x in ws_list) + ")"
acct_pred = "TRUE" if not w["account_id"] else f"account_id = '{w['account_id']}'"
FILTER = f"({acct_pred}) AND ({ws_pred})"
print("Row filter:", FILTER)


def run(sql: str):
    spark.sql(sql)
    print("✓", sql.strip().splitlines()[0][:110])


# COMMAND ----------

# MAGIC %md ## Layer 1 — source views (system tables, filtered)

# COMMAND ----------

run(f"""CREATE OR REPLACE VIEW src_billing_usage COMMENT 'Source: {w['billing_usage_table']} (Genie + SQL warehouse rows)' AS
SELECT account_id, CAST(workspace_id AS STRING) AS workspace_id, cloud, sku_name, usage_date, usage_start_time, usage_end_time,
       usage_quantity, billing_origin_product, identity_metadata, usage_metadata
FROM {w['billing_usage_table']}
WHERE usage_date >= '{w['history_start']}'
  AND (billing_origin_product = 'GENIE' OR usage_metadata.warehouse_id IS NOT NULL
       OR sku_name LIKE '%SERVERLESS_REAL_TIME_INFERENCE%')
  AND {FILTER}""")

run(f"""CREATE OR REPLACE VIEW src_list_prices COMMENT 'Source: {w['list_prices_table']}' AS
SELECT * FROM {w['list_prices_table']} WHERE {acct_pred}""")

run(f"""CREATE OR REPLACE VIEW src_query_history COMMENT 'Source: {w['query_history_table']} (warehouse queries)' AS
SELECT account_id, CAST(workspace_id AS STRING) AS workspace_id, statement_id, executed_by, execution_status,
       compute, query_source, client_application, start_time, end_time, total_duration_ms, total_task_duration_ms
FROM {w['query_history_table']}
WHERE start_time >= '{w['history_start']}' AND compute.warehouse_id IS NOT NULL AND {FILTER}""")

run(f"""CREATE OR REPLACE VIEW src_audit COMMENT 'Source: {w['audit_table']} (Genie services)' AS
SELECT account_id, CAST(workspace_id AS STRING) AS workspace_id, event_time, event_date, service_name, action_name,
       user_identity, request_params, response
FROM {w['audit_table']}
WHERE event_date >= '{w['history_start']}' AND service_name IN ('aibiGenie', 'genieChat') AND {FILTER}""")

run(f"""CREATE OR REPLACE VIEW dim_warehouses AS
SELECT warehouse_id, max_by(warehouse_name, change_time) AS warehouse_name
FROM {w['warehouses_table']} WHERE {FILTER} GROUP BY warehouse_id""")

run(f"""CREATE OR REPLACE VIEW dim_workspaces AS
SELECT CAST(workspace_id AS STRING) AS workspace_id, workspace_name
FROM {w['workspaces_table']} WHERE {acct_pred}""")

# Genie Agent (space) names are not in the system tables: label = workspace name + short space id
spark.sql("DROP VIEW IF EXISTS dim_genie_agents")
run("""CREATE OR REPLACE TABLE dim_genie_agents COMMENT 'Genie Agents vistos em system.query.history (nome = workspace + id)' AS
SELECT q.genie_space_id,
       concat(COALESCE(ws.workspace_name, q.workspace_id), ' / ', left(q.genie_space_id, 12)) AS agent_name,
       q.workspace_id, q.warehouse_id
FROM (
  SELECT query_source.genie_space_id AS genie_space_id,
         max_by(workspace_id, start_time) AS workspace_id,
         max_by(compute.warehouse_id, start_time) AS warehouse_id
  FROM src_query_history WHERE query_source.genie_space_id IS NOT NULL GROUP BY 1
) q LEFT JOIN dim_workspaces ws ON ws.workspace_id = q.workspace_id""")

# COMMAND ----------

# MAGIC %md ## Layer 2 — forecast inputs (editable; created only if missing)

# COMMAND ----------

if w["reset_assumptions"] == "true":
    spark.sql("DROP TABLE IF EXISTS forecast_assumptions")
    spark.sql("DROP TABLE IF EXISTS forecast_scenarios")

run("""CREATE TABLE IF NOT EXISTS forecast_assumptions (
  contract_discount_srti DOUBLE COMMENT 'Desconto contratual no SKU Serverless Real-Time Inference (0-1). Padrão 0 = preço de lista',
  contract_discount_sql  DOUBLE COMMENT 'Desconto contratual no SKU de SQL warehouse (0-1). Padrão 0 = preço de lista',
  addon_uplift           DOUBLE COMMENT 'Adicional de plataforma (ex.: ESC) sobre $DBUs (0-1)',
  headroom               DOUBLE COMMENT 'Margem de segurança da previsão (0-1)',
  free_allowance_dbus    DOUBLE COMMENT 'Franquia gratuita por usuário/mês (todas as superfícies Genie) — documentação pública',
  promo_factor           DOUBLE COMMENT 'Fator do desconto promocional aplicado na medição (0.75 = 25% off) — documentação pública',
  promo_end_date         DATE   COMMENT 'Último dia da promoção — documentação pública',
  fy_start               DATE   COMMENT 'Primeiro mês do ano fiscal a projetar'
) COMMENT 'Entradas da previsão (não são dados de uso). Edite com UPDATE.'""")
if spark.table("forecast_assumptions").count() == 0:
    run("INSERT INTO forecast_assumptions VALUES (0.0, 0.0, 0.0, 0.15, 150.0, 0.75, DATE'2027-01-31', DATE'2027-01-01')")

run("""CREATE TABLE IF NOT EXISTS forecast_scenarios (
  scenario STRING, scenario_order INT,
  human_usage_growth_m DOUBLE COMMENT 'Crescimento mensal do consumo cobrável de humanos',
  sp_growth_m          DOUBLE COMMENT 'Crescimento mensal do consumo de service principals',
  warehouse_growth_m   DOUBLE COMMENT 'Crescimento mensal do custo de warehouse atribuído ao Genie',
  new_uc_usd_m         DOUBLE COMMENT 'Novos casos de uso: US$ adicionados por mês após o fim da promoção (acumulativo)',
  description STRING
) COMMENT 'Cenários da previsão (entradas). Edite com UPDATE.'""")
if spark.table("forecast_scenarios").count() == 0:
    run("""INSERT INTO forecast_scenarios VALUES
      ('Conservador', 1, 0.00, 0.00, 0.00, 0.0, 'Mantém o run-rate atual'),
      ('Base',        2, 0.03, 0.05, 0.03, 0.0, 'Ajuste com o plano de expansão das áreas'),
      ('Agressivo',   3, 0.06, 0.10, 0.06, 0.0, 'Ajuste com a população-alvo completa e todas as apps em produção')""")

# COMMAND ----------

# MAGIC %md ## Layer 3 — analytical views (guide steps 1–7)

# COMMAND ----------

# Monthly aggregates of the system tables (refreshed by this job). Live views on billing/query history are too slow to
# drive an interactive dashboard on large accounts; prices, discounts and forecasts stay as live views on top of these.
run("""CREATE OR REPLACE TABLE agg_srti_skus COMMENT 'SKUs SRTI usados na conta (de system.billing.usage)' AS
SELECT sku_name, cloud, billing_origin_product = 'GENIE' AND sku_name <> 'GENIE_FREE_USAGE' AS billed_by_genie,
       MAX(usage_date) AS last_usage_date
FROM src_billing_usage
WHERE sku_name LIKE '%SERVERLESS_REAL_TIME_INFERENCE%'
GROUP BY ALL""")

run("""CREATE OR REPLACE TABLE agg_genie_usage_monthly COMMENT 'DBUs Genie por mês/identidade/superfície (de system.billing.usage)' AS
SELECT DATE_TRUNC('MONTH', u.usage_date) AS month, u.workspace_id,
       u.identity_metadata.run_as AS run_as,
       CASE WHEN u.identity_metadata.run_as LIKE '%@%' THEN 'HUMANO' ELSE 'SERVICE_PRINCIPAL' END AS identity_type,
       u.usage_metadata.genie.surface AS surface, u.usage_metadata.genie.channel AS channel, u.sku_name,
       u.sku_name = 'GENIE_FREE_USAGE' AS is_free,
       SUM(CAST(u.usage_quantity AS DOUBLE)) AS recorded_dbus,
       SUM(CASE WHEN u.sku_name <> 'GENIE_FREE_USAGE' AND u.usage_date <= a.promo_end_date
                THEN CAST(u.usage_quantity AS DOUBLE) / a.promo_factor
                ELSE CAST(u.usage_quantity AS DOUBLE) END) AS full_rate_dbus,
       COUNT(DISTINCT u.usage_date) AS active_days
FROM src_billing_usage u CROSS JOIN (SELECT * FROM forecast_assumptions LIMIT 1) a
WHERE u.billing_origin_product = 'GENIE'
GROUP BY ALL""")

run("""CREATE OR REPLACE TABLE agg_genie_warehouse_monthly
COMMENT 'Queries/tempo de task por mês, warehouse e Genie Agent + custo de lista do warehouse (de system.query.history e system.billing.*)' AS
WITH q AS (
  SELECT DATE_TRUNC('MONTH', start_time) AS month, compute.warehouse_id AS warehouse_id,
         query_source.genie_space_id AS genie_space_id,
         SUM(total_task_duration_ms) AS task_ms, COUNT(*) AS queries
  FROM src_query_history GROUP BY ALL
),
genie_wh AS (SELECT DISTINCT month, warehouse_id FROM q WHERE genie_space_id IS NOT NULL),
tot AS (SELECT q.month, q.warehouse_id, SUM(q.task_ms) AS all_task_ms FROM q JOIN genie_wh USING (month, warehouse_id) GROUP BY ALL),
cost AS (
  SELECT DATE_TRUNC('MONTH', u.usage_date) AS month, u.usage_metadata.warehouse_id AS warehouse_id,
         SUM(CAST(u.usage_quantity AS DOUBLE) * CAST(lp.pricing.effective_list.default AS DOUBLE)) AS warehouse_list_cost_usd
  FROM src_billing_usage u
  JOIN src_list_prices lp
    ON u.sku_name = lp.sku_name AND u.cloud = lp.cloud
   AND u.usage_end_time >= lp.price_start_time
   AND (lp.price_end_time IS NULL OR u.usage_end_time < lp.price_end_time)
  WHERE u.usage_metadata.warehouse_id IS NOT NULL
  GROUP BY ALL
)
SELECT q.month, q.warehouse_id, q.genie_space_id, q.queries, q.task_ms, tot.all_task_ms, cost.warehouse_list_cost_usd
FROM q JOIN tot USING (month, warehouse_id) LEFT JOIN cost USING (month, warehouse_id)""")

# Step 1 — SKU & unit price (from list prices only; no hard-coded rates)
run("""CREATE OR REPLACE VIEW v_price COMMENT 'Passo 1: SKU SRTI usado pelo Genie e preço (lista e líquido)' AS
WITH a AS (SELECT * FROM forecast_assumptions LIMIT 1),
genie_sku AS (
  SELECT max_by(sku_name, last_usage_date) AS sku, max_by(cloud, last_usage_date) AS cloud FROM agg_srti_skus WHERE billed_by_genie
),
any_srti AS (   -- fallback: SRTI SKU of the same account/region used by other AI products
  SELECT max_by(sku_name, last_usage_date) AS sku, max_by(cloud, last_usage_date) AS cloud FROM agg_srti_skus
),
sku AS (SELECT COALESCE(g.sku, s.sku) AS srti_sku, COALESCE(g.cloud, s.cloud) AS cloud,
               CASE WHEN g.sku IS NOT NULL THEN 'Faturado pelo Genie' WHEN s.sku IS NOT NULL THEN 'Outro produto SRTI da conta' END AS sku_source
        FROM genie_sku g CROSS JOIN any_srti s),
lp AS (
  SELECT sku_name, cloud, max_by(CAST(pricing.effective_list.default AS DOUBLE), price_start_time) AS list_price
  FROM src_list_prices WHERE price_end_time IS NULL GROUP BY sku_name, cloud
)
SELECT sku.srti_sku, sku.sku_source, lp.list_price AS srti_list_price,
       lp.list_price * (1 - a.contract_discount_srti)                       AS srti_net_price,
       lp.list_price * (1 - a.contract_discount_srti) * (1 + a.addon_uplift) AS srti_net_price_with_addon,
       a.*
FROM a CROSS JOIN sku LEFT JOIN lp ON lp.sku_name = sku.srti_sku AND lp.cloud = sku.cloud""")

run("""CREATE OR REPLACE VIEW v_genie_usage_normalized COMMENT 'DBUs Genie mensais normalizados para taxa cheia' AS
SELECT * FROM agg_genie_usage_monthly""")

# Step 2
run("""CREATE OR REPLACE VIEW v_monthly_baseline COMMENT 'Passo 2: DBUs mensais por superfície e tipo de identidade' AS
SELECT n.month, n.surface, n.channel, n.identity_type,
       COUNT(DISTINCT n.run_as) AS identities,
       SUM(CASE WHEN n.is_free THEN n.recorded_dbus ELSE 0 END)     AS free_dbus,
       SUM(CASE WHEN NOT n.is_free THEN n.recorded_dbus ELSE 0 END) AS billed_dbus,
       SUM(n.full_rate_dbus)                                         AS full_rate_dbus
FROM v_genie_usage_normalized n
GROUP BY ALL""")

# Step 3
run("""CREATE OR REPLACE VIEW v_identity_month COMMENT 'Passo 3: consumo por identidade/mês e simulação das regras pós-promoção' AS
WITH agg AS (
  SELECT month, run_as, identity_type,
         SUM(full_rate_dbus) AS full_rate_dbus,
         SUM(CASE WHEN surface = 'GENIE_AGENTS' THEN full_rate_dbus ELSE 0 END) AS agents_dbus,
         SUM(CASE WHEN surface = 'GENIE_ONE'    THEN full_rate_dbus ELSE 0 END) AS one_dbus,
         SUM(CASE WHEN surface = 'GENIE_CODE'   THEN full_rate_dbus ELSE 0 END) AS code_dbus,
         SUM(CASE WHEN NOT is_free THEN recorded_dbus ELSE 0 END)              AS billed_dbus_today,
         MAX(active_days) AS active_days
  FROM v_genie_usage_normalized GROUP BY ALL
)
SELECT a.*,
       CASE WHEN a.identity_type = 'HUMANO' THEN GREATEST(a.full_rate_dbus - p.free_allowance_dbus, 0)
            ELSE a.full_rate_dbus END                                   AS billable_dbus_post_promo,
       CASE WHEN a.identity_type = 'HUMANO' THEN GREATEST(a.full_rate_dbus - p.free_allowance_dbus, 0)
            ELSE a.full_rate_dbus END * p.srti_net_price_with_addon      AS cost_post_promo_usd,
       a.billed_dbus_today * p.srti_net_price_with_addon                 AS cost_today_usd,
       a.identity_type = 'HUMANO' AND a.full_rate_dbus > p.free_allowance_dbus AS above_allowance
FROM agg a CROSS JOIN v_price p""")

run("""CREATE OR REPLACE VIEW v_post_promo_simulation COMMENT 'Passo 3: quanto cada mês teria custado com as regras de fev/2027' AS
SELECT month, identity_type, COUNT(*) AS identities, SUM(full_rate_dbus) AS gross_dbus,
       SUM(billable_dbus_post_promo) AS billable_dbus_post_promo, SUM(cost_post_promo_usd) AS cost_post_promo_usd,
       SUM(cost_today_usd) AS cost_today_usd, COUNT_IF(above_allowance) AS humans_above_allowance
FROM v_identity_month GROUP BY ALL""")

# Step 4
run("""CREATE OR REPLACE VIEW v_user_persona_month COMMENT 'Passo 4: usuários humanos classificados em personas por percentil do mês' AS
WITH r AS (
  SELECT i.*, PERCENT_RANK() OVER (PARTITION BY month ORDER BY full_rate_dbus) AS pct_rank
  FROM v_identity_month i WHERE identity_type = 'HUMANO'
)
SELECT r.*,
       CASE WHEN code_dbus > 0.5 * full_rate_dbus THEN '4-Desenvolvedor (Genie Code)'
            WHEN pct_rank <= 0.50 THEN '1-Iniciante'
            WHEN pct_rank <= 0.90 THEN '2-Praticante'
            ELSE '3-Intensivo' END AS persona,
       CASE WHEN full_rate_dbus <= 150 THEN '0-150 (franquia)'
            WHEN full_rate_dbus <= 450 THEN '150-450'
            WHEN full_rate_dbus <= 1000 THEN '450-1000'
            ELSE '> 1000' END AS dbu_band
FROM r""")

run("""CREATE OR REPLACE VIEW v_persona_stats COMMENT 'Passo 4: percentis e custo por persona' AS
SELECT month, persona, COUNT(*) AS users,
       PERCENTILE_APPROX(full_rate_dbus, 0.5) AS p50_dbus, PERCENTILE_APPROX(full_rate_dbus, 0.9) AS p90_dbus,
       AVG(full_rate_dbus) AS avg_dbus, SUM(billable_dbus_post_promo) AS billable_dbus_post_promo,
       SUM(cost_post_promo_usd) AS cost_post_promo_usd, COUNT_IF(full_rate_dbus <= 150) AS users_within_free
FROM v_user_persona_month GROUP BY ALL""")

# Step 5
run("""CREATE OR REPLACE VIEW v_warehouse_cost_month COMMENT 'Custo mensal dos warehouses usados pelo Genie (lista e líquido)' AS
SELECT DISTINCT g.month, g.warehouse_id, g.warehouse_list_cost_usd AS list_cost_usd,
       g.warehouse_list_cost_usd * (1 - a.contract_discount_sql) * (1 + a.addon_uplift) AS net_cost_usd
FROM agg_genie_warehouse_monthly g CROSS JOIN forecast_assumptions a""")

run("""CREATE OR REPLACE VIEW v_warehouse_attribution COMMENT 'Passo 5: rateio do custo de warehouse por Genie Agent (tempo de task)' AS
SELECT g.month, g.warehouse_id, COALESCE(w.warehouse_name, g.warehouse_id) AS warehouse_name,
       g.genie_space_id,
       CASE WHEN g.genie_space_id IS NULL THEN '(não-Genie / Genie One)'
            ELSE COALESCE(d.agent_name, g.genie_space_id) END AS agent_name,
       g.queries, g.task_ms / NULLIF(g.all_task_ms, 0) AS share_of_warehouse,
       g.warehouse_list_cost_usd * g.task_ms / NULLIF(g.all_task_ms, 0) AS attributed_list_cost_usd,
       g.warehouse_list_cost_usd * g.task_ms / NULLIF(g.all_task_ms, 0)
         * (1 - a.contract_discount_sql) * (1 + a.addon_uplift) AS attributed_net_cost_usd
FROM agg_genie_warehouse_monthly g CROSS JOIN forecast_assumptions a
LEFT JOIN dim_warehouses w ON w.warehouse_id = g.warehouse_id
LEFT JOIN dim_genie_agents d ON d.genie_space_id = g.genie_space_id""")

# Step 6
# Audit logs are large (all services, whole account): keep a small monthly aggregate, refreshed by this job (daily schedule).
run("""CREATE OR REPLACE TABLE agg_genie_questions_monthly
COMMENT 'Agregado mensal de perguntas a Genie Agents derivado de system.access.audit (atualizado pelo job)' AS
SELECT DATE_TRUNC('MONTH', event_date) AS month, workspace_id,
       request_params['space_id'] AS genie_space_id,
       user_identity.email AS identity,
       action_name IN ('genieCreateAgenticResponse', 'createAgenticResponse') AS is_agent_mode,
       COUNT(*) AS questions,
       MAX(event_time) AS last_event_time
FROM src_audit
WHERE service_name = 'aibiGenie'
  AND action_name IN ('genieStartConversationMessage', 'genieCreateConversationMessage', 'createConversationMessage',
                      'genieCreateAgenticResponse', 'createAgenticResponse')
  AND request_params['space_id'] IS NOT NULL
GROUP BY ALL""")

run("""CREATE OR REPLACE VIEW v_agent_activity COMMENT 'Passo 6: perguntas e identidades ativas por Genie Agent/mês (audit)' AS
SELECT a.month, a.genie_space_id, COALESCE(g.agent_name, a.genie_space_id) AS agent_name,
       SUM(a.questions) AS questions,
       SUM(CASE WHEN a.is_agent_mode THEN a.questions ELSE 0 END) AS agent_mode_questions,
       SUM(CASE WHEN a.identity NOT LIKE '%@%' THEN a.questions ELSE 0 END) AS sp_questions,
       COUNT(DISTINCT a.identity) AS active_identities
FROM agg_genie_questions_monthly a LEFT JOIN dim_genie_agents g ON g.genie_space_id = a.genie_space_id
GROUP BY ALL""")

run("""CREATE OR REPLACE VIEW v_unit_costs COMMENT 'Passo 6: custo por pergunta (LLM a taxa cheia + warehouse) por Genie Agent' AS
WITH llm AS (SELECT month, SUM(full_rate_dbus) AS agents_full_rate_dbus
             FROM v_genie_usage_normalized WHERE surface = 'GENIE_AGENTS' GROUP BY month),
q AS (SELECT month, SUM(questions) AS all_questions FROM v_agent_activity GROUP BY month),
wh AS (SELECT month, genie_space_id, SUM(attributed_net_cost_usd) AS warehouse_net_cost_usd
       FROM v_warehouse_attribution WHERE genie_space_id IS NOT NULL GROUP BY ALL)
SELECT act.month, act.genie_space_id, act.agent_name, act.questions, act.agent_mode_questions,
       act.agent_mode_questions / act.questions AS agent_mode_share, act.active_identities,
       llm.agents_full_rate_dbus / q.all_questions                              AS llm_dbus_per_question,
       llm.agents_full_rate_dbus / q.all_questions * p.srti_net_price_with_addon AS llm_cost_per_question_usd,
       COALESCE(wh.warehouse_net_cost_usd, 0) / act.questions                   AS warehouse_cost_per_question_usd,
       llm.agents_full_rate_dbus / q.all_questions * p.srti_net_price_with_addon
         + COALESCE(wh.warehouse_net_cost_usd, 0) / act.questions               AS total_cost_per_question_usd,
       COALESCE(wh.warehouse_net_cost_usd, 0)                                   AS warehouse_net_cost_usd
FROM v_agent_activity act JOIN llm USING (month) JOIN q USING (month)
LEFT JOIN wh ON wh.month = act.month AND wh.genie_space_id = act.genie_space_id
CROSS JOIN v_price p""")

run("""CREATE OR REPLACE VIEW v_monthly_cost_components COMMENT 'Histórico mensal: custo hoje vs regras pós-promoção' AS
WITH llm AS (
  SELECT month,
         SUM(CASE WHEN identity_type = 'HUMANO' THEN cost_post_promo_usd ELSE 0 END)            AS human_llm_post_promo_usd,
         SUM(CASE WHEN identity_type = 'SERVICE_PRINCIPAL' THEN cost_post_promo_usd ELSE 0 END) AS sp_llm_post_promo_usd,
         SUM(cost_today_usd) AS llm_billed_today_usd,
         COUNT_IF(identity_type = 'HUMANO') AS active_humans
  FROM v_identity_month GROUP BY month
),
wh AS (SELECT month, SUM(attributed_net_cost_usd) AS genie_warehouse_usd
       FROM v_warehouse_attribution WHERE genie_space_id IS NOT NULL GROUP BY month)
SELECT llm.month, llm.active_humans, llm.human_llm_post_promo_usd, llm.sp_llm_post_promo_usd,
       COALESCE(wh.genie_warehouse_usd, 0) AS genie_warehouse_usd,
       llm.human_llm_post_promo_usd + llm.sp_llm_post_promo_usd + COALESCE(wh.genie_warehouse_usd, 0) AS total_post_promo_usd,
       llm.llm_billed_today_usd + COALESCE(wh.genie_warehouse_usd, 0) AS total_today_usd,
       llm.month < DATE_TRUNC('MONTH', current_date()) AS is_complete_month
FROM llm LEFT JOIN wh USING (month)""")

# Step 7
run("""CREATE OR REPLACE VIEW v_forecast_baseline COMMENT 'Run-rate do último mês completo (base da previsão)' AS
WITH m0 AS (SELECT MAX(month) AS baseline_month FROM v_monthly_cost_components WHERE is_complete_month),
a AS (SELECT free_allowance_dbus FROM forecast_assumptions LIMIT 1),
i AS (
  SELECT m0.baseline_month, i.identity_type, i.billable_dbus_post_promo, i.full_rate_dbus,
         GREATEST(i.code_dbus - a.free_allowance_dbus, 0) AS code_billable_full
  FROM v_identity_month i JOIN m0 ON i.month = m0.baseline_month CROSS JOIN a
),
agg AS (
  SELECT baseline_month,
         COUNT_IF(identity_type = 'HUMANO') AS active_humans,
         SUM(CASE WHEN identity_type = 'HUMANO' THEN billable_dbus_post_promo ELSE 0 END) AS human_billable_dbus_post_promo,
         SUM(CASE WHEN identity_type = 'HUMANO' THEN code_billable_full ELSE 0 END)       AS human_code_billable_dbus_full,
         SUM(CASE WHEN identity_type = 'SERVICE_PRINCIPAL' THEN full_rate_dbus ELSE 0 END) AS sp_full_rate_dbus
  FROM i GROUP BY baseline_month
)
SELECT agg.*, COALESCE(c.genie_warehouse_usd, 0) AS genie_warehouse_usd
FROM agg LEFT JOIN v_monthly_cost_components c ON c.month = agg.baseline_month""")

run("""CREATE OR REPLACE VIEW v_fy_forecast COMMENT 'Passo 7: previsão mensal do ano fiscal por cenário' AS
WITH b AS (SELECT * FROM v_forecast_baseline),
p AS (SELECT * FROM v_price),
months AS (SELECT explode(sequence(p.fy_start, add_months(p.fy_start, 11), INTERVAL 1 MONTH)) AS month FROM p),
grid AS (
  SELECT m.month, s.*, CAST(months_between(m.month, b.baseline_month) AS INT) AS k,
         m.month <= p.promo_end_date AS in_promo,
         GREATEST(CAST(months_between(m.month, date_add(p.promo_end_date, 1)) AS INT) + 1, 0) AS months_after_promo
  FROM months m CROSS JOIN forecast_scenarios s CROSS JOIN b CROSS JOIN p
)
SELECT g.month, g.scenario, g.scenario_order, g.in_promo,
       CASE WHEN g.in_promo THEN b.human_code_billable_dbus_full * p.promo_factor
            ELSE b.human_billable_dbus_post_promo END
         * POWER(1 + g.human_usage_growth_m, g.k) * p.srti_net_price_with_addon  AS human_llm_usd,
       b.sp_full_rate_dbus * CASE WHEN g.in_promo THEN p.promo_factor ELSE 1 END
         * POWER(1 + g.sp_growth_m, g.k) * p.srti_net_price_with_addon           AS sp_llm_usd,
       b.genie_warehouse_usd * POWER(1 + g.warehouse_growth_m, g.k)              AS genie_warehouse_usd,
       g.new_uc_usd_m * g.months_after_promo                                      AS new_use_cases_usd,
       p.headroom
FROM grid g CROSS JOIN b CROSS JOIN p""")

run("""CREATE OR REPLACE VIEW v_fy_forecast_total COMMENT 'Passo 7: previsão com totais e margem' AS
SELECT *,
       human_llm_usd + sp_llm_usd + genie_warehouse_usd + new_use_cases_usd                    AS total_usd,
       (human_llm_usd + sp_llm_usd + genie_warehouse_usd + new_use_cases_usd) * (1 + headroom) AS total_with_headroom_usd
FROM v_fy_forecast""")

# COMMAND ----------

# MAGIC %md ## Smoke test

# COMMAND ----------

display(spark.sql("SELECT * FROM v_price"))
display(spark.sql("SELECT * FROM v_monthly_cost_components ORDER BY month"))
display(spark.sql("""SELECT scenario, ROUND(SUM(total_usd)) AS fy_total_usd, ROUND(SUM(total_with_headroom_usd)) AS fy_total_with_headroom_usd
                     FROM v_fy_forecast_total GROUP BY scenario ORDER BY MIN(scenario_order)"""))
