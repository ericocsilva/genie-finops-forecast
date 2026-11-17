#!/usr/bin/env python3
"""Generates src/dashboards/genie_finops_passos.lvdash.json — didactic AI/BI dashboard (pt_BR) that follows
steps 1 to 10 of docs/GUIA_PREVISAO_GENIE_ptBR.md, one tab per step.

Each tab has: (1) a header with the step goal and the guide section, (2) a "Como ler" box,
(3) an "O que os dados mostram" table whose sentences are computed in SQL from the customer's own data
(so the comments stay valid in any workspace), (4) KPIs and charts with captions.

Run:  python3 scripts/build_dashboard_passos.py
Uses the same views as the thematic dashboard (built by src/notebooks/build_genie_finops_views.py).
All dataset queries use bare view names; catalog/schema come from the bundle.
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "dashboards" / "genie_finops_passos.lvdash.json"

# ---------------------------------------------------------------- SQL snippets
LAST = "(SELECT MAX(month) FROM v_monthly_cost_components WHERE is_complete_month)"
FIRST = "(SELECT MIN(month) FROM v_monthly_cost_components)"
RANGE = f"month > {FIRST} AND month <= {LAST}"          # full months, first (partial) month excluded
REF = f"ref AS (SELECT {LAST} AS m)"
MES = "date_format(ref.m, 'MM/yyyy')"


def N(x, d=0):
    """pt-BR number formatting (1.234,5) with 'n/d' for nulls."""
    return f"COALESCE(translate(format_number(CAST({x} AS DOUBLE), {d}), ',.', '.,'), 'n/d')"


def U(x, d=0):
    return f"concat('US$ ', {N(x, d)})"


def P(x, d=1):
    return f"concat({N(f'100 * ({x})', d)}, '%')"


def SP(x, d=1):
    """signed percent change."""
    return f"concat(CASE WHEN ({x}) >= 0 THEN '+' ELSE '' END, {P(x, d)})"


def q(lines):
    return [l if l.endswith("\n") else l + "\n" for l in lines]


def obs(ctes, sentences):
    """Dataset query: one row per observation (ordem, observacao). ctes: list of 'name AS (...)'."""
    lines = ["WITH " + ",\n".join(ctes)]
    for i, (src, expr) in enumerate(sentences, 1):
        lines.append(("SELECT " if i == 1 else "UNION ALL SELECT ") + f"{i} AS ordem, {expr} AS observacao FROM {src}")
    # Pre-wrap each sentence (~WRAP chars per line) so the Vega-Lite text list below can render it on several lines.
    lines[1] = "o AS (" + lines[1]
    lines[-1] = lines[-1] + "),"
    lines.insert(1, ",")
    lines += [
        "wrapped AS (SELECT ordem, observacao, regexp_replace(regexp_replace(concat('• ', observacao),"
        f" '(.{{1,{WRAP}}})(\\\\s+|$)', '$1\\n   '), '\\n   $', '') AS texto FROM o WHERE observacao IS NOT NULL),",
        "lines_ AS (SELECT *, size(split(texto, '\\\\n')) AS n_lines FROM wrapped)",
        f"SELECT ordem, observacao, texto, (COALESCE(SUM(n_lines) OVER (ORDER BY ordem ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) * {LINE_PX}",
        f"       + (ordem - 1) * {GAP_PX}) AS y_px",
        "FROM lines_ ORDER BY ordem",
    ]
    return q(lines)


WRAP, LINE_PX, GAP_PX = 88, 19, 10


# ---------------------------------------------------------------- formats
USD = {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact",
       "decimalPlaces": {"type": "max", "places": 1}}
USD2 = {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 2}}
USD3 = {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 3}}
USD4 = {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 4}}
NUM = {"type": "number", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 1}}
INT = {"type": "number", "decimalPlaces": {"type": "max", "places": 0}}
PCT = {"type": "number-percent", "decimalPlaces": {"type": "max", "places": 1}}
X = {"type": "number", "decimalPlaces": {"type": "max", "places": 1}}

SURFACE_COLORS = [{"value": "GENIE_AGENTS", "color": "#1D425C"}, {"value": "GENIE_ONE", "color": "#FFA600"},
                  {"value": "GENIE_CODE", "color": "#995495"}]
IDENTITY_COLORS = [{"value": "HUMANO", "color": "#4E79A7"}, {"value": "SERVICE_PRINCIPAL", "color": "#DE5582"}]
COMPONENT_COLORS = [
    {"value": "LLM — usuários humanos", "color": "#1D425C"},
    {"value": "LLM — service principals", "color": "#DE5582"},
    {"value": "SQL warehouse (Genie)", "color": "#FFA600"},
    {"value": "Novos casos de uso", "color": "#99DDB4"},
]
SCENARIO_COLORS = [{"value": "Conservador", "color": "#4E79A7"}, {"value": "Base", "color": "#FFA600"},
                   {"value": "Agressivo", "color": "#DE5582"}]

# ================================================================ datasets
datasets = []


def ds(name, display, lines):
    datasets.append({"name": name, "displayName": display, "queryLines": q(lines)})


# ---------- Introdução
ds("ds_p0_kpi", "Introdução — KPIs", [
    "WITH c AS (SELECT * FROM v_monthly_cost_components WHERE is_complete_month ORDER BY month DESC LIMIT 1),",
    "f AS (SELECT SUM(total_with_headroom_usd) AS fy_base_usd FROM v_fy_forecast_total WHERE scenario = 'Base')",
    "SELECT c.month AS ref_month, c.total_today_usd, c.total_post_promo_usd, c.total_post_promo_usd / NULLIF(c.total_today_usd, 0) AS multiplier, f.fy_base_usd",
    "FROM c CROSS JOIN f",
])

# ---------- Passo 1
ds("ds_p1_price", "Passo 1 — preço", [
    "SELECT srti_sku, sku_source, srti_list_price, srti_net_price, srti_net_price_with_addon, contract_discount_srti,",
    "       addon_uplift, free_allowance_dbus, free_allowance_dbus * srti_list_price AS allowance_value_usd",
    "FROM v_price",
])
ds("ds_p1_skus", "Passo 1 — SKUs SRTI da conta", [
    "SELECT sku_name, cloud, CASE WHEN billed_by_genie THEN 'Sim' ELSE 'Não (outro produto)' END AS billed_by_genie, last_usage_date",
    "FROM agg_srti_skus ORDER BY billed_by_genie DESC, last_usage_date DESC, sku_name",
])
datasets.append({"name": "ds_p1_obs", "displayName": "Passo 1 — observações", "queryLines": obs(
    ["p AS (SELECT * FROM v_price)",
     "s AS (SELECT COUNT(DISTINCT sku_name) AS n FROM agg_srti_skus WHERE billed_by_genie)"],
    [("p", "concat('SKU que será aplicado a Genie Agents e Genie One a partir de 01/02/2027: ', COALESCE(p.srti_sku, 'nenhum SKU SRTI encontrado'), ' (origem: ', COALESCE(p.sku_source, 'n/d'), ').')"),
     ("p", f"concat('Preço de lista: US$ ', {N('p.srti_list_price', 4)}, '/DBU. Com desconto contratual de ', {P('p.contract_discount_srti')}, ' e adicional de plataforma de ', {P('p.addon_uplift')}, ', o preço líquido usado em toda a previsão é US$ ', {N('p.srti_net_price_with_addon', 4)}, '/DBU.')"),
     ("p", f"concat('A franquia de ', {N('p.free_allowance_dbus')}, ' DBUs vale ', {U('p.free_allowance_dbus * p.srti_list_price', 2)}, ' por usuário/mês a preço de lista. A franquia não é afetada pelo desconto contratual.')"),
     ("s", "CASE WHEN s.n > 1 THEN concat(s.n, ' SKUs SRTI são faturados pelo Genie na conta, ou seja, há workspaces em várias regiões. O modelo usa um único preço (o SKU mais recente). Para precisão por região, filtre workspace_ids por região.') "
           "WHEN s.n = 1 THEN 'Um único SKU SRTI é faturado pelo Genie na conta: o preço acima vale para todo o uso.' "
           "ELSE 'O Genie ainda não fatura nenhum SKU SRTI na conta: o preço vem do SKU SRTI usado por outro produto de IA da mesma conta.' END"),
     ("p", "CASE WHEN p.contract_discount_srti = 0 THEN 'O desconto contratual está em 0% (preço de lista). Peça ao time comercial o desconto do SKU SRTI e atualize forecast_assumptions.contract_discount_srti.' "
           f"ELSE concat('Desconto contratual configurado: ', {P('p.contract_discount_srti')}, '. Confirme com o time comercial que ele vale para o SKU SRTI.') END"),
     ])})

# ---------- Passo 2
ds("ds_p2", "Passo 2 — linha de base mensal", [
    "SELECT month, surface, identity_type, channel, free_dbus, billed_dbus, full_rate_dbus, identities",
    f"FROM v_monthly_baseline WHERE {RANGE} ORDER BY month",
])
ds("ds_p2_fb", "Passo 2 — gratuito vs faturado", [
    "SELECT month, 'Gratuito hoje (GENIE_FREE_USAGE)' AS sku_type, SUM(free_dbus) AS dbus",
    f"FROM v_monthly_baseline WHERE {RANGE} GROUP BY month",
    "UNION ALL SELECT month, 'Faturado hoje (SRTI, com 25% off)', SUM(billed_dbus)",
    f"FROM v_monthly_baseline WHERE {RANGE} GROUP BY month ORDER BY month",
])
ds("ds_p2_kpi", "Passo 2 — KPIs do mês de referência", [
    f"WITH {REF},",
    "b AS (SELECT v.* FROM v_monthly_baseline v JOIN ref ON v.month = ref.m),",
    "i AS (SELECT v.* FROM v_identity_month v JOIN ref ON v.month = ref.m)",
    "SELECT (SELECT SUM(full_rate_dbus) FROM b) AS total_dbus,",
    "       (SELECT SUM(free_dbus) FROM b WHERE surface IN ('GENIE_AGENTS', 'GENIE_ONE') AND identity_type = 'HUMANO') AS free_agents_one_dbus,",
    "       (SELECT SUM(billed_dbus) FROM b WHERE identity_type = 'SERVICE_PRINCIPAL') AS sp_billed_dbus,",
    "       (SELECT COUNT_IF(identity_type = 'HUMANO') FROM i) AS humans,",
    "       (SELECT COUNT_IF(identity_type = 'SERVICE_PRINCIPAL') FROM i) AS sps",
])
datasets.append({"name": "ds_p2_obs", "displayName": "Passo 2 — observações", "queryLines": obs(
    [REF,
     "b AS (SELECT SUM(full_rate_dbus) AS tot, SUM(CASE WHEN surface = 'GENIE_AGENTS' THEN full_rate_dbus END) AS ag,"
     " SUM(CASE WHEN surface = 'GENIE_ONE' THEN full_rate_dbus END) AS one, SUM(CASE WHEN surface = 'GENIE_CODE' THEN full_rate_dbus END) AS code,"
     " SUM(CASE WHEN surface IN ('GENIE_AGENTS', 'GENIE_ONE') AND identity_type = 'HUMANO' THEN free_dbus END) AS free_ao,"
     " SUM(CASE WHEN identity_type = 'SERVICE_PRINCIPAL' THEN billed_dbus END) AS sp_billed,"
     " SUM(CASE WHEN channel = 'API' THEN full_rate_dbus END) AS api"
     " FROM v_monthly_baseline v JOIN ref ON v.month = ref.m)",
     "bp AS (SELECT SUM(full_rate_dbus) AS tot FROM v_monthly_baseline v JOIN ref ON v.month = add_months(ref.m, -1))",
     "n AS (SELECT COUNT_IF(identity_type = 'SERVICE_PRINCIPAL') AS sps FROM v_identity_month v JOIN ref ON v.month = ref.m)"],
    [("b CROSS JOIN ref", f"concat('Em ', {MES}, ', o Genie consumiu ', {N('b.tot')}, ' DBUs (taxa cheia): Genie Agents ', {P('b.ag / b.tot')}, ', Genie One ', {P('b.one / b.tot')}, ' e Genie Code ', {P('b.code / b.tot')}, '.')"),
     ("b", f"concat({N('b.free_ao')}, ' DBUs de Genie Agents e Genie One usados por pessoas foram gratuitos (GENIE_FREE_USAGE). É esse volume que passa a ser cobrável, acima da franquia, a partir de 01/02/2027.')"),
     ("b CROSS JOIN n", f"concat('Service principals já tiveram ', {N('b.sp_billed')}, ' DBUs faturados no mês (', {N('n.sps')}, ' identidades). Isso já é custo hoje: SPs não têm franquia nem gratuidade.')"),
     ("b", f"concat('O canal API (apps, integrações, MCP) respondeu por ', {P('b.api / b.tot')}, ' dos DBUs. O restante veio da interface do Genie (UI).')"),
     ("b CROSS JOIN bp", f"concat('Variação do consumo total de DBUs em relação ao mês anterior: ', {SP('b.tot / bp.tot - 1')}, '. Com poucos meses de histórico, use essa tendência só para calibrar os cenários do Passo 7.')"),
     ])})

# ---------- Passo 3
ds("ds_p3", "Passo 3 — simulação pós-promoção", [
    "SELECT month, identity_type, identities, gross_dbus, billable_dbus_post_promo, cost_today_usd, cost_post_promo_usd, humans_above_allowance",
    f"FROM v_post_promo_simulation WHERE {RANGE} ORDER BY month, identity_type",
])
ds("ds_p3_cost", "Passo 3 — hoje vs fev/2027", [
    "SELECT month, '1. Custo de LLM hoje (regras atuais)' AS basis, SUM(cost_today_usd) AS usd",
    f"FROM v_post_promo_simulation WHERE {RANGE} GROUP BY month",
    "UNION ALL SELECT month, '2. Mesmo uso com as regras de fev/2027', SUM(cost_post_promo_usd)",
    f"FROM v_post_promo_simulation WHERE {RANGE} GROUP BY month ORDER BY month",
])
ds("ds_p3_dbus", "Passo 3 — efeito da franquia (humanos)", [
    "SELECT month, '1. DBUs brutos (taxa cheia)' AS kind, gross_dbus AS dbus",
    f"FROM v_post_promo_simulation WHERE identity_type = 'HUMANO' AND {RANGE}",
    "UNION ALL SELECT month, '2. DBUs cobráveis após a franquia', billable_dbus_post_promo",
    f"FROM v_post_promo_simulation WHERE identity_type = 'HUMANO' AND {RANGE} ORDER BY month",
])
P3_CTE = ("s AS (SELECT SUM(cost_today_usd) AS today, SUM(cost_post_promo_usd) AS post,"
          " SUM(CASE WHEN identity_type = 'SERVICE_PRINCIPAL' THEN cost_post_promo_usd END) AS sp_post,"
          " SUM(CASE WHEN identity_type = 'HUMANO' THEN identities END) AS humans,"
          " SUM(CASE WHEN identity_type = 'HUMANO' THEN humans_above_allowance END) AS above,"
          " SUM(CASE WHEN identity_type = 'HUMANO' THEN gross_dbus END) AS h_gross,"
          " SUM(CASE WHEN identity_type = 'HUMANO' THEN billable_dbus_post_promo END) AS h_bill"
          " FROM v_post_promo_simulation v JOIN ref ON v.month = ref.m)")
ds("ds_p3_kpi", "Passo 3 — KPIs", [
    f"WITH {REF}, {P3_CTE}",
    "SELECT today AS cost_today_usd, post AS cost_post_promo_usd, post / NULLIF(today, 0) AS multiplier,",
    "       above / NULLIF(humans, 0) AS pct_above, 1 - h_bill / NULLIF(h_gross, 0) AS allowance_absorbed FROM s",
])
datasets.append({"name": "ds_p3_obs", "displayName": "Passo 3 — observações", "queryLines": obs(
    [REF, P3_CTE],
    [("s CROSS JOIN ref", f"concat('Em ', {MES}, ', o LLM do Genie custou ', {U('s.today')}, ' com as regras atuais. Com as regras de fev/2027, o mesmo uso custaria ', {U('s.post')}, ' (', {N('s.post / s.today', 1)}, 'x).')"),
     ("s", f"concat({N('s.above')}, ' de ', {N('s.humans')}, ' usuários humanos (', {P('s.above / s.humans')}, ') passaram da franquia de 150 DBUs no mês. Para os demais, o custo de LLM seria zero.')"),
     ("s", f"concat('A franquia por usuário absorve ', {P('1 - s.h_bill / s.h_gross')}, ' dos DBUs consumidos por pessoas. O restante (', {N('s.h_bill')}, ' DBUs) vem de quem passa de 150 DBUs.')"),
     ("s", f"concat('Service principals respondem por ', {P('s.sp_post / s.post')}, ' do custo de LLM pós-promoção. Todo DBU de SP é cobrado.')"),
     ("s", "'Este valor ainda não inclui a computação do SQL warehouse (Passo 5) nem crescimento (Passo 7): é o run-rate de LLM a partir de fev/2027.'"),
     ])})

# ---------- Passo 4
ds("ds_p4_persona", "Passo 4 — personas por mês", [
    "SELECT month, persona, users, p50_dbus, p90_dbus, avg_dbus, billable_dbus_post_promo, cost_post_promo_usd, users_within_free",
    f"FROM v_persona_stats WHERE {RANGE} ORDER BY month, persona",
])
ds("ds_p4_persona_ref", "Passo 4 — personas no mês de referência", [
    "SELECT persona, users, p50_dbus, p90_dbus, avg_dbus, users_within_free, cost_post_promo_usd,",
    "       cost_post_promo_usd / users AS cost_per_user_usd",
    f"FROM v_persona_stats WHERE month = {LAST} ORDER BY persona",
])
ds("ds_p4_band", "Passo 4 — faixas de DBUs", [
    "SELECT dbu_band, persona, COUNT(*) AS users, SUM(cost_post_promo_usd) AS cost_post_promo_usd",
    f"FROM v_user_persona_month WHERE month = {LAST} GROUP BY ALL ORDER BY dbu_band",
])
ds("ds_p4_top", "Passo 4 — top 20 identidades", [
    "SELECT i.run_as AS identity, i.identity_type, COALESCE(p.persona, 'Service principal') AS persona,",
    "       i.full_rate_dbus, i.agents_dbus, i.one_dbus, i.code_dbus, i.billable_dbus_post_promo, i.cost_post_promo_usd",
    "FROM v_identity_month i LEFT JOIN v_user_persona_month p ON p.month = i.month AND p.run_as = i.run_as",
    f"WHERE i.month = {LAST} ORDER BY i.cost_post_promo_usd DESC LIMIT 20",
])
P4_CTES = [REF,
           "h AS (SELECT v.* FROM v_identity_month v JOIN ref ON v.month = ref.m WHERE v.identity_type = 'HUMANO')",
           "pc AS (SELECT PERCENTILE_APPROX(full_rate_dbus, 0.5) AS p50, PERCENTILE_APPROX(full_rate_dbus, 0.9) AS p90,"
           " PERCENTILE_APPROX(full_rate_dbus, 0.99) AS p99, MAX(full_rate_dbus) AS mx, COUNT(*) AS n FROM h)",
           "r AS (SELECT cost_post_promo_usd AS c, ROW_NUMBER() OVER (ORDER BY cost_post_promo_usd DESC) AS rn, COUNT(*) OVER () AS n FROM h)",
           "conc AS (SELECT SUM(CASE WHEN rn <= n * 0.1 THEN c END) / SUM(c) AS top10pct, SUM(CASE WHEN rn <= 20 THEN c END) / SUM(c) AS top20 FROM r)",
           "ps AS (SELECT max_by(persona, cost_post_promo_usd) AS top_persona, MAX(cost_post_promo_usd) AS top_cost, SUM(cost_post_promo_usd) AS tot,"
           " SUM(CASE WHEN persona LIKE '4-%' THEN users END) AS devs, SUM(CASE WHEN persona LIKE '1-%' THEN users END) AS beginners"
           " FROM v_persona_stats v JOIN ref ON v.month = ref.m)"]
ds("ds_p4_kpi", "Passo 4 — KPIs", [
    "WITH " + ",\n".join(P4_CTES),
    "SELECT pc.p50 AS p50_dbus, pc.p90 AS p90_dbus, pc.p99 AS p99_dbus, conc.top10pct FROM pc CROSS JOIN conc",
])
datasets.append({"name": "ds_p4_obs", "displayName": "Passo 4 — observações", "queryLines": obs(
    P4_CTES,
    [("pc CROSS JOIN ref", f"concat('Em ', {MES}, ', o usuário mediano (p50) consumiu ', {N('pc.p50')}, ' DBUs; p90 = ', {N('pc.p90')}, ', p99 = ', {N('pc.p99')}, ' e o maior consumo individual = ', {N('pc.mx')}, ' DBUs. Compare com a franquia de 150 DBUs.')"),
     ("conc", f"concat('Os 10% de usuários que mais consomem concentram ', {P('conc.top10pct')}, ' do custo de LLM pós-promoção, e os 20 maiores, ', {P('conc.top20')}, '. Por isso a franquia deve ser aplicada por usuário: médias enganam.')"),
     ("ps", f"concat('A persona com maior custo é ', substr(ps.top_persona, 3), ': ', {U('ps.top_cost')}, ' (', {P('ps.top_cost / ps.tot')}, ' do custo de LLM de humanos).')"),
     ("ps", f"concat({N('ps.beginners')}, ' iniciantes ficam dentro da franquia (custo de LLM zero). ', {N('ps.devs')}, ' usuários são predominantemente Genie Code: a partir de fev/2027 eles dividem a mesma franquia com Agents e One.')"),
     ("ps", "'Próximo passo: confirmar com cada área se o uso dos top 20 abaixo é legítimo e recorrente antes de projetá-lo no Passo 7.'"),
     ])})

# ---------- Passo 5
ds("ds_p5_trend", "Passo 5 — LLM vs warehouse", [
    "SELECT month, '1. LLM (regras pós-promoção)' AS component, human_llm_post_promo_usd + sp_llm_post_promo_usd AS usd",
    f"FROM v_monthly_cost_components WHERE is_complete_month AND month > {FIRST}",
    "UNION ALL SELECT month, '2. SQL warehouse atribuído ao Genie', genie_warehouse_usd",
    f"FROM v_monthly_cost_components WHERE is_complete_month AND month > {FIRST} ORDER BY month",
])
ds("ds_p5_top", "Passo 5 — top 15 Genie Agents", [
    "SELECT agent_name, warehouse_name, attributed_net_cost_usd FROM v_warehouse_attribution",
    f"WHERE month = {LAST} AND genie_space_id IS NOT NULL ORDER BY attributed_net_cost_usd DESC LIMIT 15",
])
P5_WH = ("w AS (SELECT warehouse_id, MAX(warehouse_name) AS warehouse_name,"
         " SUM(CASE WHEN genie_space_id IS NOT NULL THEN share_of_warehouse ELSE 0 END) AS genie_share,"
         " SUM(CASE WHEN genie_space_id IS NOT NULL THEN queries ELSE 0 END) AS genie_queries,"
         " COUNT(DISTINCT genie_space_id) AS agents,"
         " SUM(CASE WHEN genie_space_id IS NOT NULL THEN attributed_net_cost_usd ELSE 0 END) AS genie_cost_usd,"
         " SUM(attributed_net_cost_usd) AS warehouse_cost_usd"
         f" FROM v_warehouse_attribution WHERE month = {LAST} GROUP BY warehouse_id)")
ds("ds_p5_wh", "Passo 5 — warehouses", [
    "WITH " + P5_WH,
    "SELECT warehouse_name, CASE WHEN genie_share >= 0.95 THEN 'Dedicado ao Genie (≥ 95%)' WHEN genie_share >= 0.5 THEN 'Majoritariamente Genie'",
    "       ELSE 'Compartilhado (< 50% Genie)' END AS wh_type, agents, genie_queries, genie_share, genie_cost_usd, warehouse_cost_usd",
    "FROM w ORDER BY genie_cost_usd DESC LIMIT 50",
])
P5_CTES = [REF, P5_WH.replace(f"month = {LAST}", "month = (SELECT m FROM ref)"),
           "c AS (SELECT v.* FROM v_monthly_cost_components v JOIN ref ON v.month = ref.m)",
           "cp AS (SELECT v.* FROM v_monthly_cost_components v JOIN ref ON v.month = add_months(ref.m, -1))",
           "t AS (SELECT max_by(agent_name, attributed_net_cost_usd) AS agent, MAX(attributed_net_cost_usd) AS cost"
           " FROM v_warehouse_attribution v JOIN ref ON v.month = ref.m WHERE genie_space_id IS NOT NULL)",
           "k AS (SELECT COUNT(*) AS n, COUNT_IF(genie_share >= 0.95) AS dedicated, COUNT_IF(genie_share < 0.5) AS shared FROM w)"]
ds("ds_p5_kpi", "Passo 5 — KPIs", [
    "WITH " + ",\n".join(P5_CTES),
    "SELECT c.genie_warehouse_usd, c.genie_warehouse_usd / NULLIF(c.total_post_promo_usd, 0) AS wh_share, k.n AS warehouses, k.dedicated",
    "FROM c CROSS JOIN k",
])
datasets.append({"name": "ds_p5_obs", "displayName": "Passo 5 — observações", "queryLines": obs(
    P5_CTES,
    [("c CROSS JOIN ref", f"concat('Em ', {MES}, ', a computação SQL atribuída aos Genie Agents custou ', {U('c.genie_warehouse_usd')}, ', ou ', {P('c.genie_warehouse_usd / c.total_post_promo_usd')}, ' do custo total pós-promoção. Esse valor não entra no budget do Genie.')"),
     ("k", f"concat({N('k.n')}, ' warehouses executaram queries do Genie: ', {N('k.dedicated')}, ' são praticamente dedicados (≥ 95% do tempo de task) e ', {N('k.shared')}, ' são compartilhados (< 50%). Em warehouses compartilhados o rateio é uma estimativa.')"),
     ("t", f"concat('O Genie Agent com maior custo de warehouse no mês é ', COALESCE(t.agent, 'n/d'), ' (', {U('t.cost')}, ').')"),
     ("c CROSS JOIN cp", f"concat('Variação do custo de warehouse do Genie em relação ao mês anterior: ', {SP('c.genie_warehouse_usd / cp.genie_warehouse_usd - 1')}, '.')"),
     ("c", "'Ociosidade e auto-stop não entram no rateio proporcional. Para atribuição exata, use um warehouse serverless dedicado por área para os Genie Agents de produção.'"),
     ])})

# ---------- Passo 6
ds("ds_p6_unit", "Passo 6 — custo por pergunta", [
    "SELECT agent_name, questions, agent_mode_share, active_identities, llm_dbus_per_question,",
    "       llm_cost_per_question_usd, warehouse_cost_per_question_usd, total_cost_per_question_usd, warehouse_net_cost_usd",
    f"FROM v_unit_costs WHERE month = {LAST} ORDER BY questions DESC LIMIT 25",
])
P6_CTES = [REF,
           "u AS (SELECT SUM(questions) AS questions, COUNT(*) AS agents, SUM(agent_mode_questions) AS am,"
           " MAX(llm_cost_per_question_usd) AS llm_q, SUM(warehouse_net_cost_usd) AS wh"
           " FROM v_unit_costs v JOIN ref ON v.month = ref.m)",
           "c AS (SELECT v.* FROM v_monthly_cost_components v JOIN ref ON v.month = ref.m)",
           "top AS (SELECT max_by(agent_name, total_cost_per_question_usd) AS agent, MAX(total_cost_per_question_usd) AS cpq"
           " FROM v_unit_costs v JOIN ref ON v.month = ref.m WHERE questions >= 20)"]
ds("ds_p6_kpi", "Passo 6 — KPIs", [
    "WITH " + ",\n".join(P6_CTES),
    "SELECT u.questions, u.am / NULLIF(u.questions, 0) AS agent_mode_share, u.llm_q + u.wh / NULLIF(u.questions, 0) AS cost_per_question_usd,",
    "       (c.human_llm_post_promo_usd + c.genie_warehouse_usd) / NULLIF(c.active_humans, 0) AS cost_per_active_user_usd",
    "FROM u CROSS JOIN c",
])
datasets.append({"name": "ds_p6_obs", "displayName": "Passo 6 — observações", "queryLines": obs(
    P6_CTES,
    [("u CROSS JOIN ref", f"concat('Em ', {MES}, ' o audit log registrou ', {N('u.questions')}, ' perguntas a ', {N('u.agents')}, ' Genie Agents, ', {P('u.am / u.questions')}, ' delas em Agent mode (mais tokens e mais queries por pergunta).')"),
     ("u", f"concat('Custo médio por pergunta: ', {U('u.llm_q + u.wh / u.questions', 3)}, ' = LLM ', {U('u.llm_q', 3)}, ' + warehouse ', {U('u.wh / u.questions', 3)}, '.')"),
     ("c", f"concat('Custo por usuário humano ativo por mês (LLM cobrável pós-promoção + warehouse): ', {U('(c.human_llm_post_promo_usd + c.genie_warehouse_usd) / c.active_humans', 2)}, ' para ', {N('c.active_humans')}, ' usuários ativos.')"),
     ("top", f"concat('Maior custo por pergunta (Agents com 20 ou mais perguntas): ', COALESCE(top.agent, 'n/d'), ', com ', {U('top.cpq', 2)}, ' por pergunta. Revise instruções, uso de Agent mode e tamanho do warehouse.')"),
     ("u", "'O LLM por pergunta é a média da conta (o billing ainda não traz o Genie Agent nem a conversa). A parte de warehouse é específica de cada Agent.'"),
     ])})

# ---------- Passo 7
ds("ds_p7_fc", "Passo 7 — previsão mensal", [
    "SELECT month, scenario, scenario_order, in_promo, human_llm_usd, sp_llm_usd, genie_warehouse_usd,",
    "       new_use_cases_usd, total_usd, total_with_headroom_usd",
    "FROM v_fy_forecast_total ORDER BY scenario_order, month",
])
ds("ds_p7_long", "Passo 7 — previsão por componente", [
    "SELECT month, scenario, 'LLM — usuários humanos' AS component, human_llm_usd AS usd FROM v_fy_forecast_total",
    "UNION ALL SELECT month, scenario, 'LLM — service principals', sp_llm_usd FROM v_fy_forecast_total",
    "UNION ALL SELECT month, scenario, 'SQL warehouse (Genie)', genie_warehouse_usd FROM v_fy_forecast_total",
    "UNION ALL SELECT month, scenario, 'Novos casos de uso', new_use_cases_usd FROM v_fy_forecast_total",
    "ORDER BY month",
])
ds("ds_p7_tot", "Passo 7 — totais por cenário", [
    "SELECT f.scenario, MIN(f.scenario_order) AS scenario_order, SUM(f.human_llm_usd) AS human_llm_usd, SUM(f.sp_llm_usd) AS sp_llm_usd,",
    "       SUM(f.genie_warehouse_usd) AS genie_warehouse_usd, SUM(f.new_use_cases_usd) AS new_use_cases_usd,",
    "       SUM(f.total_usd) AS total_usd, SUM(f.total_with_headroom_usd) AS total_with_headroom_usd,",
    "       MAX(s.human_usage_growth_m) AS human_usage_growth_m, MAX(s.sp_growth_m) AS sp_growth_m, MAX(s.warehouse_growth_m) AS warehouse_growth_m",
    "FROM v_fy_forecast_total f JOIN forecast_scenarios s ON s.scenario = f.scenario GROUP BY f.scenario ORDER BY scenario_order",
])
P7_CTES = ["t AS (SELECT SUM(CASE WHEN scenario = 'Conservador' THEN total_with_headroom_usd END) AS cons,"
           " SUM(CASE WHEN scenario = 'Base' THEN total_with_headroom_usd END) AS base,"
           " SUM(CASE WHEN scenario = 'Agressivo' THEN total_with_headroom_usd END) AS aggr,"
           " SUM(CASE WHEN scenario = 'Base' THEN human_llm_usd END) AS b_h, SUM(CASE WHEN scenario = 'Base' THEN sp_llm_usd END) AS b_sp,"
           " SUM(CASE WHEN scenario = 'Base' THEN genie_warehouse_usd END) AS b_wh, SUM(CASE WHEN scenario = 'Base' THEN new_use_cases_usd END) AS b_new,"
           " SUM(CASE WHEN scenario = 'Base' THEN total_usd END) AS b_tot, MAX(headroom) AS headroom FROM v_fy_forecast_total)",
           "m AS (SELECT MAX(CASE WHEN in_promo THEN total_usd END) AS promo_m, min_by(total_usd, CASE WHEN in_promo THEN NULL ELSE month END) AS first_paid,"
           " COUNT_IF(NOT in_promo) AS paid_months FROM v_fy_forecast_total WHERE scenario = 'Base')",
           "b AS (SELECT * FROM v_forecast_baseline)"]
datasets.append({"name": "ds_p7_obs", "displayName": "Passo 7 — observações", "queryLines": obs(
    P7_CTES,
    [("t", f"concat('Previsão do ano fiscal (com margem de ', {P('t.headroom', 0)}, '): Conservador ', {U('t.cons')}, ' · Base ', {U('t.base')}, ' · Agressivo ', {U('t.aggr')}, '.')"),
     ("m", f"concat('No cenário Base, o custo mensal passa de ', {U('m.promo_m')}, ' em jan/2027 (ainda na promoção) para ', {U('m.first_paid')}, ' em fev/2027 (', {N('m.first_paid / m.promo_m', 1)}, 'x). São ', {N('m.paid_months')}, ' meses cobrados com as novas regras.')"),
     ("t", f"concat('Composição do cenário Base no ano: LLM de humanos ', {P('t.b_h / t.b_tot')}, ', LLM de service principals ', {P('t.b_sp / t.b_tot')}, ', SQL warehouse ', {P('t.b_wh / t.b_tot')}, ' e novos casos de uso ', {P('t.b_new / t.b_tot')}, '.')"),
     ("b", f"concat('A projeção parte do run-rate de ', date_format(b.baseline_month, 'MM/yyyy'), ' (último mês completo): ', {N('b.active_humans')}, ' usuários humanos ativos e ', {N('b.human_billable_dbus_post_promo')}, ' DBUs cobráveis de humanos.')"),
     ("b", "'O histórico é curto (desde 20/07/2026) para uma previsão estatística: os crescimentos de cada cenário são premissas da tabela forecast_scenarios. Ajuste-os com o plano de expansão das áreas.'"),
     ])})

# ---------- Passo 8
P8_REF = [REF,
          "u AS (SELECT SUM(questions) AS questions, MAX(llm_cost_per_question_usd) AS llm_q, SUM(warehouse_net_cost_usd) AS wh"
          " FROM v_unit_costs v JOIN ref ON v.month = ref.m)",
          "cpq AS (SELECT u.llm_q + u.wh / NULLIF(u.questions, 0) AS cost_per_question_usd FROM u)",
          "pm AS (SELECT COUNT_IF(NOT in_promo) AS paid_months FROM v_fy_forecast_total WHERE scenario = 'Base')"]
ds("ds_p8_analogy", "Passo 8 — analogia por volume de perguntas", [
    "WITH " + ",\n".join(P8_REF) + ",",
    "v AS (SELECT * FROM VALUES (1000), (5000), (10000), (50000) AS t(questions_per_month))",
    "SELECT v.questions_per_month, cpq.cost_per_question_usd, v.questions_per_month * cpq.cost_per_question_usd AS monthly_usd,",
    "       v.questions_per_month * cpq.cost_per_question_usd * pm.paid_months AS fy_usd",
    "FROM v CROSS JOIN cpq CROSS JOIN pm ORDER BY v.questions_per_month",
])
ds("ds_p8_persona", "Passo 8 — analogia por persona (100 usuários)", [
    "WITH pm AS (SELECT COUNT_IF(NOT in_promo) AS paid_months FROM v_fy_forecast_total WHERE scenario = 'Base')",
    "SELECT persona, cost_post_promo_usd / users AS cost_per_user_usd,",
    "       100 * cost_post_promo_usd / users AS monthly_100_users_usd, 100 * cost_post_promo_usd / users * pm.paid_months AS fy_100_users_usd",
    f"FROM v_persona_stats CROSS JOIN pm WHERE month = {LAST} ORDER BY persona",
])
ds("ds_p8_scen", "Passo 8 — novos casos de uso nas premissas", [
    "SELECT scenario, new_uc_usd_m, description FROM forecast_scenarios ORDER BY scenario_order",
])
datasets.append({"name": "ds_p8_obs", "displayName": "Passo 8 — observações", "queryLines": obs(
    P8_REF + ["s AS (SELECT MAX(new_uc_usd_m) AS mx, MAX(CASE WHEN scenario = 'Base' THEN new_uc_usd_m END) AS base FROM forecast_scenarios)",
              "pp AS (SELECT MAX(CASE WHEN persona LIKE '2-%' THEN cost_post_promo_usd / users END) AS prat,"
              " MAX(CASE WHEN persona LIKE '3-%' THEN cost_post_promo_usd / users END) AS inten"
              " FROM v_persona_stats v JOIN ref ON v.month = ref.m)"],
    [("s", "CASE WHEN s.mx = 0 THEN 'As premissas ainda não têm valor para novos casos de uso (new_uc_usd_m = 0 em todos os cenários). Use as tabelas de analogia abaixo e atualize forecast_scenarios.' "
           f"ELSE concat('Cenário Base: ', {U('s.base')}, ' por mês adicionados a cada mês após o fim da promoção (valor acumulativo, definido em forecast_scenarios).') END"),
     ("cpq", f"concat('Por analogia com os Genie Agents atuais (', {U('cpq.cost_per_question_usd', 3)}, ' por pergunta), um novo Agent com 10.000 perguntas/mês custaria cerca de ', {U('10000 * cpq.cost_per_question_usd')}, ' por mês.')"),
     ("pp", f"concat('Por persona: 100 novos Praticantes custariam cerca de ', {U('100 * pp.prat')}, ' por mês, e 100 novos usuários Intensivos, ', {U('100 * pp.inten')}, ' (só LLM, sem warehouse).')"),
     ("pm", "'A opção mais confiável é um piloto de 2 a 4 semanas com um grupo representativo, medido com os Passos 2 a 6. A calculadora de sizing não inclui computação SQL nem Genie Code.'"),
     ])})

# ---------- Passo 9
P9_CTES = [REF,
           "p AS (SELECT * FROM v_price)",
           "h AS (SELECT v.* FROM v_identity_month v JOIN ref ON v.month = ref.m WHERE v.identity_type = 'HUMANO')",
           "pc AS (SELECT PERCENTILE_APPROX(full_rate_dbus, 0.9) AS p90, PERCENTILE_APPROX(full_rate_dbus, 0.99) AS p99, COUNT(*) AS n FROM h)",
           "f AS (SELECT (human_llm_usd + sp_llm_usd) / NULLIF(1 - p.contract_discount_srti, 0) AS feb_llm_list_usd"
           " FROM v_fy_forecast_total CROSS JOIN p WHERE scenario = 'Base' AND NOT in_promo ORDER BY month LIMIT 1)",
           "th AS (SELECT GREATEST(pc.p90 - p.free_allowance_dbus, 0) * p.srti_list_price * (1 + p.addon_uplift) AS user_limit_usd,"
           " GREATEST(pc.p99 - p.free_allowance_dbus, 0) * p.srti_list_price * (1 + p.addon_uplift) AS power_limit_usd,"
           " pc.p90, pc.p99, pc.n FROM pc CROSS JOIN p)",
           "ab AS (SELECT COUNT_IF(h.full_rate_dbus > th.p90) AS above_default, COUNT_IF(h.full_rate_dbus > th.p99) AS above_power FROM h CROSS JOIN th)",
           "sp AS (SELECT SUM(CASE WHEN identity_type = 'SERVICE_PRINCIPAL' THEN cost_post_promo_usd END) / SUM(cost_post_promo_usd) AS sp_share,"
           " COUNT_IF(identity_type = 'SERVICE_PRINCIPAL' AND cost_post_promo_usd > 0) AS sps FROM v_identity_month v JOIN ref ON v.month = ref.m)",
           "wsh AS (SELECT COUNT(*) AS shared FROM (SELECT warehouse_id, SUM(CASE WHEN genie_space_id IS NOT NULL THEN share_of_warehouse ELSE 0 END) AS gs"
           " FROM v_warehouse_attribution v JOIN ref ON v.month = ref.m GROUP BY warehouse_id) WHERE gs < 0.5)"]
ds("ds_p9_kpi", "Passo 9 — limites sugeridos", [
    "WITH " + ",\n".join(P9_CTES),
    "SELECT f.feb_llm_list_usd AS pool_100_usd, 0.8 * f.feb_llm_list_usd AS pool_80_usd, th.user_limit_usd, th.power_limit_usd",
    "FROM f CROSS JOIN th",
])
ds("ds_p9_persona", "Passo 9 — limite por persona", [
    "WITH p AS (SELECT * FROM v_price)",
    "SELECT s.persona, s.users, s.p90_dbus,",
    "       GREATEST(s.p90_dbus - p.free_allowance_dbus, 0) * p.srti_list_price * (1 + p.addon_uplift) AS suggested_limit_list_usd",
    f"FROM v_persona_stats s CROSS JOIN p WHERE s.month = {LAST} ORDER BY s.persona",
])
ds("ds_p9_sp", "Passo 9 — service principals", [
    "SELECT run_as AS identity, full_rate_dbus, agents_dbus, one_dbus, code_dbus, cost_today_usd, cost_post_promo_usd",
    f"FROM v_identity_month WHERE month = {LAST} AND identity_type = 'SERVICE_PRINCIPAL' ORDER BY cost_post_promo_usd DESC LIMIT 10",
])
datasets.append({"name": "ds_p9_obs", "displayName": "Passo 9 — observações", "queryLines": obs(
    P9_CTES,
    [("f", f"concat('Pool mensal sugerido para o budget do Genie (preço de lista, LLM do cenário Base em fev/2027): ', {U('f.feb_llm_list_usd')}, '. Alertas por e-mail/webhook em 80% (', {U('0.8 * f.feb_llm_list_usd')}, ') e 100%, sem bloqueio.')"),
     ("th", f"concat('Limite padrão por usuário sugerido: ', {U('th.user_limit_usd', 2)}, '/mês acima da franquia (p90 = ', {N('th.p90')}, ' DBUs), com bloqueio. Grupo genie-power-users: ', {U('th.power_limit_usd', 2)}, '/mês (p99 = ', {N('th.p99')}, ' DBUs).')"),
     ("ab CROSS JOIN th", f"concat({N('ab.above_default')}, ' de ', {N('th.n')}, ' usuários passariam do limite padrão no mês de referência, e ', {N('ab.above_power')}, ' passariam do limite de power users. Esses são os candidatos ao grupo com override e ao processo de aprovação.')"),
     ("sp", f"concat('Service principals somam ', {P('sp.sp_share')}, ' do custo de LLM pós-promoção (', {N('sp.sps')}, ' SPs com custo). Para apps voltadas a usuários, prefira OBO: cada usuário usa a própria franquia e a atribuição fica por pessoa.')"),
     ("wsh", f"concat({N('wsh.shared')}, ' warehouses compartilhados (< 50% Genie) executam queries do Genie. Budgets do Genie não cobrem warehouse: use budgets de DBSQL e tags nos warehouses, de preferência dedicados por área.')"),
     ])})

# ---------- Passo 10
ds("ds_p10_track", "Passo 10 — real vs previsto", [
    "SELECT month, '1. Real — faturado hoje' AS series, total_today_usd AS usd FROM v_monthly_cost_components",
    f"WHERE is_complete_month AND month > {FIRST}",
    "UNION ALL SELECT month, '2. Real — regras de fev/2027', total_post_promo_usd FROM v_monthly_cost_components",
    f"WHERE is_complete_month AND month > {FIRST}",
    "UNION ALL SELECT month, concat('3. Previsto — ', scenario), total_usd FROM v_fy_forecast_total",
    "ORDER BY month",
])
ds("ds_p10_agents", "Passo 10 — Agents para otimizar", [
    "SELECT agent_name, questions, agent_mode_share, total_cost_per_question_usd, warehouse_net_cost_usd",
    f"FROM v_unit_costs WHERE month = {LAST} AND questions >= 20 ORDER BY total_cost_per_question_usd DESC LIMIT 10",
])
ds("ds_p10_movers", "Passo 10 — maiores aumentos vs mês anterior", [
    "WITH cur AS (SELECT run_as, identity_type, cost_post_promo_usd FROM v_identity_month WHERE month = " + LAST + "),",
    "prev AS (SELECT run_as, cost_post_promo_usd FROM v_identity_month WHERE month = add_months(" + LAST + ", -1))",
    "SELECT cur.run_as AS identity, cur.identity_type, COALESCE(prev.cost_post_promo_usd, 0) AS prev_usd, cur.cost_post_promo_usd AS cur_usd,",
    "       cur.cost_post_promo_usd - COALESCE(prev.cost_post_promo_usd, 0) AS delta_usd",
    "FROM cur LEFT JOIN prev USING (run_as) ORDER BY delta_usd DESC LIMIT 10",
])
P10_CTES = [REF,
            "fr AS (SELECT GREATEST((SELECT MAX(last_usage_date) FROM agg_srti_skus),"
            " (SELECT CAST(MAX(last_event_time) AS DATE) FROM agg_genie_questions_monthly)) AS d)",
            "cur AS (SELECT * FROM v_monthly_cost_components WHERE NOT is_complete_month ORDER BY month DESC LIMIT 1)",
            "c AS (SELECT v.* FROM v_monthly_cost_components v JOIN ref ON v.month = ref.m)",
            "cp AS (SELECT v.* FROM v_monthly_cost_components v JOIN ref ON v.month = add_months(ref.m, -1))",
            "fb AS (SELECT total_usd FROM v_fy_forecast_total WHERE scenario = 'Base' AND NOT in_promo ORDER BY month LIMIT 1)"]
datasets.append({"name": "ds_p10_obs", "displayName": "Passo 10 — observações", "queryLines": obs(
    P10_CTES,
    [("fr CROSS JOIN ref", f"concat('Dados das system tables processados até ', date_format(fr.d, 'dd/MM/yyyy'), '. Mês de referência (último completo): ', {MES}, '. Os agregados são recalculados pelo job genie-finops-build-views (agendado diariamente às 06:00 BRT).')"),
     ("cur CROSS JOIN fr", f"concat('Mês corrente (', date_format(cur.month, 'MM/yyyy'), ', parcial): ', {U('cur.total_post_promo_usd')}, ' até agora com as regras de fev/2027. Projeção linear para o mês inteiro: ', {U('cur.total_post_promo_usd / day(fr.d) * day(last_day(cur.month))')}, '.')"),
     ("c CROSS JOIN cp", f"concat('Custo pós-promoção do mês de referência vs mês anterior: ', {SP('c.total_post_promo_usd / cp.total_post_promo_usd - 1')}, '. Compare com o crescimento mensal do cenário Base (Passo 7).')"),
     ("fb", f"concat('Previsão do cenário Base para fev/2027 (primeiro mês cobrado): ', {U('fb.total_usd')}, '. A partir de mar/2027, compare o real com esse valor todo mês e recalibre os cenários.')"),
     ("fb", "'Rotina mensal sugerida: atualizar e publicar o dashboard, enviar por assinatura a FinOps e às áreas, revisar os top usuários, SPs e Agents com maior custo por pergunta, e ajustar premissas e budgets.'"),
     ])})


# ================================================================ widget helpers
def text(name, md, x, y, w, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [md]}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def frame(title, desc=None):
    f = {"title": title, "showTitle": True}
    if desc:
        f.update({"description": desc, "showDescription": True})
    return f


def counter(name, ds_name, field, title, fmt, x, y, w=3, h=3, filters=None, desc=None):
    query = {"datasetName": ds_name, "fields": [{"name": f"sum({field})", "expression": f"SUM(`{field}`)"}], "disaggregated": False}
    if filters:
        query["filters"] = [{"expression": f} for f in filters]
    value = {"fieldName": f"sum({field})", "displayName": title}
    if fmt:
        value["format"] = fmt
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": query}],
                       "spec": {"version": 2, "widgetType": "counter", "encodings": {"value": value}, "frame": frame(title, desc)}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def chart(name, kind, ds_name, x_field, y_field, title, x, y, w=6, h=6, color=None, color_map=None, y_fmt=USD,
          x_type="temporal", agg="SUM", filters=None, layout=None, desc=None, horizontal=False, annotations=None,
          y_label=None, color_label=None, x_label=None):
    fields = []
    if x_type == "temporal":
        x_name = f"monthly({x_field})"
        fields.append({"name": x_name, "expression": f'DATE_TRUNC("MONTH", `{x_field}`)'})
    else:
        x_name = x_field
        fields.append({"name": x_name, "expression": f"`{x_field}`"})
    y_name = f"{agg.lower()}({y_field})"
    fields.append({"name": y_name, "expression": f"{agg}(`{y_field}`)"})
    if color:
        fields.append({"name": color, "expression": f"`{color}`"})
    query = {"datasetName": ds_name, "fields": fields, "disaggregated": False}
    if filters:
        query["filters"] = [{"expression": f} for f in filters]
    x_enc = {"fieldName": x_name, "scale": {"type": x_type}, "displayName": x_label or ("Mês" if x_type == "temporal" else x_field)}
    if x_type == "categorical":
        x_enc["scale"]["sort"] = {"by": "value"} if horizontal else {"by": "alphabetical"}
    is_usd = bool(y_fmt) and y_fmt.get("type") == "number-currency"
    y_enc = {"fieldName": y_name, "scale": {"type": "quantitative"}, "displayName": y_label or ("US$" if is_usd else "DBUs")}
    if y_fmt:
        y_enc["format"] = y_fmt
    enc = {"x": x_enc, "y": y_enc}
    if horizontal:
        x_enc["scale"] = {"type": "categorical", "sort": {"by": "value"}}
        enc = {"y": x_enc, "x": y_enc}
    if color:
        c = {"fieldName": color, "scale": {"type": "categorical"}, "displayName": color_label or color}
        if color_map:
            c["scale"]["mappings"] = color_map
        enc["color"] = c
    spec = {"version": 3, "widgetType": kind, "encodings": enc, "frame": frame(title, desc)}
    if layout:
        spec["mark"] = {"layout": layout}
    if annotations:
        spec["annotations"] = annotations
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": query}], "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def table(name, ds_name, cols, title, x, y, w=12, h=6, desc=None):
    fields = [{"name": c[0], "expression": f"`{c[0]}`"} for c in cols]
    columns = []
    for c in cols:
        col = {"fieldName": c[0], "displayName": c[1]}
        if len(c) > 2 and c[2]:
            col["format"] = c[2]
        columns.append(col)
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {
        "datasetName": ds_name, "fields": fields, "disaggregated": True}}],
        "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": columns}, "frame": frame(title, desc)}},
        "position": {"x": x, "y": y, "width": w, "height": h}}


def observations(step, x, y, w=8, h=6):
    """Text list rendered with Vega-Lite (table cells do not wrap long sentences)."""
    vl = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "data": {"name": "databricks_query"},
        "width": "container", "height": "container",
        "config": {"autosize": {"type": "fit", "contains": "padding"}, "view": {"stroke": None}},
        "mark": {"type": "text", "align": "left", "baseline": "top", "lineBreak": "\n", "lineHeight": LINE_PX,
                 "fontSize": 13, "color": {"expr": "colors.textPrimary.default"}},
        "encoding": {"x": {"value": 2}, "y": {"field": "y_px", "type": "quantitative", "scale": None},
                     "text": {"field": "texto", "type": "nominal"},
                     "tooltip": {"field": "observacao", "type": "nominal", "title": "Observação"}},
    }
    fields = ["ordem", "texto", "observacao", "y_px"]
    return {"widget": {"name": f"p{step}_obs",
                       "queries": [{"name": "main_query", "query": {
                           "datasetName": f"ds_p{step}_obs",
                           "fields": [{"name": f, "expression": f"`{f}`"} for f in fields], "disaggregated": True}}],
                       "spec": {"version": 1, "widgetType": "custom-vega-viz",
                                "jsonSpec": {"type": "vega-lite", "spec": json.dumps(vl, ensure_ascii=False)},
                                "encodings": {"fields": [{"fieldName": f} for f in fields]},
                                "data": {"queryName": "main_query"},
                                "frame": frame("🔎 O que os dados mostram",
                                               "Frases calculadas automaticamente a partir das system tables (mês de referência = último mês completo)")}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def step_header(step, title, section, goal, how_to_read, h_head=2, h_body=6):
    """Header (full width) + 'Como ler' box (left, w=4) + observations table (right, w=8). Returns (widgets, next_y)."""
    head = text(f"p{step}_head",
                f"## Passo {step} — {title}\n"
                f"**Objetivo:** {goal}  \n"
                f"_Guia: seção {section} · ← " + ("Introdução" if step == 1 else f"Passo {step - 1}") + (f" · Passo {step + 1} →_" if step < 10 else "_"),
                0, 0, 12, h_head)
    how = text(f"p{step}_how", "### 📖 Como ler esta aba\n" + how_to_read, 0, h_head, 4, h_body)
    return [head, how, observations(step, 4, h_head, 8, h_body)], h_head + h_body


PROMO_LINE = [{"type": "vertical-line", "encodings": {
    "x": {"dataValue": "2027-01-31T12:00:00.000", "dataType": "DATETIME"},
    "label": {"value": "Fim da promoção (31/01/2027)"},
    "color": {"value": {"hex": "#FF7E5C"}}}}]

# ================================================================ pages
pages = []


def page(name, display, layout):
    pages.append({"name": name, "displayName": display, "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": layout})


# ---------- 0 · Introdução
intro = [
    text("p0_title",
         "# Guia de Previsão de Gastos com Genie — passo a passo (Passos 1 a 10)\n"
         "Este dashboard segue, aba por aba, o **Guia de Previsão de Gastos com Genie (Próximo Ano Fiscal)** (`docs/GUIA_PREVISAO_GENIE_ptBR.md`). "
         "Cada aba corresponde a um passo do guia e traz o **objetivo**, um quadro **Como ler**, as **observações calculadas a partir dos dados** "
         "e os gráficos que sustentam cada conclusão. Todos os números vêm das system tables do próprio workspace: nenhum dado é simulado.",
         0, 0, 12, 3),
    counter("p0_k1", "ds_p0_kpi", "total_today_usd", "Custo Genie hoje (último mês completo)", USD, 0, 3,
            desc="LLM faturado + SQL warehouse atribuído"),
    counter("p0_k2", "ds_p0_kpi", "total_post_promo_usd", "Mesmo uso com regras de fev/2027", USD, 3, 3,
            desc="Passo 3 + Passo 5"),
    counter("p0_k3", "ds_p0_kpi", "multiplier", "Multiplicador (fev/2027 ÷ hoje)", X, 6, 3,
            desc="Quantas vezes o custo mensal aumenta"),
    counter("p0_k4", "ds_p0_kpi", "fy_base_usd", "Previsão FY2027 — cenário Base", USD, 9, 3,
            desc="Passo 7, com margem de segurança"),
    text("p0_rules",
         "### O que muda em 01/02/2027\n"
         "| Componente | Até 31/01/2027 | A partir de 01/02/2027 |\n"
         "|---|---|---|\n"
         "| Genie Agents e Genie One (pessoas) | Gratuito (`GENIE_FREE_USAGE`) | Cobrado acima da franquia |\n"
         "| Genie Code | Cobrado acima da franquia, com 25% de desconto | Cobrado acima da franquia, sem desconto |\n"
         "| Service principals | Sempre cobrado, sem franquia | Sempre cobrado, sem franquia |\n"
         "| Franquia | 150 DBUs/usuário/mês, só Genie Code consome | 150 DBUs/usuário/mês **compartilhados** por Code, One e Agents |\n"
         "| SQL warehouse | Cobrado (DBSQL) | Cobrado (DBSQL), fora do budget do Genie |\n",
         0, 6, 7, 7),
    text("p0_map",
         "### Roteiro das abas\n"
         "1. **SKU e preço**: quanto custa um DBU\n"
         "2. **Linha de base**: quanto consumimos hoje\n"
         "3. **Reprecificar**: o mesmo uso com as regras de fev/2027\n"
         "4. **Personas**: quem consome\n"
         "5. **SQL warehouse**: o custo fora do LLM\n"
         "6. **Custos unitários**: custo por pergunta e por usuário\n"
         "7. **Projeção FY**: cenários Conservador, Base e Agressivo\n"
         "8. **Novos casos de uso**: o que ainda não tem histórico\n"
         "9. **Controles**: budgets antes de 01/02/2027\n"
         "10. **Operacionalizar**: acompanhamento mensal",
         7, 6, 5, 7),
    text("p0_note",
         "_Mês de referência = último mês completo. O primeiro mês do histórico (julho/2026, a partir de 20/07) é parcial e fica fora dos gráficos mensais. "
         "Valores em US$ com o desconto contratual e os adicionais configurados em `forecast_assumptions` (Passo 1). "
         "Para a visão consolidada por tema, use o dashboard **Genie FinOps & Previsão FY2027**._",
         0, 13, 12, 2),
]
page("p00_intro", "0 · Introdução", intro)

# ---------- Passo 1
w, y = step_header(1, "Identificar o SKU e o preço unitário", "3",
                   "descobrir em qual SKU (Serverless Real-Time Inference, SRTI) o Genie será cobrado e qual preço por DBU usar na previsão.",
                   "- O preço vem de `system.billing.list_prices`, nunca de um valor fixo.\n"
                   "- **P_net = P_list × (1 − desconto contratual)**. O desconto não está nas system tables: vem do time comercial.\n"
                   "- Se houver adicional de plataforma (ex.: ESC), ele é aplicado depois do desconto.\n"
                   "- Esse preço é usado em todos os passos seguintes.")
w += [
    counter("p1_k1", "ds_p1_price", "srti_list_price", "Preço de lista (US$/DBU)", USD4, 0, y),
    counter("p1_k2", "ds_p1_price", "contract_discount_srti", "Desconto contratual SRTI", PCT, 3, y,
            desc="Editável em forecast_assumptions"),
    counter("p1_k3", "ds_p1_price", "srti_net_price_with_addon", "Preço líquido usado (US$/DBU)", USD4, 6, y,
            desc="Com desconto e adicional"),
    counter("p1_k4", "ds_p1_price", "allowance_value_usd", "Valor da franquia (US$/usuário/mês)", USD2, 9, y,
            desc="150 DBUs × preço de lista"),
    table("p1_skus", "ds_p1_skus", [("sku_name", "SKU"), ("cloud", "Cloud"), ("billed_by_genie", "Faturado pelo Genie?"),
                                    ("last_usage_date", "Último uso")],
          "SKUs SRTI encontrados na conta (system.billing.usage)", 0, y + 3, 12, 5,
          desc="O modelo usa o SKU faturado pelo Genie mais recente. Vários SKUs indicam workspaces em várias regiões."),
]
page("p01_sku", "1 · SKU e preço", w)

# ---------- Passo 2
w, y = step_header(2, "Linha de base: DBUs mensais por produto e identidade", "4",
                   "medir quanto o Genie consome hoje, separando produto (Agents, One, Code), tipo de identidade e o que é gratuito ou já faturado.",
                   "- **Gratuito hoje** (`GENIE_FREE_USAGE`) em Agents/One é o volume que **passa a ser cobrável** em fev/2027.\n"
                   "- **Faturado hoje** por service principals já é custo real.\n"
                   "- DBUs **a taxa cheia** = gratuito + faturado ÷ 0,75 (remove o desconto de 25%).\n"
                   "- Humano vs SP: `run_as` com `@` = pessoa. Valide com a lista de SPs.")
w += [
    counter("p2_k1", "ds_p2_kpi", "total_dbus", "DBUs no mês (taxa cheia)", NUM, 0, y),
    counter("p2_k2", "ds_p2_kpi", "free_agents_one_dbus", "DBUs gratuitos Agents/One", NUM, 3, y,
            desc="Viram cobráveis em fev/2027"),
    counter("p2_k3", "ds_p2_kpi", "humans", "Usuários humanos ativos", INT, 6, y),
    counter("p2_k4", "ds_p2_kpi", "sps", "Service principals ativos", INT, 9, y),
    chart("p2_surface", "bar", "ds_p2", "month", "full_rate_dbus", "DBUs por produto Genie (taxa cheia)", 0, y + 3,
          color="surface", color_map=SURFACE_COLORS, y_fmt=NUM, color_label="Produto",
          desc="Agents e One são gratuitos hoje para pessoas; Code já é cobrado acima da franquia"),
    chart("p2_fb", "bar", "ds_p2_fb", "month", "dbus", "DBUs gratuitos vs faturados hoje", 6, y + 3,
          color="sku_type", y_fmt=NUM, color_label="SKU",
          color_map=[{"value": "Gratuito hoje (GENIE_FREE_USAGE)", "color": "#99DDB4"},
                     {"value": "Faturado hoje (SRTI, com 25% off)", "color": "#1D425C"}],
          desc="Valores como registrados no billing (faturado ainda com o desconto de 25%)"),
    chart("p2_identity", "bar", "ds_p2", "month", "billed_dbus", "DBUs já faturados hoje, por tipo de identidade", 0, y + 9,
          color="identity_type", color_map=IDENTITY_COLORS, y_fmt=NUM, color_label="Identidade",
          desc="Service principals não têm franquia nem gratuidade"),
    chart("p2_channel", "bar", "ds_p2", "month", "full_rate_dbus", "DBUs por canal (UI vs API)", 6, y + 9,
          color="channel", y_fmt=NUM, color_label="Canal",
          color_map=[{"value": "UI", "color": "#4E79A7"}, {"value": "API", "color": "#FF7054"}],
          desc="API = apps, integrações e MCP, onde é comum o uso de service principals"),
]
page("p02_baseline", "2 · Linha de base", w)

# ---------- Passo 3
w, y = step_header(3, "Reprecificar o histórico pelas regras pós-01/02/2027", "5",
                   "calcular quanto cada mês do histórico teria custado se as regras de fev/2027 já estivessem valendo.",
                   "- Pessoas: **cobrável = max(0, DBUs do mês em todos os produtos − 150)**, por usuário.\n"
                   "- Service principals: **cobrável = todos os DBUs**.\n"
                   "- Sem desconto promocional de 25%.\n"
                   "- A franquia é aplicada **por usuário e por mês**: nunca sobre o total.")
w += [
    counter("p3_k1", "ds_p3_kpi", "cost_today_usd", "LLM hoje (mês de ref.)", USD, 0, y),
    counter("p3_k2", "ds_p3_kpi", "cost_post_promo_usd", "LLM com regras de fev/2027", USD, 3, y),
    counter("p3_k3", "ds_p3_kpi", "multiplier", "Multiplicador", X, 6, y, desc="fev/2027 ÷ hoje"),
    counter("p3_k4", "ds_p3_kpi", "pct_above", "% de usuários acima da franquia", PCT, 9, y),
    chart("p3_cost", "bar", "ds_p3_cost", "month", "usd", "Custo de LLM: hoje vs regras de fev/2027 (US$)", 0, y + 3,
          color="basis", layout="group", color_label="Base de cálculo",
          color_map=[{"value": "1. Custo de LLM hoje (regras atuais)", "color": "#4E79A7"},
                     {"value": "2. Mesmo uso com as regras de fev/2027", "color": "#FF7054"}],
          desc="A diferença entre as barras é o impacto do fim da gratuidade e da promoção"),
    chart("p3_dbus", "bar", "ds_p3_dbus", "month", "dbus", "Efeito da franquia sobre os DBUs de pessoas", 6, y + 3,
          color="kind", layout="group", y_fmt=NUM, color_label="DBUs",
          color_map=[{"value": "1. DBUs brutos (taxa cheia)", "color": "#99DDB4"},
                     {"value": "2. DBUs cobráveis após a franquia", "color": "#1D425C"}],
          desc="A distância entre as barras é o que a franquia de 150 DBUs/usuário absorve"),
    table("p3_tbl", "ds_p3", [("month", "Mês"), ("identity_type", "Identidade"), ("identities", "Identidades", INT),
                              ("gross_dbus", "DBUs brutos", NUM), ("billable_dbus_post_promo", "DBUs cobráveis", NUM),
                              ("humans_above_allowance", "Acima da franquia", INT), ("cost_today_usd", "Custo hoje", USD),
                              ("cost_post_promo_usd", "Custo regras fev/2027", USD)],
          "Simulação mês a mês (resultado da query do Passo 3 do guia)", 0, y + 9, 12, 5),
]
page("p03_reprice", "3 · Reprecificar", w)

# ---------- Passo 4
w, y = step_header(4, "Segmentar os usuários em personas", "6",
                   "entender quem consome: poucos usuários intensivos costumam concentrar a maior parte do custo.",
                   "- Personas por percentil do mês: **Iniciante** (≤ p50), **Praticante** (p50–p90), **Intensivo** (> p90).\n"
                   "- **Desenvolvedor**: mais da metade dos DBUs em Genie Code.\n"
                   "- Os percentis da sua organização definem os limites por usuário do budget (Passo 9).\n"
                   "- Confirme com as áreas o uso dos top 20.")
w += [
    counter("p4_k1", "ds_p4_kpi", "p50_dbus", "p50 de DBUs por usuário", NUM, 0, y),
    counter("p4_k2", "ds_p4_kpi", "p90_dbus", "p90 de DBUs por usuário", NUM, 3, y),
    counter("p4_k3", "ds_p4_kpi", "p99_dbus", "p99 de DBUs por usuário", NUM, 6, y),
    counter("p4_k4", "ds_p4_kpi", "top10pct", "Custo dos 10% maiores usuários", PCT, 9, y, desc="% do custo de LLM de pessoas"),
    chart("p4_users", "bar", "ds_p4_persona", "month", "users", "Usuários ativos por persona", 0, y + 3,
          color="persona", y_fmt=NUM, color_label="Persona", y_label="Usuários"),
    chart("p4_cost", "bar", "ds_p4_persona", "month", "cost_post_promo_usd", "Custo de LLM pós-promoção por persona (US$)", 6, y + 3,
          color="persona", color_label="Persona",
          desc="Compare com o gráfico ao lado: muitos usuários, pouco custo; poucos usuários, muito custo"),
    chart("p4_band", "bar", "ds_p4_band", "dbu_band", "users", "Usuários por faixa de DBUs no mês de referência", 0, y + 9,
          color="persona", x_type="categorical", y_fmt=NUM, color_label="Persona", y_label="Usuários", x_label="DBUs no mês",
          desc="Quem está na faixa 0–150 não paga LLM"),
    table("p4_stats", "ds_p4_persona_ref", [("persona", "Persona"), ("users", "Usuários", INT), ("p50_dbus", "p50 DBUs", NUM),
                                            ("p90_dbus", "p90 DBUs", NUM), ("users_within_free", "Na franquia", INT),
                                            ("cost_per_user_usd", "Custo/usuário", USD2), ("cost_post_promo_usd", "Custo total", USD)],
          "Percentis e custo por persona (mês de referência)", 6, y + 9, 6, 6),
    table("p4_top", "ds_p4_top", [("identity", "Identidade"), ("identity_type", "Tipo"), ("persona", "Persona"),
                                  ("full_rate_dbus", "DBUs", NUM), ("agents_dbus", "Agents", NUM), ("one_dbus", "One", NUM),
                                  ("code_dbus", "Code", NUM), ("billable_dbus_post_promo", "Cobráveis", NUM),
                                  ("cost_post_promo_usd", "Custo regras fev/2027", USD)],
          "Top 20 identidades por custo pós-promoção (validar com as áreas)", 0, y + 15, 12, 7),
]
page("p04_personas", "4 · Personas", w)

# ---------- Passo 5
w, y = step_header(5, "Atribuir a computação do SQL warehouse ao Genie", "7",
                   "somar o custo do SQL warehouse que executa as queries geradas pelo Genie, que fica fora da linha de LLM e do budget do Genie.",
                   "- Queries de Genie Agents são identificadas por `query_source.genie_space_id` em `system.query.history`.\n"
                   "- O custo do warehouse é **rateado pelo tempo de task** entre Genie e outras cargas.\n"
                   "- Warehouse **dedicado** ao Genie = atribuição exata (recomendado).\n"
                   "- Genie One não traz `genie_space_id`: aparece como não-Genie.")
w += [
    counter("p5_k1", "ds_p5_kpi", "genie_warehouse_usd", "Warehouse atribuído ao Genie", USD, 0, y, desc="Mês de referência"),
    counter("p5_k2", "ds_p5_kpi", "wh_share", "Peso do warehouse no custo total", PCT, 3, y, desc="Sobre o custo pós-promoção"),
    counter("p5_k3", "ds_p5_kpi", "warehouses", "Warehouses com queries do Genie", INT, 6, y),
    counter("p5_k4", "ds_p5_kpi", "dedicated", "Warehouses dedicados (≥ 95%)", INT, 9, y),
    chart("p5_trend", "bar", "ds_p5_trend", "month", "usd", "LLM vs SQL warehouse por mês (US$, regras de fev/2027)", 0, y + 3,
          color="component", color_label="Componente",
          color_map=[{"value": "1. LLM (regras pós-promoção)", "color": "#1D425C"},
                     {"value": "2. SQL warehouse atribuído ao Genie", "color": "#FFA600"}]),
    chart("p5_top", "bar", "ds_p5_top", "agent_name", "attributed_net_cost_usd", "Top 15 Genie Agents por custo de warehouse (US$)", 6, y + 3,
          x_type="categorical", horizontal=True, x_label="Genie Agent",
          desc="Nome = workspace / id do Genie Agent (as system tables não trazem o título)"),
    table("p5_wh", "ds_p5_wh", [("warehouse_name", "Warehouse"), ("wh_type", "Tipo"), ("agents", "Genie Agents", INT),
                                ("genie_queries", "Queries Genie", INT), ("genie_share", "% do tempo de task", PCT),
                                ("genie_cost_usd", "Custo atribuído ao Genie", USD), ("warehouse_cost_usd", "Custo total do warehouse", USD)],
          "Warehouses que executam queries do Genie (mês de referência)", 0, y + 9, 12, 6,
          desc="Compartilhado = o rateio é estimativa; considere separar os Genie Agents de produção"),
]
page("p05_warehouse", "5 · SQL warehouse", w)

# ---------- Passo 6
w, y = step_header(6, "Montar custos unitários", "8",
                   "transformar custo em indicadores de negócio (custo por pergunta e por usuário ativo) para projetar a partir de usuários, Agents e perguntas.",
                   "- Perguntas e usuários vêm de `system.access.audit` (serviço `aibiGenie`).\n"
                   "- **Custo por pergunta** = LLM por pergunta + warehouse por pergunta.\n"
                   "- **Custo por usuário ativo** = (LLM cobrável + warehouse) ÷ usuários ativos.\n"
                   "- Custo por pergunta alto aponta Agent mode intenso, instruções ou metadados fracos ou warehouse grande demais.")
w += [
    counter("p6_k1", "ds_p6_kpi", "questions", "Perguntas no mês", NUM, 0, y),
    counter("p6_k2", "ds_p6_kpi", "agent_mode_share", "% em Agent mode", PCT, 3, y),
    counter("p6_k3", "ds_p6_kpi", "cost_per_question_usd", "Custo médio por pergunta", USD3, 6, y, desc="LLM + warehouse"),
    counter("p6_k4", "ds_p6_kpi", "cost_per_active_user_usd", "Custo por usuário ativo/mês", USD2, 9, y, desc="LLM cobrável + warehouse"),
    chart("p6_cpq", "bar", "ds_p6_unit", "agent_name", "total_cost_per_question_usd", "Custo por pergunta (US$): 25 Agents com mais perguntas",
          0, y + 3, 12, 7, x_type="categorical", horizontal=True, agg="AVG", y_fmt=USD2, x_label="Genie Agent",
          desc="O componente de LLM é a média da conta; a diferença entre Agents vem do warehouse"),
    table("p6_tbl", "ds_p6_unit", [("agent_name", "Genie Agent"), ("questions", "Perguntas", INT), ("agent_mode_share", "% Agent mode", PCT),
                                   ("active_identities", "Identidades ativas", INT), ("llm_dbus_per_question", "DBUs LLM/pergunta", NUM),
                                   ("llm_cost_per_question_usd", "LLM/pergunta", USD3), ("warehouse_cost_per_question_usd", "Warehouse/pergunta", USD3),
                                   ("total_cost_per_question_usd", "Total/pergunta", USD3), ("warehouse_net_cost_usd", "Warehouse no mês", USD)],
          "Economia unitária por Genie Agent (mês de referência)", 0, y + 10, 12, 7),
]
page("p06_unit", "6 · Custos unitários", w)

# ---------- Passo 7
w, y = step_header(7, "Projetar o próximo ano fiscal", "9",
                   "projetar mês a mês o custo do FY2027 em três cenários, a partir do run-rate dos Passos 3 e 5.",
                   "- **Custo(m) = LLM de pessoas acima da franquia + LLM de SPs + warehouse + novos casos de uso**, × (1 + adicional).\n"
                   "- **Jan/2027** ainda é promocional: só Genie Code (com 25% off) e SPs são cobrados.\n"
                   "- A partir de **fev/2027** valem as novas regras.\n"
                   "- Crescimentos e margem estão nas tabelas de premissas (`forecast_scenarios`, `forecast_assumptions`).")
w += [
    counter("p7_k1", "ds_p7_tot", "total_with_headroom_usd", "FY2027 — Conservador", USD, 0, y, 4, 3, filters=["`scenario` = 'Conservador'"],
            desc="Run-rate atual, sem crescimento"),
    counter("p7_k2", "ds_p7_tot", "total_with_headroom_usd", "FY2027 — Base", USD, 4, y, 4, 3, filters=["`scenario` = 'Base'"],
            desc="Plano de expansão das áreas"),
    counter("p7_k3", "ds_p7_tot", "total_with_headroom_usd", "FY2027 — Agressivo", USD, 8, y, 4, 3, filters=["`scenario` = 'Agressivo'"],
            desc="População-alvo completa"),
    chart("p7_line", "line", "ds_p7_fc", "month", "total_with_headroom_usd", "Custo mensal previsto por cenário (US$, com margem)", 0, y + 3,
          color="scenario", color_map=SCENARIO_COLORS, annotations=PROMO_LINE, color_label="Cenário",
          desc="O salto entre jan e fev/2027 é o fim da gratuidade de Agents e One"),
    chart("p7_comp", "bar", "ds_p7_long", "month", "usd", "Cenário Base por componente (US$, sem margem)", 6, y + 3,
          color="component", color_map=COMPONENT_COLORS, filters=["`scenario` = 'Base'"], color_label="Componente",
          annotations=PROMO_LINE),
    table("p7_tot", "ds_p7_tot", [("scenario", "Cenário"), ("human_usage_growth_m", "Cresc. pessoas/mês", PCT),
                                  ("sp_growth_m", "Cresc. SPs/mês", PCT), ("warehouse_growth_m", "Cresc. warehouse/mês", PCT),
                                  ("human_llm_usd", "LLM pessoas", USD), ("sp_llm_usd", "LLM SPs", USD),
                                  ("genie_warehouse_usd", "SQL warehouse", USD), ("new_use_cases_usd", "Novos UCs", USD),
                                  ("total_usd", "Total", USD), ("total_with_headroom_usd", "Total com margem", USD)],
          "Premissas e totais do ano fiscal por cenário", 0, y + 9, 12, 4),
    table("p7_month", "ds_p7_fc", [("scenario", "Cenário"), ("month", "Mês"), ("in_promo", "Promoção?"),
                                   ("human_llm_usd", "LLM pessoas", USD), ("sp_llm_usd", "LLM SPs", USD),
                                   ("genie_warehouse_usd", "Warehouse", USD), ("new_use_cases_usd", "Novos UCs", USD),
                                   ("total_usd", "Total", USD), ("total_with_headroom_usd", "Total com margem", USD)],
          "Previsão mensal (modelo do Apêndice A do guia)", 0, y + 13, 12, 7),
]
page("p07_forecast", "7 · Projeção FY", w)

# ---------- Passo 8
w, y = step_header(8, "Dimensionar novos casos de uso sem histórico", "10",
                   "estimar o custo de Genie Agents planejados para o próximo ano, que ainda não aparecem nas system tables.",
                   "- **Opção 1 (mais confiável):** piloto de 2 a 4 semanas, medido com os Passos 2 a 6.\n"
                   "- **Opção 2:** calculadora de sizing da Databricks (só LLM; sem SQL nem Genie Code).\n"
                   "- **Opção 3:** analogia com o custo por pergunta ou por usuário dos Agents atuais (tabelas abaixo).\n"
                   "- Lance o resultado em `forecast_scenarios.new_uc_usd_m`.")
w += [
    table("p8_analogy", "ds_p8_analogy", [("questions_per_month", "Perguntas/mês", INT), ("cost_per_question_usd", "Custo/pergunta atual", USD3),
                                          ("monthly_usd", "Custo mensal estimado", USD), ("fy_usd", "Custo no FY (meses cobrados)", USD)],
          "Analogia por volume: novo Genie Agent com N perguntas/mês", 0, y, 6, 5,
          desc="Custo médio por pergunta do mês de referência (LLM + warehouse)"),
    table("p8_persona", "ds_p8_persona", [("persona", "Persona"), ("cost_per_user_usd", "Custo/usuário/mês", USD2),
                                          ("monthly_100_users_usd", "100 usuários/mês", USD), ("fy_100_users_usd", "100 usuários no FY", USD)],
          "Analogia por persona: 100 novos usuários", 6, y, 6, 5,
          desc="Só LLM (acima da franquia), sem warehouse. Some o warehouse pelo custo por pergunta."),
    table("p8_scen", "ds_p8_scen", [("scenario", "Cenário"), ("new_uc_usd_m", "Novos UCs: US$/mês (acumulativo)", USD2),
                                    ("description", "Descrição")],
          "Valor atual de novos casos de uso nas premissas", 0, y + 5, 12, 4,
          desc="Ex.: UPDATE forecast_scenarios SET new_uc_usd_m = 2000 WHERE scenario = 'Base'"),
]
page("p08_new_uc", "8 · Novos casos de uso", w)

# ---------- Passo 9
w, y = step_header(9, "Implementar controles antes de 01/02/2027", "11",
                   "configurar budgets e boas práticas de identidade e warehouse para que o custo não surpreenda depois do fim da promoção.",
                   "- Budget: Account Console → *Usage → Budgets* → **Unity Gateway**, tag `databricks-product = genie`.\n"
                   "- **Pool compartilhado:** só alerta (80% e 100%), sem bloqueio.\n"
                   "- **Limite por usuário:** com bloqueio, a partir dos percentis do Passo 4.\n"
                   "- Budgets trabalham a **preço de lista** (sem o desconto contratual): os valores abaixo já estão a preço de lista.\n"
                   "- Até 31/01/2027 limites por usuário não afetam Agents/One: revise-os em jan/2027.", h_body=7)
w += [
    counter("p9_k1", "ds_p9_kpi", "pool_100_usd", "Pool mensal sugerido (100%)", USD, 0, y, desc="LLM do cenário Base em fev/2027, preço de lista"),
    counter("p9_k2", "ds_p9_kpi", "pool_80_usd", "Alerta em 80%", USD, 3, y),
    counter("p9_k3", "ds_p9_kpi", "user_limit_usd", "Limite padrão por usuário", USD2, 6, y, desc="p90, acima da franquia"),
    counter("p9_k4", "ds_p9_kpi", "power_limit_usd", "Limite do grupo power users", USD2, 9, y, desc="p99, acima da franquia"),
    text("p9_controls",
         "### Controles recomendados\n"
         "| Controle | Recomendação |\n|---|---|\n"
         "| Budget do Genie | Criar já. Na promoção acompanha o Genie Code; a partir de 01/02 cobre também Agents e One |\n"
         "| Pool compartilhado | Só alerta em 80% e 100% (bloquear afeta todos) |\n"
         "| Limite por usuário | Padrão com bloqueio, a partir do p90 |\n"
         "| Overrides | Um grupo por persona (ex.: `genie-power-users`), com aprovação |\n"
         "| Webhooks / e-mail | Para FinOps e para o responsável da área |\n"
         "| Warehouses dedicados | Um serverless por área para Genie Agents |\n"
         "| Identidade | Preferir OBO a service principal em apps para usuários |\n",
         0, y + 3, 6, 7),
    table("p9_persona", "ds_p9_persona", [("persona", "Persona"), ("users", "Usuários", INT), ("p90_dbus", "p90 DBUs", NUM),
                                          ("suggested_limit_list_usd", "Limite sugerido (US$ lista/mês)", USD2)],
          "Limite por usuário sugerido para cada persona (override por grupo)", 6, y + 3, 6, 7,
          desc="(p90 da persona − 150) × preço de lista × (1 + adicional)"),
    table("p9_sp", "ds_p9_sp", [("identity", "Service principal"), ("full_rate_dbus", "DBUs", NUM), ("agents_dbus", "Agents", NUM),
                                ("one_dbus", "One", NUM), ("code_dbus", "Code", NUM), ("cost_today_usd", "Custo hoje", USD),
                                ("cost_post_promo_usd", "Custo regras fev/2027", USD)],
          "Top 10 service principals: candidatos a migrar para OBO", 0, y + 10, 12, 6,
          desc="Uso por SP é 100% cobrado e não tem atribuição por pessoa"),
]
page("p09_controls", "9 · Controles", w)

# ---------- Passo 10
w, y = step_header(10, "Operacionalizar: acompanhamento mensal", "12",
                   "transformar a previsão em rotina: comparar todo mês o real com o previsto e agir sobre os maiores desvios.",
                   "- Agende o refresh mensal do dashboard e uma **assinatura** para FinOps e responsáveis das áreas.\n"
                   "- Compare o **real** com o **previsto** e recalibre os cenários, principalmente depois de fev/2027.\n"
                   "- Revise os Agents com maior custo por pergunta e as identidades que mais cresceram.\n"
                   "- Ajuste premissas (Passo 7) e limites (Passo 9).")
w += [
    chart("p10_track", "line", "ds_p10_track", "month", "usd", "Real vs previsto (US$/mês, sem margem)", 0, y, 12, 7,
          color="series", color_label="Série", annotations=PROMO_LINE,
          color_map=[{"value": "1. Real — faturado hoje", "color": "#4E79A7"},
                     {"value": "2. Real — regras de fev/2027", "color": "#1D425C"},
                     {"value": "3. Previsto — Conservador", "color": "#99DDB4"},
                     {"value": "3. Previsto — Base", "color": "#FFA600"},
                     {"value": "3. Previsto — Agressivo", "color": "#DE5582"}],
          desc="A partir de mar/2027, a série real com as novas regras deve ficar entre os cenários previstos"),
    table("p10_agents", "ds_p10_agents", [("agent_name", "Genie Agent"), ("questions", "Perguntas", INT),
                                          ("agent_mode_share", "% Agent mode", PCT), ("total_cost_per_question_usd", "Custo/pergunta", USD3),
                                          ("warehouse_net_cost_usd", "Warehouse no mês", USD)],
          "Top 10 Agents com maior custo por pergunta (≥ 20 perguntas)", 0, y + 7, 6, 7,
          desc="Revisar instruções, uso de Agent mode e tamanho do warehouse"),
    table("p10_movers", "ds_p10_movers", [("identity", "Identidade"), ("identity_type", "Tipo"), ("prev_usd", "Mês anterior", USD),
                                          ("cur_usd", "Mês de ref.", USD), ("delta_usd", "Aumento", USD)],
          "Top 10 identidades que mais cresceram (custo com regras de fev/2027)", 6, y + 7, 6, 7,
          desc="Confirmar com a área se o crescimento é esperado"),
]
page("p10_ops", "10 · Operacionalizar", w)

# Counters with title + caption need height 4: grow each counter row and push everything below it down by 1.
for _p in pages:
    _rows = sorted({w_["position"]["y"] for w_ in _p["layout"]
                    if w_["widget"].get("spec", {}).get("widgetType") == "counter" and w_["position"]["height"] == 3
                    and w_["widget"]["spec"]["frame"].get("showDescription")}, reverse=True)
    for _y0 in _rows:
        for w_ in _p["layout"]:
            pos = w_["position"]
            if pos["y"] >= _y0 + 3:
                pos["y"] += 1
            elif pos["y"] == _y0 and w_["widget"].get("spec", {}).get("widgetType") == "counter":
                pos["height"] = 4

dashboard = {
    "datasets": datasets,
    "pages": pages,
    "uiSettings": {"theme": {
        "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
        "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
        "widgetBorderColor": {"light": "#FFFFFF", "dark": "#11171C"},
        "fontColor": {"light": "#11171C", "dark": "#E8ECF0"},
        "selectionColor": {"light": "#2272B4", "dark": "#8ACAFF"},
        "visualizationColors": ["#1D425C", "#FFA600", "#DE5582", "#4E79A7", "#995495", "#FF7054", "#99DDB4"],
        "widgetHeaderAlignment": "LEFT"}},
}

OUT.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False))
print(f"wrote {OUT} ({len(datasets)} datasets, {len(pages)} pages)")
