# Genie FinOps & Previsão FY2027 — Databricks Asset Bundle

Dashboards e consultas para **prever o gasto com Genie (Genie Agents, Genie One e Genie Code) no próximo ano fiscal**,
considerando a mudança de cobrança de **01/02/2027**: fim da gratuidade de Genie Agents e Genie One e do desconto promocional de 25% no Genie Code.

**Tudo é calculado a partir das system tables do seu próprio workspace/conta.** Nenhum dado é gerado, simulado ou enviado para fora do Databricks.

> **English summary.** A Databricks Asset Bundle (DAB) that deploys (1) a job that builds views and small monthly aggregates over
> `system.billing.usage`, `system.billing.list_prices`, `system.query.history`, `system.access.audit`, `system.compute.warehouses`
> and `system.access.workspaces_latest`; (2) two AI/BI dashboards (pt-BR) that re-price current Genie usage under the post-Feb-2027
> rules and forecast the next fiscal year by scenario; (3) step-by-step SQL files. The written guide is available in
> [Portuguese](docs/GUIA_PREVISAO_GENIE_ptBR.md) and [English](docs/GENIE_COST_FORECAST_GUIDE_en.md).
> Prerequisites and deployment steps are below (commands are the same in any language).

---

## Conteúdo

| Recurso | Descrição |
|---|---|
| Job **`genie-finops-build-views`** | Cria as views sobre as system tables, recalcula os agregados mensais e cria (uma vez) as tabelas de premissas. Agendado diariamente às 06:00 (America/Sao_Paulo) no target `prod`. |
| Dashboard **"Genie FinOps & Previsão FY2027"** | Visão por tema, 5 abas: *Visão geral*, *Usuários & personas*, *Genie Agents & warehouses*, *Previsão FY2027* e *Premissas*. |
| Dashboard **"Genie FinOps — Guia passo a passo (Passos 1 a 10)"** | Versão didática: uma aba por passo do guia (0 · Introdução + Passos 1 a 10). Cada aba traz o objetivo, um quadro *Como ler* e observações geradas em SQL a partir dos seus dados. |
| `src/sql/00..08_*.sql` | As queries do guia, passo a passo, para rodar no SQL Editor. |
| `docs/` | Guia de previsão (pt-BR e inglês) e roteiro de apresentação. |

### Estrutura do repositório

```
databricks.yml                       # bundle: variáveis e targets (dev, prod)
resources/
  genie_finops_views.job.yml         # job que cria views, agregados e premissas
  genie_finops.dashboard.yml         # dashboard por tema
  genie_finops_passos.dashboard.yml  # dashboard passo a passo
src/
  notebooks/build_genie_finops_views.py
  dashboards/*.lvdash.json           # gerados pelos scripts em scripts/
  sql/00..08_*.sql                   # queries do guia
scripts/
  build_dashboard.py                 # gera src/dashboards/genie_finops.lvdash.json
  build_dashboard_passos.py          # gera src/dashboards/genie_finops_passos.lvdash.json
  test_dashboard_queries.py          # roda todas as queries dos dashboards
  test_sql_files.py                  # roda os arquivos src/sql
docs/
  GUIA_PREVISAO_GENIE_ptBR.md        # guia passo a passo (pt-BR)
  GENIE_COST_FORECAST_GUIDE_en.md    # same guide (English)
  ROTEIRO_DEMO.md                    # roteiro de apresentação
```

### Objetos criados no esquema (padrão `genie_finops`)

| Tipo | Objetos | Origem |
|---|---|---|
| Views de origem (filtradas por conta/workspace) | `src_billing_usage`, `src_list_prices`, `src_query_history`, `src_audit`, `dim_warehouses`, `dim_workspaces` | system tables |
| Agregados mensais (recalculados pelo job) | `agg_genie_usage_monthly`, `agg_srti_skus`, `agg_genie_warehouse_monthly`, `agg_genie_questions_monthly`, `dim_genie_agents` | system tables (audit log e query history são grandes demais para consultar ao vivo em contas grandes) |
| **Entradas da previsão** (não são dados de uso) | `forecast_assumptions` (descontos, adicional ESC, margem, franquia, datas) e `forecast_scenarios` (crescimentos mensais) | valores padrão neutros: desconto 0% (preço de lista), adicional 0%, margem 15%. Ajuste com `UPDATE` |
| Views analíticas (passos do guia) | `v_price` (1) · `v_monthly_baseline` (2) · `v_identity_month`, `v_post_promo_simulation` (3) · `v_user_persona_month`, `v_persona_stats` (4) · `v_warehouse_cost_month`, `v_warehouse_attribution` (5) · `v_agent_activity`, `v_unit_costs` (6) · `v_monthly_cost_components`, `v_forecast_baseline`, `v_fy_forecast`, `v_fy_forecast_total` (7) | agregados + premissas |

---

## Pré-requisitos

### 1. Workspace e system tables

- Workspace com **Unity Catalog**.
- **System tables habilitadas** para os esquemas `billing`, `query`, `access` e `compute`.
  O esquema `billing` vem habilitado por padrão; os demais são habilitados por um **account admin** ou **metastore admin**:

  ```bash
  databricks metastores current --profile <perfil>          # anote o metastore_id
  databricks system-schemas list   <metastore_id> --profile <perfil>
  databricks system-schemas enable <metastore_id> query   --profile <perfil>
  databricks system-schemas enable <metastore_id> access  --profile <perfil>
  databricks system-schemas enable <metastore_id> compute --profile <perfil>
  ```

- O SKU `GENIE_FREE_USAGE` só existe a partir de **20/07/2026**. A análise começa nessa data (variável `history_start`).

### 2. Permissões de quem faz o deploy (e roda o job)

| Permissão | Para quê |
|---|---|
| `USE CATALOG` em `system` + `USE SCHEMA` e `SELECT` em `system.billing`, `system.query`, `system.access` e `system.compute` | Ler as system tables |
| `USE CATALOG` e `CREATE SCHEMA` no catálogo de destino (ou `USE SCHEMA` + `CREATE TABLE` em um esquema já existente) | Criar views, agregados e premissas |
| `CAN USE` no SQL warehouse | Executar os dashboards |
| Permissão para criar jobs e dashboards no workspace | Deploy do bundle |

Exemplo de grants (rodados por um metastore admin):

```sql
GRANT USE CATALOG ON CATALOG system TO `finops@empresa.com`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.billing TO `finops@empresa.com`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.query   TO `finops@empresa.com`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.access  TO `finops@empresa.com`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.compute TO `finops@empresa.com`;
GRANT USE CATALOG, CREATE SCHEMA ON CATALOG <catalogo> TO `finops@empresa.com`;
```

> As system tables cobrem **todos os workspaces da conta** (billing, audit) ou do metastore. Restrinja quem tem acesso ao esquema
> `genie_finops` e aos dashboards: eles mostram e-mails de usuários, service principals e custos.

### 3. Computação

- **Serverless compute para jobs** habilitado no workspace (o job não define cluster e roda em serverless).
- Um **SQL warehouse** (serverless recomendado) para os dashboards. Por padrão o bundle procura o warehouse
  **"Serverless Starter Warehouse"**; se ele não existir, informe outro com `--var="warehouse_id=<id>"`.

### 4. Ferramentas locais

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) **≥ 0.281** (testado com 1.26).
- Git.
- (Opcional) Python 3.9+ apenas para regenerar os dashboards ou rodar os scripts de teste em `scripts/`.

---

## Deploy

### 1. Clonar e autenticar

```bash
git clone https://github.com/ericocsilva/genie-finops-forecast.git
cd genie-finops-forecast

databricks auth login --host https://<seu-workspace> --profile genie-finops
databricks current-user me --profile genie-finops        # confere a autenticação
```

### 2. Validar e implantar

Use o target **`prod`** para o uso real (job agendado, nomes sem prefixo) ou **`dev`** para testar
(recursos com prefixo `[dev <usuário>]` e agendamento pausado).

```bash
databricks bundle validate -t prod --profile genie-finops --var="catalog=<catalogo>"

databricks bundle deploy -t prod --profile genie-finops \
  --var="catalog=<catalogo>" \
  --var="warehouse_id=<id-do-warehouse>"     # opcional se existir "Serverless Starter Warehouse"
```

Variáveis opcionais (todas com `--var="nome=valor"`):

| Variável | Padrão | Uso |
|---|---|---|
| `schema` | `genie_finops` | Esquema das views e premissas |
| `history_start` | `2026-07-20` | Primeiro dia analisado |
| `workspace_ids` | vazio (todos) | Lista separada por vírgulas para limitar a análise a alguns workspaces (ex.: por área ou região) |
| `account_id` | vazio | Necessário só quando as tabelas de origem têm várias contas |
| `billing_usage_table`, `list_prices_table`, `query_history_table`, `audit_table`, `warehouses_table`, `workspaces_table` | `system.*` | Apontar para cópias das system tables com as mesmas colunas |

### 3. Criar as views (primeira execução)

```bash
databricks bundle run genie_finops_views -t prod --profile genie-finops    # ~5–10 min na primeira vez
```

### 4. Ajustar as premissas comerciais

Os valores padrão usam **preço de lista** (desconto 0%). Informe o desconto contratual e os adicionais, se houver,
no SQL Editor (veja também `src/sql/08_what_if_premissas.sql`):

```sql
USE <catalogo>.genie_finops;
UPDATE forecast_assumptions SET contract_discount_srti = 0.30, contract_discount_sql = 0.30, addon_uplift = 0.15;
UPDATE forecast_scenarios  SET human_usage_growth_m = 0.05, new_uc_usd_m = 2000 WHERE scenario = 'Base';
```

Clique em **Refresh** nos dashboards. Para restaurar os padrões:
`databricks bundle run genie_finops_views -t prod --profile genie-finops --params reset_assumptions=true`.

### 5. Abrir e compartilhar os dashboards

```bash
databricks bundle summary -t prod --profile genie-finops     # links do job e dos dashboards
```

- O deploy publica os dashboards com as **credenciais de quem fez o deploy**: os leitores não precisam de acesso às system tables.
  Compartilhe apenas com o time de FinOps e os responsáveis das áreas.
- Em cada dashboard, use **Schedule** para enviar uma assinatura mensal por e-mail (Passo 10 do guia).

### Atualizar ou remover

```bash
git pull && databricks bundle deploy -t prod --profile genie-finops --var="catalog=<catalogo>"   # atualizar
databricks bundle destroy -t prod --profile genie-finops                                      # remover job e dashboards
```

`bundle destroy` não apaga o esquema. Para removê-lo: `DROP SCHEMA <catalogo>.genie_finops CASCADE;`.

---

## Regras de cobrança modeladas

Fonte: documentação pública da Databricks (nov/2026). Confirme as condições do seu contrato com o time de conta.

- Até 31/01/2027, Genie Agents e Genie One usados por pessoas são gratuitos (`GENIE_FREE_USAGE`, DBUs integrais).
- Os DBUs cobrados hoje têm a quantidade reduzida em 25% pela promoção (o modelo divide por 0,75 para normalizar).
- Service principals são sempre cobrados, sem franquia.
- A partir de 01/02/2027: um único pool de 150 DBUs/usuário/mês para todas as superfícies, sem promoção.
- A computação SQL é rateada pelo tempo de task, por `query_source.genie_space_id`.
- O preço vem só de `system.billing.list_prices`, para o SKU SRTI faturado pelo Genie (ou, se ainda não houver, o SKU SRTI usado por outro produto da conta).

## Limitações conhecidas

- **Nome do Genie Agent:** as system tables não trazem o título do Genie Agent. Os dashboards mostram `workspace / id`.
- **Preço:** em contas com várias regiões é usado um único preço SRTI (o SKU faturado mais recente). Para precisão por região, filtre `workspace_ids` por região.
- **Identidades:** a classificação humano vs service principal é por heurística (`@` no `run_as`).
- **Agregados:** recalculados uma vez por dia pelo job. Preço, premissas e previsão são calculados na hora.
- **Genie One:** as queries do Genie One não trazem `genie_space_id`; a computação do Genie One aparece como "não-Genie / Genie One".
- **LLM por pergunta:** o billing ainda não traz o Genie Agent nem a conversa; o custo de LLM por pergunta é a média da conta.

---

## Desenvolvimento

Os arquivos `src/dashboards/*.lvdash.json` são gerados pelos scripts. Edite os scripts e regenere:

```bash
python3 scripts/build_dashboard.py           # dashboard por tema
python3 scripts/build_dashboard_passos.py    # dashboard passo a passo

# Testa todas as queries dos dashboards contra o esquema implantado
python3 scripts/test_dashboard_queries.py <perfil> <warehouse_id> <catalogo> genie_finops
python3 scripts/test_dashboard_queries.py <perfil> <warehouse_id> <catalogo> genie_finops src/dashboards/genie_finops_passos.lvdash.json
python3 scripts/test_sql_files.py          <perfil> <warehouse_id> <catalogo> genie_finops
```

## Aviso

Este projeto não é um produto oficial da Databricks e não substitui a fatura nem o contrato. As estimativas dependem das premissas
informadas e das regras de cobrança publicadas na data acima. Valide os números com o time de conta Databricks antes de usá-los em orçamento.
