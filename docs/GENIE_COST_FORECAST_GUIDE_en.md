# Forecasting Genie Spend for the Next Fiscal Year — Step-by-Step Guide

**Audience:** platform / FinOps owners
**Date:** 2026-11-12
**Scope:** Genie Agents (formerly Genie Spaces), Genie One, Genie Code, and the SQL compute they consume

---

## 0. TL;DR

1. **Genie Agents and Genie One stop being free on Feb 1, 2027.** Through **Jan 31, 2027**, human-user LLM usage on these two surfaces is free (recorded as `GENIE_FREE_USAGE`). From Feb 1 it is billed like Genie Code: every human user gets **150 DBUs/month free, shared across all Genie surfaces**, and anything above that is billed on the **Serverless Real-Time Inference (SRTI)** SKU.
2. **Service principals get no free allowance** and are billed today. This matters for production patterns where Genie Agents are called by apps under an SP.
3. **Genie's LLM DBUs are already metered today, even while free.** `system.billing.usage` holds a full record since **2026-07-20**, so you can forecast from **real data** instead of assumptions.
4. **SQL warehouse compute is a separate cost.** It is not in the Genie LLM line and is not covered by Genie budgets. Forecast it separately.
5. Recommended approach: **(a)** baseline the LLM DBUs per user and per surface → **(b)** re-price them at post-promo rules (150-DBU allowance per user, no 25% promo) → **(c)** add Genie-attributed warehouse cost → **(d)** project growth with scenarios → **(e)** turn on Genie budgets before Feb 1.

---

## 1. Understand the billing model (what changes in the next FY)

| Component | Until Jan 31, 2027 | From Feb 1, 2027 | Where it shows up |
|---|---|---|---|
| **Genie Agents: LLM** (human users) | Free (metered as `GENIE_FREE_USAGE`) | Billed above the 150 DBU/user/month allowance | `system.billing.usage`, `billing_origin_product = 'GENIE'`, `usage_metadata.genie.surface = 'GENIE_AGENTS'` |
| **Genie One: LLM** (human users) | Free | Billed above the allowance | `surface = 'GENIE_ONE'` |
| **Genie Code: LLM** | Billed above 150 DBU/user/month, **25% promo discount** | Billed above the allowance, **no promo discount** (list price, less your contract discount) | `surface = 'GENIE_CODE'` |
| **Service principal usage** (any surface) | **Billed**, no allowance | Billed, no allowance | `identity_metadata.run_as` = SP application ID |
| **SQL warehouse compute** for generated queries | Billed (normal DBSQL) | Billed (normal DBSQL) | `system.billing.usage` (warehouse SKU) + `system.query.history` |
| **Free allowance** | 150 DBUs/user/month, **one pool shared across Code + One + Agents**, resets on the 1st | Same | `sku_name = 'GENIE_FREE_USAGE'` |

Notes:
- **Reference price:** 150 DBUs ≈ US$10.50 in US East (≈ US$0.07/DBU). Each cloud region has its own SRTI price, so always take the rate from `system.billing.list_prices` (Step 1) and apply your contract discount.
- **On-behalf-of (OBO):** when an app or API calls Genie **on behalf of the end user**, the LLM usage is charged to that user and counts against that user's free allowance. When the app calls as a **service principal**, every DBU is billed. Users who reach Genie through a group or role (RBAC) don't get the free promo either.
- **Agent mode** (multi-step reasoning) uses more LLM tokens and **runs more SQL queries** per question than standard chat, so it costs more.
- **Language matters:** non-English content (Portuguese, Spanish, etc.) uses **more tokens per question**. Users working in other languages will exhaust the 150-DBU allowance faster than English-language benchmarks suggest. This is one more reason to forecast from your own data.
- **During the promo, Genie Agents and Genie One usage doesn't draw down the 150-DBU allowance**. That usage is fully waived, so today the allowance is consumed by Genie Code only. **From Feb 1 all three surfaces share one 150-DBU pool**, so heavy Genie Code developers will have no allowance left for Agents and One.
- **Genie One → Genie Agent calls:** the Agent's data work is attributed to `GENIE_AGENTS`, and Genie One's orchestration to `GENIE_ONE`. Nothing is counted twice.
- **Dashboards shared with publisher credentials:** Genie LLM tokens are charged to the **end user asking the question**, while the warehouse compute runs as the publisher.
- **Web search tool** (when Genie uses it): LLM tokens plus a per-call fee, both billed as Genie DBUs.
- **Order of operations for the bill:** (1) Genie DBUs → (2) subtract the 150-DBU free allowance → (3) promo (only until Jan 31, 2027) → (4) price on the SRTI SKU with your negotiated SRTI discount → (5) platform add-on uplifts such as **Enhanced Security & Compliance (ESC)**, if applicable to your workspaces. The free allowance is fixed at list price and isn't affected by discounts.
- Docs: [Monitor Genie cost](https://learn.microsoft.com/en-us/azure/databricks/genie/monitor-cost) · [Budgets for Genie](https://learn.microsoft.com/en-us/azure/databricks/genie/budgets) · [Consumption guide](https://learn.microsoft.com/en-us/azure/databricks/genie/consumption-guide) · [Cost & budgets FAQ](https://learn.microsoft.com/en-us/azure/databricks/genie/genie-cost-budgets-faq) · [Release note: free through Jan 31, 2027](https://learn.microsoft.com/en-us/azure/databricks/ai-bi/release-notes/2026)

---

## 2. Prerequisites

| Item | Why | Who |
|---|---|---|
| Access to `system.billing.usage` and `system.billing.list_prices` | LLM DBUs and prices | Metastore/account admin grants `USE` + `SELECT` |
| Access to `system.query.history` | Attribute warehouse compute to Genie | Same |
| Access to `system.access.audit` | Activity volume (questions, conversations, feedback) | Same |
| A small SQL warehouse (Serverless recommended) to run the queries | | Platform team |
| Account admin in the Account Console | Budgets (Step 9) | Account admin |
| List of Genie Agents in production, their owners, warehouses, and whether they're called by **users (UI/OBO)** or **service principals** | Segmentation | FinOps + BU owners |

> ⚠️ The `GENIE_FREE_USAGE` SKU only exists from **2026-07-20**, so free usage before that date isn't visible. Use **Aug 2026 → current month** as the baseline (3+ full months).

---

## 3. Step 1 — Find the SKU and the unit price that will apply

**3.1 Which SRTI SKU(s) are you already billed on for Genie?**

```sql
SELECT DISTINCT cloud, sku_name
FROM system.billing.usage
WHERE billing_origin_product = 'GENIE'
  AND sku_name <> 'GENIE_FREE_USAGE';
```

**3.2 Current list price for that SKU** (if 3.1 returns nothing, look the SKU up by pattern):

```sql
SELECT cloud, sku_name, currency_code, usage_unit,
       pricing.effective_list.default AS list_price_per_dbu,
       price_start_time
FROM system.billing.list_prices
WHERE sku_name LIKE '%SERVERLESS_REAL_TIME_INFERENCE%'
  AND price_end_time IS NULL
ORDER BY sku_name;
```

Write down **`P_list`** (US$/DBU) for the region(s) you use. Your **contract discount `d`** comes from the commercial team, not from system tables. Use **`P_net = P_list × (1 − d)`** in the forecast.

---

## 4. Step 2 — Baseline: monthly Genie LLM DBUs by surface and identity type

```sql
-- Monthly Genie LLM DBUs by surface, human vs service principal, free vs billed
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
```

How to read it:
- `free_dbus` on `GENIE_AGENTS` / `GENIE_ONE` is the volume that **turns billable** (above the allowance) on Feb 1, 2027.
- `billed_dbus` with `identity_type = SERVICE_PRINCIPAL` is **already a cost today**. Check it against your production integrations.
- The `'@'` test treats Entra UPN identities as human and application IDs (UUIDs) as service principals. Check the classification against your SP list.

---

## 5. Step 3 — Re-price history under the post-Feb 1 rules (per user)

> **Key point:** apply the allowance **per user, per month**, not to the total. A few power users can drive most of the cost, so aggregate averages are misleading.

Rules to apply:
- Human users: `billable = max(0, total_monthly_dbus_all_surfaces − 150)`.
- Service principals: `billable = total_monthly_dbus`.
- Billed (SRTI) Genie DBUs today **already include the 25% promo discount**: the promo lowers the DBU quantity, not the price in `list_prices`. `GENIE_FREE_USAGE` rows are recorded at raw, full DBUs. **True consumption = free_dbus + billed_dbus / 0.75.** After Jan 31, 2027 the two become directly summable.

```sql
-- Simulate each historical month as if the post-Feb-2027 rules were in force
WITH per_identity_month AS (
  SELECT
    DATE_TRUNC('MONTH', usage_date)           AS month,
    identity_metadata.run_as                  AS run_as,
    CASE WHEN identity_metadata.run_as LIKE '%@%'
         THEN 'HUMAN' ELSE 'SERVICE_PRINCIPAL' END AS identity_type,
    SUM(CASE
          WHEN sku_name <> 'GENIE_FREE_USAGE'
          THEN usage_quantity / 0.75          -- remove the 25% promo (applies to all billed Genie DBUs, incl. SPs)
          ELSE usage_quantity
        END)                                  AS full_rate_dbus,
    SUM(CASE WHEN usage_metadata.genie.surface = 'GENIE_AGENTS' THEN usage_quantity ELSE 0 END) AS agents_dbus,
    SUM(CASE WHEN usage_metadata.genie.surface = 'GENIE_ONE'    THEN usage_quantity ELSE 0 END) AS one_dbus
  FROM system.billing.usage
  WHERE billing_origin_product = 'GENIE'
    AND usage_date >= '2026-08-01'
    AND usage_date <  DATE_TRUNC('MONTH', CURRENT_DATE)   -- full months only
  GROUP BY ALL
)
SELECT
  month,
  identity_type,
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
```

Set `:p_net_usd_per_dbu` = `P_net` from Step 1. The result is **"what this month would have cost from Feb 2027"**, which is your run-rate starting point.

---

## 6. Step 4 — Segment users into personas (for scenario modelling)

```sql
WITH per_user_month AS (
  SELECT DATE_TRUNC('MONTH', usage_date) AS month,
         identity_metadata.run_as        AS run_as,
         SUM(usage_quantity)             AS dbus
  FROM system.billing.usage
  WHERE billing_origin_product = 'GENIE'
    AND identity_metadata.run_as LIKE '%@%'
    AND usage_date >= '2026-08-01'
    AND usage_date <  DATE_TRUNC('MONTH', CURRENT_DATE)
  GROUP BY ALL
)
SELECT month,
       COUNT(*)                                   AS active_users,
       PERCENTILE_APPROX(dbus, 0.50)              AS p50_dbus,
       PERCENTILE_APPROX(dbus, 0.75)              AS p75_dbus,
       PERCENTILE_APPROX(dbus, 0.90)              AS p90_dbus,
       PERCENTILE_APPROX(dbus, 0.99)              AS p99_dbus,
       MAX(dbus)                                  AS max_dbus,
       COUNT_IF(dbus <= 150)                      AS users_within_free,
       COUNT_IF(dbus >  150 AND dbus <= 450)      AS users_150_450,
       COUNT_IF(dbus >  450)                      AS users_above_450
FROM per_user_month
GROUP BY month
ORDER BY month;
```

Suggested persona tiers (thresholds come from your own percentiles):

| Persona | Typical profile | Rule of thumb |
|---|---|---|
| Beginner | Occasional questions | ≤ p50, usually inside the 150 DBU allowance → ~US$0 LLM |
| Practitioner | Regular use, standard chat | p50–p90 |
| Power user | Agent mode, long analyses, Genie Code authoring | > p90; these users drive most of the bill |
| Service principal / app | Production integrations (apps, MCP, batch) | 100% billable; size per app |

Also list the **top 20 users and SPs** by DBUs (`ORDER BY dbus DESC LIMIT 20`) and confirm with each BU that the usage is legitimate and expected to recur.

---

## 7. Step 5 — Attribute SQL warehouse compute to Genie

Genie LLM cost is often **not the largest line**. The warehouses that run the generated SQL can cost more. Use `query_source.genie_space_id` in `system.query.history` to identify Genie Agent queries and allocate warehouse cost by their share of task time:

```sql
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
       ROUND(q.genie_task_ms / NULLIF(q.all_task_ms, 0), 3)                 AS genie_share,
       ROUND(w.list_cost_usd, 2)                                            AS warehouse_list_cost_usd,
       ROUND(w.list_cost_usd * q.genie_task_ms / NULLIF(q.all_task_ms, 0), 2) AS genie_attributed_cost_usd
FROM q JOIN wh_cost w USING (month, warehouse_id)
WHERE q.genie_queries > 0
ORDER BY q.month, genie_attributed_cost_usd DESC;
```

To break it down **per Genie Agent**, group `q` by `query_source.genie_space_id` as well.

Caveats and recommendations:
- Proportional allocation doesn't capture **idle/auto-stop time**. If a warehouse is **dedicated to Genie**, use 100% of its cost. This is the most accurate setup and **the recommended practice** for production Genie Agents.
- Genie One queries may not carry `genie_space_id`. Use `client_application` / `executed_by` as a proxy, and treat Genie One compute as an estimate. (A best-effort free compute allowance for Genie One is in Beta.)

---

## 8. Step 6 — Build unit costs (cost per question / per active user)

Unit costs let you forecast from **business drivers** (users, agents, questions) instead of DBUs.

**8.1 Find the relevant audit actions** (action names differ between Genie Agents and Genie One):

```sql
SELECT service_name, action_name, COUNT(*) AS events
FROM system.access.audit
WHERE service_name IN ('aibiGenie', 'genieChat')
  AND event_date >= '2026-08-01'
GROUP BY ALL
ORDER BY events DESC;
```

**8.2 Monthly questions and active users per Genie Agent.** Replace the action list with the message-creation actions you found in 8.1:

```sql
SELECT DATE_TRUNC('MONTH', event_date)                  AS month,
       request_params['space_id']                       AS genie_space_id,
       COUNT(*)                                         AS questions,
       COUNT(DISTINCT user_identity.email)              AS active_users
FROM system.access.audit
WHERE service_name = 'aibiGenie'
  AND action_name IN ('<message-creation actions from 8.1>')
  AND event_date >= '2026-08-01'
GROUP BY ALL
ORDER BY month, questions DESC;
```

**8.3 Unit economics**, combining Steps 2–5 and 8.2:

| KPI | Formula |
|---|---|
| LLM DBUs per question (Agents) | `GENIE_AGENTS DBUs / questions` |
| LLM cost per question | `DBUs per question × P_net` |
| Warehouse cost per question | `genie_attributed_cost_usd / genie_queries` (Step 5) |
| **All-in cost per question** | LLM + warehouse |
| Cost per active user per month | `(billable LLM + warehouse) / active users` |

Track these KPIs per Genie Agent. A high cost per question usually points to a fixable cause, such as heavy Agent mode, poor instructions or metadata, or an oversized or always-on warehouse.

---

## 9. Step 7 — Project the next fiscal year (scenario model)

Start from the run-rate in Steps 3 and 5, then apply drivers per month:

```
Monthly Genie cost(m) =
    Σ_personas [ users_p(m) × max(0, avg_DBU_p(m) − 150) ] × P_net      ← human LLM (all surfaces)
  + Σ_apps    [ SP_DBUs_app(m) ] × P_net                                ← service principals
  + Σ_agents  [ questions_a(m) × warehouse_cost_per_question_a ]        ← SQL compute
  + new_use_cases(m)                                                    ← pipeline (Step 8)
  × (1 + add-on uplift, e.g. ESC, if applicable)
```

Where `P_net = P_list × (1 − SRTI contract discount)`. There is no promo factor from Feb 2027.

Notes on the calendar:
- **Jan 2027:** Genie Agents and Genie One are still free, and Genie Code still has the 25% promo.
- **Feb 2027 onwards:** the full post-promo rules apply. If your fiscal year is Jan–Dec, that's **11 billable months** for Agents and One.

Build three scenarios:

| Scenario | Users growth | DBU / user | SP / app usage | New Genie Agents |
|---|---|---|---|---|
| Conservative | current active users, flat | current p50/p75 | current | none |
| Base | BU roll-out plan | +10–20% (more Agent mode) | planned apps | confirmed pipeline |
| Aggressive | full target population | power-user mix grows | all planned apps in prod | full pipeline |

Tips:
- History only goes back to mid-2026, which is **too short for a statistical forecast**. Use the series to calibrate the scenarios. If you want a trend line, `ai_forecast()` in Databricks SQL can project the monthly series, but treat it as indicative only.
- Add **headroom (10–20%)** for power users and the adoption curve. The FY27 Genie One roll-out and new features (file attachments, volumes search, sub-agents) tend to raise usage.
- Keep a **separate line for Genie Code** (developers who author and maintain Agents). This is a different persona and budget from consumers.

---

## 10. Step 8 — Size new use cases that have no history yet

For Genie Agents planned for next year, there is nothing in the system tables yet. Use one of these:
1. **A 2–4 week pilot** with a representative group of users, then measure it with Steps 2–8. This is the most reliable option.
2. **The Databricks Genie Agents/One sizing calculator.** Your Databricks account team can run it with you: persona counts in, monthly LLM estimate out. It **excludes SQL compute and Genie Code**, so add those from Step 5 or Step 8.
3. **Analogy:** use the unit cost per question from a similar existing Genie Agent.

---

## 11. Step 9 — Put guardrails in place **before Feb 1, 2027**

| Control | How | Recommendation |
|---|---|---|
| **Genie budget** | Account Console → *Usage → Budgets* → resource type **Unity Gateway**, tag `databricks-product = genie` (no other tags) | Create it now. During the promo it tracks Genie Code. From Feb 1 it will cover Agents and One as well |
| **Shared threshold** (pool) | Monthly pool for all users in scope | **Alert-only** at 80% and 100%. Avoid *Block usage* here because it blocks everyone in scope |
| **Per-user threshold** | Default monthly limit per user on top of the free allowance | Set it from the Beginner/Practitioner percentile (Step 4), with *Block usage* |
| **Overrides** | Per user or group (up to 100 per budget) | One account group per persona (e.g., `genie-power-users`) with a higher limit, plus an approval process to join |
| **Webhooks / e-mail** | Per threshold | Send to FinOps and the BU owner |
| **Dedicated warehouses** | One Serverless warehouse per BU/domain for Genie Agents | Exact compute attribution and auto-stop control |
| **Identity pattern** | Prefer **OBO / user pass-through** over service principals for user-facing apps | Gives per-user attribution and uses each user's 150 DBU allowance. SP usage is 100% billable |

Limits to know:
- Budgets **cannot yet be split per surface** (Code vs Agents vs One). They share the same tag. Use `usage_metadata.genie.surface` in reporting.
- Budgets are **near-real-time estimates**. `system.billing.usage` (updated every few hours) is the source of truth.
- Budgets track spend at **list price**. They include the promo and add-ons but **not your contract discount**, so set thresholds in list-price terms.
- To get separate per-product limits today, create **one group per product audience** (e.g., `genie-code-users`, `genie-consumers`) with its own per-user threshold.
- A budget created mid-month backfills from the 1st of the month.
- Workspace admins can manage budgets for their own workspaces via Governance Hub (Beta), which is useful for per-BU ownership.
- Through Jan 31, 2027, per-user budgets have **no effect** on human Genie Agents and One usage, which is free. Plan to **review the thresholds in January 2027** so they're ready when billing starts.
- Budgets don't cover warehouse compute. Use standard DBSQL budgets and tags on the warehouses.

---

## 12. Step 10 — Operationalize: a monthly Genie FinOps dashboard

1. Save the queries from Steps 1–8 into an **AI/BI dashboard**, with pages for *Run-rate*, *Per-user/persona*, *Per Genie Agent*, *Warehouse attribution*, and *Forecast vs Actual*.
2. Schedule a monthly refresh and a subscription for FinOps and BU owners.
3. Every month, compare actuals with the scenario and re-baseline the forecast, especially after Feb 2027 when real billing starts.
4. Review the top-N users, SPs, and Agents with the highest cost per question, and optimize their instructions, Agent mode use, and warehouse sizing.

---

## 13. Assumptions & open points to confirm with Databricks

| # | Topic | Status |
|---|---|---|
| 1 | Free promo for Genie Agents and Genie One ends **Jan 31, 2027** | Public release notes and docs |
| 2 | 150 DBU/user/month allowance is **shared** across all Genie surfaces and **excludes SPs** | Public docs |
| 3 | 25% promo ends Jan 31, 2027. Billed Genie DBUs today are reduced at metering (÷0.75 to normalize) | Confirmed by Databricks pricing FAQ |
| 4 | Post-Feb 1 billing SKU for Agents and One = same regional SRTI SKU as Genie Code | Confirmed (one SRTI SKU, tagged by surface). Confirm the exact regional SKU via Step 1 |
| 4b | High-volume Genie Agents (e.g., SP-driven apps) can use **Reserved Capacity / Provisioned Throughput** instead of pay-as-you-go | Available on request. Discuss with Databricks if SP volume is large and predictable |
| 4c | ESC / compliance add-on uplift applies on top of Genie $DBUs | Confirm whether it applies to your workspaces |
| 5 | Genie One compute: best-effort free allowance (account-level) | Beta. Don't rely on it for the forecast |
| 6 | Finer-grained cost data (per conversation/question) in system tables | On the roadmap. Use the Step 8 proxies for now |
| 7 | Future add-ons (e.g., Genie Ontology) | Not included in this forecast. Add as a separate line once pricing is published |
| 8 | Contract discount `d` and commit drawdown | Confirm with the Databricks account executive |

---

## Appendix A — Forecast template (fill in per month)

| Month | Active human users | Avg DBU/user | Billable human DBUs | SP DBUs | LLM cost (US$) | Genie warehouse cost (US$) | Genie Code (US$) | New UCs (US$) | **Total (US$)** |
|---|---|---|---|---|---|---|---|---|---|
| Jan-27 (promo) | | | 0 (Agents/One) | | | | (25% off) | | |
| Feb-27 | | | | | | | | | |
| … | | | | | | | | | |
| Dec-27 | | | | | | | | | |
| **FY total** | | | | | | | | | |
