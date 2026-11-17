#!/usr/bin/env python3
"""Generates src/dashboards/genie_finops.lvdash.json (AI/BI dashboard, pt_BR).

Run:  python3 scripts/build_dashboard.py
All dataset queries use bare view names; catalog/schema come from the bundle
(dataset_catalog / dataset_schema in resources/genie_finops.dashboard.yml).
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "dashboards" / "genie_finops.lvdash.json"

LAST_MONTH = "(SELECT MAX(month) FROM v_monthly_cost_components WHERE is_complete_month)"
FIRST_MONTH = "(SELECT MIN(month) FROM v_monthly_cost_components)"

USD = {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact",
       "decimalPlaces": {"type": "max", "places": 1}}
USD2 = {"type": "number-currency", "currencyCode": "USD", "decimalPlaces": {"type": "exact", "places": 3}}
NUM = {"type": "number", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 1}}
PCT = {"type": "number-percent", "decimalPlaces": {"type": "max", "places": 1}}

COMPONENT_COLORS = [
    {"value": "LLM — usuários humanos", "color": "#1D425C"},
    {"value": "LLM — service principals", "color": "#DE5582"},
    {"value": "SQL warehouse (Genie)", "color": "#FFA600"},
    {"value": "Novos casos de uso", "color": "#99DDB4"},
]
SCENARIO_COLORS = [
    {"value": "Conservador", "color": "#4E79A7"},
    {"value": "Base", "color": "#FFA600"},
    {"value": "Agressivo", "color": "#DE5582"},
]


def q(lines):
    return [l if l.endswith("\n") else l + "\n" for l in lines]


datasets = [
    {"name": "ds_kpi", "displayName": "KPIs do mês de referência", "queryLines": q([
        "WITH c AS (SELECT * FROM v_monthly_cost_components WHERE is_complete_month ORDER BY month DESC LIMIT 1),",
        "f AS (SELECT SUM(total_with_headroom_usd) AS fy_base_usd FROM v_fy_forecast_total WHERE scenario = 'Base'),",
        "u AS (SELECT COUNT(*) AS humans, COUNT_IF(NOT above_allowance) AS humans_within_free",
        "      FROM v_identity_month WHERE identity_type = 'HUMANO' AND month = " + LAST_MONTH + ")",
        "SELECT c.month AS ref_month, c.total_today_usd, c.total_post_promo_usd, c.sp_llm_post_promo_usd,",
        "       c.genie_warehouse_usd, u.humans, u.humans_within_free / u.humans AS pct_within_free, f.fy_base_usd",
        "FROM c CROSS JOIN f CROSS JOIN u",
    ])},
    {"name": "ds_components", "displayName": "Histórico de custo por componente (regras pós-promoção)", "queryLines": q([
        "SELECT month, 'LLM — usuários humanos' AS component, human_llm_post_promo_usd AS usd, total_today_usd FROM v_monthly_cost_components",
        "WHERE is_complete_month AND month > " + FIRST_MONTH,
        "UNION ALL SELECT month, 'LLM — service principals', sp_llm_post_promo_usd, total_today_usd FROM v_monthly_cost_components",
        "WHERE is_complete_month AND month > " + FIRST_MONTH,
        "UNION ALL SELECT month, 'SQL warehouse (Genie)', genie_warehouse_usd, total_today_usd FROM v_monthly_cost_components",
        "WHERE is_complete_month AND month > " + FIRST_MONTH,
        "ORDER BY month",
    ])},
    {"name": "ds_today_vs_post", "displayName": "Hoje vs regras de fev/2027", "queryLines": q([
        "SELECT month, 'Faturado hoje (promoção)' AS basis, total_today_usd AS usd FROM v_monthly_cost_components",
        "WHERE is_complete_month AND month > " + FIRST_MONTH,
        "UNION ALL SELECT month, 'Mesmo uso com regras de fev/2027', total_post_promo_usd FROM v_monthly_cost_components",
        "WHERE is_complete_month AND month > " + FIRST_MONTH,
        "ORDER BY month",
    ])},
    {"name": "ds_surface", "displayName": "DBUs por superfície e tipo de identidade", "queryLines": q([
        "SELECT month, surface, identity_type, channel, free_dbus, billed_dbus, full_rate_dbus, identities",
        "FROM v_monthly_baseline WHERE month > " + FIRST_MONTH + " AND month <= " + LAST_MONTH,
        "ORDER BY month",
    ])},
    {"name": "ds_persona", "displayName": "Personas por mês", "queryLines": q([
        "SELECT month, persona, users, p50_dbus, p90_dbus, avg_dbus, billable_dbus_post_promo, cost_post_promo_usd, users_within_free",
        "FROM v_persona_stats WHERE month > " + FIRST_MONTH + " AND month <= " + LAST_MONTH,
        "ORDER BY month, persona",
    ])},
    {"name": "ds_band", "displayName": "Distribuição de DBUs por usuário (mês de referência)", "queryLines": q([
        "SELECT dbu_band, persona, COUNT(*) AS users, SUM(cost_post_promo_usd) AS cost_post_promo_usd",
        "FROM v_user_persona_month WHERE month = " + LAST_MONTH,
        "GROUP BY ALL ORDER BY dbu_band",
    ])},
    {"name": "ds_top", "displayName": "Top identidades (mês de referência)", "queryLines": q([
        "SELECT i.run_as AS identity, i.identity_type,",
        "       COALESCE(p.persona, 'Service principal') AS persona,",
        "       i.full_rate_dbus, i.agents_dbus, i.one_dbus, i.code_dbus,",
        "       i.billable_dbus_post_promo, i.cost_today_usd, i.cost_post_promo_usd",
        "FROM v_identity_month i",
        "LEFT JOIN v_user_persona_month p ON p.month = i.month AND p.run_as = i.run_as",
        "WHERE i.month = " + LAST_MONTH,
        "ORDER BY i.cost_post_promo_usd DESC LIMIT 25",
    ])},
    {"name": "ds_attrib", "displayName": "Atribuição de warehouse por Genie Agent", "queryLines": q([
        "SELECT warehouse_name, agent_name, queries, share_of_warehouse, attributed_list_cost_usd, attributed_net_cost_usd,",
        "       genie_space_id IS NOT NULL AS is_genie_agent",
        "FROM v_warehouse_attribution WHERE month = " + LAST_MONTH,
        "ORDER BY attributed_net_cost_usd DESC LIMIT 50",
    ])},
    {"name": "ds_attrib_top", "displayName": "Top 15 Genie Agents por custo de warehouse", "queryLines": q([
        "SELECT agent_name, warehouse_name, attributed_net_cost_usd FROM v_warehouse_attribution",
        "WHERE month = " + LAST_MONTH + " AND genie_space_id IS NOT NULL",
        "ORDER BY attributed_net_cost_usd DESC LIMIT 15",
    ])},
    {"name": "ds_unit", "displayName": "Custo por pergunta por Genie Agent", "queryLines": q([
        "SELECT agent_name, questions, agent_mode_share, active_identities, llm_dbus_per_question,",
        "       llm_cost_per_question_usd, warehouse_cost_per_question_usd, total_cost_per_question_usd, warehouse_net_cost_usd",
        "FROM v_unit_costs WHERE month = " + LAST_MONTH,
        "ORDER BY questions DESC LIMIT 25",
    ])},
    {"name": "ds_forecast", "displayName": "Previsão FY2027 por cenário", "queryLines": q([
        "SELECT month, scenario, scenario_order, in_promo, human_llm_usd, sp_llm_usd, genie_warehouse_usd,",
        "       new_use_cases_usd, total_usd, total_with_headroom_usd",
        "FROM v_fy_forecast_total ORDER BY scenario_order, month",
    ])},
    {"name": "ds_forecast_long", "displayName": "Previsão FY2027 por componente", "queryLines": q([
        "SELECT month, scenario, 'LLM — usuários humanos' AS component, human_llm_usd AS usd FROM v_fy_forecast_total",
        "UNION ALL SELECT month, scenario, 'LLM — service principals', sp_llm_usd FROM v_fy_forecast_total",
        "UNION ALL SELECT month, scenario, 'SQL warehouse (Genie)', genie_warehouse_usd FROM v_fy_forecast_total",
        "UNION ALL SELECT month, scenario, 'Novos casos de uso', new_use_cases_usd FROM v_fy_forecast_total",
        "ORDER BY month",
    ])},
    {"name": "ds_fy_totals", "displayName": "Totais FY2027 por cenário", "queryLines": q([
        "SELECT scenario, MIN(scenario_order) AS scenario_order, SUM(human_llm_usd) AS human_llm_usd, SUM(sp_llm_usd) AS sp_llm_usd,",
        "       SUM(genie_warehouse_usd) AS genie_warehouse_usd, SUM(new_use_cases_usd) AS new_use_cases_usd,",
        "       SUM(total_usd) AS total_usd, SUM(total_with_headroom_usd) AS total_with_headroom_usd",
        "FROM v_fy_forecast_total GROUP BY scenario ORDER BY scenario_order",
    ])},
    {"name": "ds_assumptions", "displayName": "Premissas", "queryLines": q([
        "SELECT srti_sku, srti_list_price, srti_net_price_with_addon, contract_discount_srti, contract_discount_sql,",
        "       addon_uplift, headroom, free_allowance_dbus, promo_factor, promo_end_date, fy_start,",
        "       (SELECT baseline_month FROM v_forecast_baseline) AS baseline_month",
        "FROM v_price",
    ])},
    {"name": "ds_scenarios", "displayName": "Cenários", "queryLines": q([
        "SELECT scenario, human_usage_growth_m, sp_growth_m, warehouse_growth_m, new_uc_usd_m, description",
        "FROM forecast_scenarios ORDER BY scenario_order",
    ])},
]


# ---------- widget helpers ----------
def text(name, md, x, y, w, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [md]}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def counter(name, ds, field, title, fmt, x, y, w=3, h=4, filters=None, desc=None):
    query = {"datasetName": ds, "fields": [{"name": f"sum({field})", "expression": f"SUM(`{field}`)"}],
             "disaggregated": False}
    if filters:
        query["filters"] = [{"expression": f} for f in filters]
    frame = {"title": title, "showTitle": True}
    if desc:
        frame.update({"description": desc, "showDescription": True})
    value = {"fieldName": f"sum({field})", "displayName": title}
    if fmt:
        value["format"] = fmt
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": query}],
                       "spec": {"version": 2, "widgetType": "counter", "encodings": {"value": value}, "frame": frame}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def chart(name, kind, ds, x_field, y_field, title, x, y, w=6, h=6, color=None, color_map=None, y_fmt=USD,
          x_type="temporal", agg="SUM", filters=None, layout=None, desc=None, horizontal=False, annotations=None, y_label=None, color_label=None, x_label=None):
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
    query = {"datasetName": ds, "fields": fields, "disaggregated": False}
    if filters:
        query["filters"] = [{"expression": f} for f in filters]
    x_enc = {"fieldName": x_name, "scale": {"type": x_type}, "displayName": x_label or ("Mês" if x_type == "temporal" else "Genie Agent")}
    if x_type == "categorical":
        x_enc["scale"]["sort"] = {"by": "value"} if horizontal else {"by": "alphabetical"}
    y_enc = {"fieldName": y_name, "scale": {"type": "quantitative"}, "displayName": y_label or ("US$" if y_fmt and y_fmt.get("type") == "number-currency" else "DBUs")}
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
    spec = {"version": 3, "widgetType": kind, "encodings": enc, "frame": {"title": title, "showTitle": True}}
    if desc:
        spec["frame"].update({"description": desc, "showDescription": True})
    if layout:
        spec["mark"] = {"layout": layout}
    if annotations:
        spec["annotations"] = annotations
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": query}], "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def table(name, ds, cols, title, x, y, w=12, h=7, desc=None):
    fields = [{"name": c[0], "expression": f"`{c[0]}`"} for c in cols]
    columns = []
    for c in cols:
        col = {"fieldName": c[0], "displayName": c[1]}
        if len(c) > 2 and c[2]:
            col["format"] = c[2]
        columns.append(col)
    frame = {"title": title, "showTitle": True}
    if desc:
        frame.update({"description": desc, "showDescription": True})
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {
        "datasetName": ds, "fields": fields, "disaggregated": True}}],
        "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": columns}, "frame": frame}},
        "position": {"x": x, "y": y, "width": w, "height": h}}


PROMO_LINE = [{"type": "vertical-line", "encodings": {
    "x": {"dataValue": "2027-01-31T12:00:00.000", "dataType": "DATETIME"},
    "label": {"value": "Fim da promoção (31/01/2027)"},
    "color": {"value": {"hex": "#FF7E5C"}}}}]

# ---------- pages ----------
overview = [
    text("ov_header",
         "# Genie FinOps & Previsão FY2027\n"
         "Quanto o Genie custa **hoje**, quanto o **mesmo uso** custaria com as regras que entram em vigor em **01/02/2027** "
         "(fim da gratuidade de Genie Agents/One e do desconto de 25%) e a **previsão do FY2027**. "
         "Valores em US$ líquidos de desconto contratual (premissas na aba *Premissas*). "
         "_Fonte: system tables (`system.billing.usage`, `system.billing.list_prices`, `system.query.history`, `system.access.audit`)._",
         0, 0, 12, 3),
    counter("kpi_today", "ds_kpi", "total_today_usd", "Custo Genie hoje (mês de ref.)", USD, 0, 3,
            desc="LLM faturado (Genie Code + service principals) + warehouse atribuído ao Genie"),
    counter("kpi_post", "ds_kpi", "total_post_promo_usd", "Mesmo uso com regras de fev/2027", USD, 3, 3,
            desc="Franquia de 150 DBUs/usuário/mês compartilhada, sem promoção"),
    counter("kpi_free", "ds_kpi", "pct_within_free", "% usuários dentro da franquia", PCT, 6, 3,
            desc="Usuários humanos com ≤ 150 DBUs no mês (custo de LLM = 0)"),
    counter("kpi_fy", "ds_kpi", "fy_base_usd", "Previsão FY2027 — cenário Base", USD, 9, 3,
            desc="Inclui margem de segurança (headroom)"),
    chart("ov_today_vs_post", "bar", "ds_today_vs_post", "month", "usd", "Custo mensal: hoje vs regras de fev/2027 (US$)",
          0, 7, 6, 6, color="basis", layout="group", color_label="Base de cálculo",
          color_map=[{"value": "Faturado hoje (promoção)", "color": "#4E79A7"},
                     {"value": "Mesmo uso com regras de fev/2027", "color": "#FF7054"}]),
    chart("ov_components", "bar", "ds_components", "month", "usd", "Composição do custo pós-promoção (US$)",
          6, 7, 6, 6, color="component", color_map=COMPONENT_COLORS, color_label="Componente",
          desc="LLM de humanos acima da franquia + LLM de service principals + SQL warehouse dos Genie Agents"),
    chart("ov_surface", "bar", "ds_surface", "month", "full_rate_dbus", "DBUs (taxa cheia) por superfície Genie",
          0, 13, 6, 6, color="surface", y_fmt=NUM, color_label="Superfície",
          color_map=[{"value": "GENIE_AGENTS", "color": "#1D425C"}, {"value": "GENIE_ONE", "color": "#FFA600"},
                     {"value": "GENIE_CODE", "color": "#995495"}]),
    chart("ov_identity", "bar", "ds_surface", "month", "billed_dbus", "DBUs já faturados hoje, por tipo de identidade",
          6, 13, 6, 6, color="identity_type", y_fmt=NUM, color_label="Identidade",
          color_map=[{"value": "HUMANO", "color": "#4E79A7"}, {"value": "SERVICE_PRINCIPAL", "color": "#DE5582"}],
          desc="Service principals não têm franquia nem promoção de gratuidade: já são cobrados hoje"),
]

personas_page = [
    text("pe_header",
         "## Usuários & personas\n"
         "A franquia de **150 DBUs/usuário/mês** é aplicada **por usuário** — médias agregadas enganam. "
         "Poucos usuários intensivos concentram a maior parte do custo; iniciantes ficam dentro da franquia.",
         0, 0, 12, 2),
    chart("pe_users", "bar", "ds_persona", "month", "users", "Usuários ativos por persona", 0, 2, 6, 6,
          color="persona", y_fmt=NUM, color_label="Persona", y_label="Usuários"),
    chart("pe_cost", "bar", "ds_persona", "month", "cost_post_promo_usd", "Custo LLM pós-promoção por persona (US$)",
          6, 2, 6, 6, color="persona", color_label="Persona"),
    chart("pe_band", "bar", "ds_band", "dbu_band", "users", "Usuários por faixa de DBUs/mês (mês de ref.)",
          0, 8, 6, 6, color="persona", x_type="categorical", y_fmt=NUM, color_label="Persona", y_label="Usuários", x_label="DBUs no mês"),
    table("pe_stats", "ds_persona", [
        ("month", "Mês"), ("persona", "Persona"), ("users", "Usuários"),
        ("p50_dbus", "p50 DBUs", NUM), ("p90_dbus", "p90 DBUs", NUM),
        ("users_within_free", "Na franquia"), ("cost_post_promo_usd", "Custo pós-promo", USD)],
        "Percentis por persona (use para definir limites por usuário no budget)", 6, 8, 6, 6),
    table("pe_top", "ds_top", [
        ("identity", "Identidade"), ("identity_type", "Tipo"), ("persona", "Persona"),
        ("full_rate_dbus", "DBUs (taxa cheia)", NUM), ("agents_dbus", "Agents", NUM), ("one_dbus", "One", NUM),
        ("code_dbus", "Code", NUM), ("billable_dbus_post_promo", "DBUs cobráveis pós-promo", NUM),
        ("cost_today_usd", "Custo hoje", USD), ("cost_post_promo_usd", "Custo pós-promo", USD)],
        "Top 25 identidades por custo pós-promoção (mês de referência)", 0, 14, 12, 8),
]

agents_page = [
    text("ag_header",
         "## Genie Agents & SQL warehouses\n"
         "O custo de **computação SQL** não entra no budget do Genie e pode superar o de LLM. "
         "Rateio pelo tempo de task de `system.query.history` (`query_source.genie_space_id`). "
         "Warehouses **dedicados** ao Genie dão atribuição exata.",
         0, 0, 12, 2),
    chart("ag_wh", "bar", "ds_attrib_top", "agent_name", "attributed_net_cost_usd", "Top 15 Genie Agents — custo de warehouse atribuído (US$, mês de ref.)",
          0, 2, 6, 7, x_type="categorical", horizontal=True),
    chart("ag_unit", "bar", "ds_unit", "agent_name", "total_cost_per_question_usd", "Custo total por pergunta (US$) — 25 Agents com mais perguntas",
          6, 2, 6, 7, x_type="categorical", horizontal=True, agg="AVG",
          y_fmt={"type": "number-currency", "currencyCode": "USD", "decimalPlaces": {"type": "exact", "places": 2}}),
    table("ag_unit_tbl", "ds_unit", [
        ("agent_name", "Genie Agent"), ("questions", "Perguntas"), ("agent_mode_share", "% Agent mode", PCT),
        ("active_identities", "Identidades ativas"), ("llm_dbus_per_question", "DBUs LLM/pergunta", NUM),
        ("llm_cost_per_question_usd", "LLM/pergunta", USD2), ("warehouse_cost_per_question_usd", "Warehouse/pergunta", USD2),
        ("total_cost_per_question_usd", "Total/pergunta", USD2), ("warehouse_net_cost_usd", "Warehouse no mês", USD)],
        "Economia unitária por Genie Agent (mês de referência)", 0, 9, 12, 7),
    table("ag_attr_tbl", "ds_attrib", [
        ("warehouse_name", "Warehouse"), ("agent_name", "Genie Agent / carga"), ("queries", "Queries"),
        ("share_of_warehouse", "% do warehouse", PCT), ("attributed_net_cost_usd", "Custo atribuído (líq.)", USD)],
        "Rateio por warehouse (inclui carga não-Genie em warehouses compartilhados)", 0, 16, 12, 7),
]

forecast_page = [
    text("fc_header",
         "## Previsão FY2027\n"
         "Base = run-rate do último mês completo, reprecificado pelas regras pós-promoção e projetado com os "
         "crescimentos de cada cenário (tabela `forecast_scenarios`). Janeiro/2027 ainda é promocional. "
         "Altere premissas com `UPDATE forecast_assumptions ...` e atualize o dashboard.",
         0, 0, 12, 2),
    counter("fc_cons", "ds_fy_totals", "total_with_headroom_usd", "FY2027 — Conservador", USD, 0, 2, 4, 3,
            filters=["`scenario` = 'Conservador'"]),
    counter("fc_base", "ds_fy_totals", "total_with_headroom_usd", "FY2027 — Base", USD, 4, 2, 4, 3,
            filters=["`scenario` = 'Base'"]),
    counter("fc_aggr", "ds_fy_totals", "total_with_headroom_usd", "FY2027 — Agressivo", USD, 8, 2, 4, 3,
            filters=["`scenario` = 'Agressivo'"]),
    chart("fc_line", "line", "ds_forecast", "month", "total_with_headroom_usd", "Custo mensal previsto por cenário (US$, com margem)",
          0, 5, 6, 6, color="scenario", color_map=SCENARIO_COLORS, annotations=PROMO_LINE, color_label="Cenário"),
    chart("fc_comp", "bar", "ds_forecast_long", "month", "usd", "Cenário Base por componente (US$, sem margem)",
          6, 5, 6, 6, color="component", color_map=COMPONENT_COLORS, filters=["`scenario` = 'Base'"], color_label="Componente",
          annotations=PROMO_LINE),
    table("fc_totals", "ds_fy_totals", [
        ("scenario", "Cenário"), ("human_llm_usd", "LLM humanos", USD), ("sp_llm_usd", "LLM service principals", USD),
        ("genie_warehouse_usd", "SQL warehouse", USD), ("new_use_cases_usd", "Novos casos de uso", USD),
        ("total_usd", "Total", USD), ("total_with_headroom_usd", "Total c/ margem", USD)],
        "Totais do ano fiscal por cenário", 0, 11, 12, 4),
    table("fc_monthly", "ds_forecast", [
        ("scenario", "Cenário"), ("month", "Mês"), ("in_promo", "Promoção?"), ("human_llm_usd", "LLM humanos", USD),
        ("sp_llm_usd", "LLM SPs", USD), ("genie_warehouse_usd", "Warehouse", USD), ("new_use_cases_usd", "Novos UCs", USD),
        ("total_usd", "Total", USD), ("total_with_headroom_usd", "Total c/ margem", USD)],
        "Previsão mensal (modelo para o Apêndice A do guia)", 0, 15, 12, 8),
]

assumptions_page = [
    text("as_header",
         "## Premissas da previsão\n"
         "Tabelas editáveis no esquema da demo: `forecast_assumptions` (descontos, adicional ESC, margem, franquia, datas) e "
         "`forecast_scenarios` (crescimentos mensais e novos casos de uso). Exemplo:\n\n"
         "`UPDATE forecast_assumptions SET contract_discount_srti = 0.30;`",
         0, 0, 12, 3),
    table("as_tbl", "ds_assumptions", [
        ("srti_sku", "SKU SRTI"), ("srti_list_price", "Preço lista US$/DBU"), ("srti_net_price_with_addon", "Preço líquido US$/DBU"),
        ("contract_discount_srti", "Desconto SRTI", PCT), ("contract_discount_sql", "Desconto SQL", PCT),
        ("addon_uplift", "Adicional ESC", PCT), ("headroom", "Margem", PCT), ("free_allowance_dbus", "Franquia DBUs"),
        ("promo_factor", "Fator promo"), ("promo_end_date", "Fim promoção"), ("fy_start", "Início FY"),
        ("baseline_month", "Mês base")],
        "Premissas", 0, 3, 12, 3),
    table("as_scen", "ds_scenarios", [
        ("scenario", "Cenário"), ("human_usage_growth_m", "Cresc. humanos/mês", PCT), ("sp_growth_m", "Cresc. SPs/mês", PCT),
        ("warehouse_growth_m", "Cresc. warehouse/mês", PCT), ("new_uc_usd_m", "Novos UCs US$/mês (acum.)", USD),
        ("description", "Descrição")],
        "Cenários", 0, 6, 12, 4),
]

for _page in (personas_page, agents_page, forecast_page):
    _hdr = _page[0]["position"]
    if _hdr["height"] == 2:
        _hdr["height"] = 3
        for _w in _page[1:]:
            _w["position"]["y"] += 1

dashboard = {
    "datasets": datasets,
    "pages": [
        {"name": "visao_geral", "displayName": "Visão geral", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": overview},
        {"name": "personas", "displayName": "Usuários & personas", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": personas_page},
        {"name": "agents", "displayName": "Genie Agents & warehouses", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": agents_page},
        {"name": "previsao", "displayName": "Previsão FY2027", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": forecast_page},
        {"name": "premissas", "displayName": "Premissas", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": assumptions_page},
    ],
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
print(f"wrote {OUT} ({len(datasets)} datasets)")
