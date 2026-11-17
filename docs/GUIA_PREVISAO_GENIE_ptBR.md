
# Previsão de Gastos com Genie para o Próximo Ano Fiscal — Guia Passo a Passo

**Público:** responsáveis por plataforma / FinOps
**Data:** 12/11/2026
**Escopo:** Genie Agents (antigos Genie Spaces), Genie One, Genie Code e a computação SQL que eles consomem


## 0. Resumo executivo

1. **Genie Agents e Genie One deixam de ser gratuitos em 01/02/2027.** Até **31/01/2027**, o uso de LLM por usuários humanos nesses dois produtos é gratuito (registrado como `GENIE_FREE_USAGE`). A partir de 01/02 passa a ser cobrado como o Genie Code: cada usuário humano tem uma **franquia gratuita de 150 DBUs/mês, compartilhada entre todos os produtos Genie**, e o que exceder é cobrado no SKU **Serverless Real-Time Inference (SRTI)**.
2. **Service principals não têm franquia gratuita** e já são cobrados hoje. Isso é relevante para padrões de produção em que Genie Agents são chamados por aplicações sob um service principal.
3. **Os DBUs de LLM do Genie já são medidos hoje, mesmo quando gratuitos.** A tabela `system.billing.usage` tem o registro completo desde **20/07/2026**, então é possível fazer a previsão com **dados reais**, e não com premissas.
4. **A computação do SQL warehouse é um custo separado.** Ela não entra na linha de LLM do Genie e não é coberta pelos budgets do Genie. Faça a previsão dela à parte.
5. Abordagem recomendada: **(a)** levantar a linha de base de DBUs de LLM por usuário e por produto → **(b)** reprecificar pelas regras pós-promoção (franquia de 150 DBUs por usuário, sem os 25% de desconto) → **(c)** somar o custo de warehouse atribuído ao Genie → **(d)** projetar o crescimento com cenários → **(e)** ativar budgets do Genie antes de 01/02.

## 1. Entenda o modelo de cobrança (o que muda no próximo ano fiscal)

| Componente | Até 31/01/2027 | A partir de 01/02/2027 | Onde aparece |
|---|---|---|---|
| **Genie Agents: LLM** (usuários humanos) | Gratuito (medido como `GENIE_FREE_USAGE`) | Cobrado acima da franquia de 150 DBUs/usuário/mês | `system.billing.usage`, `billing_origin_product = 'GENIE'`, `usage_metadata.genie.surface = 'GENIE_AGENTS'` |
| **Genie One: LLM** (usuários humanos) | Gratuito | Cobrado acima da franquia | `surface = 'GENIE_ONE'` |
| **Genie Code: LLM** | Cobrado acima de 150 DBUs/usuário/mês, **com 25% de desconto promocional** | Cobrado acima da franquia, **sem desconto promocional** (preço de lista menos o desconto contratual) | `surface = 'GENIE_CODE'` |
| **Uso por service principal** (qualquer produto) | **Cobrado**, sem franquia | Cobrado, sem franquia | `identity_metadata.run_as` = application ID do SP |
| **Computação do SQL warehouse** para as queries geradas | Cobrada (DBSQL normal) | Cobrada (DBSQL normal) | `system.billing.usage` (SKU do warehouse) + `system.query.history` |
| **Franquia gratuita** | 150 DBUs/usuário/mês, renovada todo dia 1º. Durante a promoção, só o Genie Code consome a franquia | **Um único pool compartilhado entre Code + One + Agents** | `sku_name = 'GENIE_FREE_USAGE'` |

Observações:

- **Preço de referência:** 150 DBUs ≈ US$ 10,50 em US East (≈ US$ 0,07/DBU). Cada região de nuvem tem preço SRTI próprio, então use sempre o valor de `system.billing.list_prices` (Passo 1) e aplique o seu desconto contratual.
- **On-behalf-of (OBO):** quando uma aplicação ou API chama o Genie **em nome do usuário final**, o uso de LLM é atribuído a esse usuário e consome a franquia gratuita dele. Quando a aplicação chama como **service principal**, todo DBU é cobrado. Usuários que acessam o Genie por um grupo ou papel assumido (RBAC) também não recebem a franquia nem a promoção.
- **Agent mode** (raciocínio em várias etapas) usa mais tokens de LLM e **executa mais queries SQL** por pergunta do que o chat padrão, então custa mais.
- **O idioma faz diferença:** conteúdo em outros idiomas além do inglês (incluindo português) usa **mais tokens por pergunta**. Usuários que trabalham em português vão esgotar a franquia de 150 DBUs mais rápido do que os benchmarks em inglês indicam. É mais um motivo para basear a previsão nos seus próprios dados.
- **Durante a promoção, o uso de Genie Agents e Genie One não consome a franquia de 150 DBUs**, porque esse uso é totalmente isento. Hoje, só o Genie Code consome a franquia. **A partir de 01/02 os três produtos compartilham um único pool de 150 DBUs**, então desenvolvedores que usam muito o Genie Code não terão franquia sobrando para Agents e One.
- **Chamadas do Genie One para um Genie Agent:** o trabalho de dados do Agent é atribuído a `GENIE_AGENTS`, e a orquestração do Genie One a `GENIE_ONE`. Nada é contado em dobro.
- **Dashboards compartilhados com as credenciais do publicador:** os tokens de LLM do Genie são cobrados do **usuário final que faz a pergunta**, enquanto a computação do warehouse roda como o publicador.
- **Ferramenta de busca na web** (quando o Genie a utiliza): tokens de LLM mais uma taxa por chamada, ambos cobrados como DBUs do Genie.
- **Ordem de cálculo da fatura:** (1) DBUs do Genie → (2) desconta a franquia gratuita de 150 DBUs → (3) promoção (apenas até 31/01/2027) → (4) preço no SKU SRTI com o desconto negociado para esse SKU → (5) adicionais de plataforma, como **Enhanced Security & Compliance (ESC)**, se aplicáveis aos seus workspaces. A franquia gratuita é fixada a preço de lista e não é afetada por descontos.
- Documentação: [Monitorar o custo do Genie](https://learn.microsoft.com/pt-br/azure/databricks/genie/monitor-cost) · [Budgets do Genie](https://learn.microsoft.com/pt-br/azure/databricks/genie/budgets) · [Guia de consumo](https://learn.microsoft.com/pt-br/azure/databricks/genie/consumption-guide) · [FAQ de custos e budgets](https://learn.microsoft.com/pt-br/azure/databricks/genie/genie-cost-budgets-faq) · [Release note: gratuito até 31/01/2027](https://learn.microsoft.com/pt-br/azure/databricks/ai-bi/release-notes/2026)

## 2. Pré-requisitos

| Item | Para quê | Quem |
|---|---|---|
| Acesso a `system.billing.usage` e `system.billing.list_prices` | DBUs de LLM e preços | Admin do metastore/conta concede `USE` + `SELECT` |
| Acesso a `system.query.history` | Atribuir a computação do warehouse ao Genie | Idem |
| Acesso a `system.access.audit` | Volume de atividade (perguntas, conversas, feedback) | Idem |
| Um SQL warehouse pequeno (Serverless recomendado) para rodar as queries | — | Time de plataforma |
| Account admin no Account Console | Budgets (Passo 9) | Account admin |
| Lista dos Genie Agents em produção, com responsáveis, warehouses e se são chamados por **usuários (UI/OBO)** ou **service principals** | Segmentação | FinOps + responsáveis das áreas de negócio |

**⚠️ Atenção:** o SKU `GENIE_FREE_USAGE` só existe a partir de **20/07/2026**, então o uso gratuito anterior a essa data não aparece. Use **agosto/2026 → mês atual** como linha de base (3 ou mais meses completos).

## 3. Passo 1 — Identificar o SKU e o preço unitário que vão se aplicar

**3.1 Em quais SKUs SRTI você já é cobrado pelo Genie?**

```sql
SELECT DISTINCT cloud, sku_name
FROM system.billing.usage
WHERE billing_origin_product = 'GENIE'
  AND sku_name <> 'GENIE_FREE_USAGE';
```

**3.2 Preço de lista atual desse SKU** (se a 3.1 não retornar nada, busque o SKU pelo padrão do nome):

```sql
SELECT cloud, sku_name, currency_code, usage_unit,
       pricing.effective_list.default AS list_price_per_dbu,
       price_start_time
FROM system.billing.list_prices
WHERE sku_name LIKE '%SERVERLESS_REAL_TIME_INFERENCE%'
  AND price_end_time IS NULL
ORDER BY sku_name;
```

Anote o **`P_list`** (US$/DBU) da(s) região(ões) que você usa. O **desconto contratual `d`** vem do time comercial, não das system tables. Use **`P_net = P_list × (1 − d)`** na previsão.

## 4. Passo 2 — Linha de base: DBUs mensais de LLM do Genie por produto e tipo de identidade

```sql
-- DBUs mensais de LLM do Genie por produto, humano vs service principal, gratuito vs cobrado
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

Como interpretar:

- `free_dbus` em `GENIE_AGENTS` / `GENIE_ONE` é o volume que **passa a ser cobrável** (acima da franquia) a partir de 01/02/2027.
- `billed_dbus` com `identity_type = SERVICE_PRINCIPAL` **já é custo hoje**. Compare com as integrações de produção de vocês.
- O teste com `'@'` classifica identidades Entra (UPN) como humanas e application IDs (UUIDs) como service principals. Valide essa classificação com a lista de SPs de vocês.

## 5. Passo 3 — Reprecificar o histórico pelas regras pós-01/02 (por usuário)

**Ponto-chave:** aplique a franquia **por usuário e por mês**, não sobre o total. Poucos usuários intensivos podem concentrar a maior parte do custo, e médias agregadas enganam.

Regras a aplicar:

- Usuários humanos: `cobrável = max(0, total_mensal_de_dbus_em_todos_os_produtos − 150)`.
- Service principals: `cobrável = total_mensal_de_dbus`.
- Os DBUs cobrados do Genie (SKU SRTI) hoje **já incluem o desconto promocional de 25%**: a promoção reduz a quantidade de DBUs, não o preço em `list_prices`. Já as linhas `GENIE_FREE_USAGE` são registradas com os DBUs integrais. **Consumo real = free_dbus + billed_dbus / 0,75.** Depois de 31/01/2027 os dois valores podem ser somados diretamente.

```sql
-- Simula cada mês do histórico como se as regras pós-fev/2027 já estivessem valendo
WITH per_identity_month AS (
  SELECT
    DATE_TRUNC('MONTH', usage_date)           AS month,
    identity_metadata.run_as                  AS run_as,
    CASE WHEN identity_metadata.run_as LIKE '%@%'
         THEN 'HUMAN' ELSE 'SERVICE_PRINCIPAL' END AS identity_type,
    SUM(CASE
          WHEN sku_name <> 'GENIE_FREE_USAGE'
          THEN usage_quantity / 0.75          -- remove a promoção de 25% (vale para todo DBU cobrado do Genie, inclusive SPs)
          ELSE usage_quantity
        END)                                  AS full_rate_dbus,
    SUM(CASE WHEN usage_metadata.genie.surface = 'GENIE_AGENTS' THEN usage_quantity ELSE 0 END) AS agents_dbus,
    SUM(CASE WHEN usage_metadata.genie.surface = 'GENIE_ONE'    THEN usage_quantity ELSE 0 END) AS one_dbus
  FROM system.billing.usage
  WHERE billing_origin_product = 'GENIE'
    AND usage_date >= '2026-08-01'
    AND usage_date <  DATE_TRUNC('MONTH', CURRENT_DATE)   -- apenas meses completos
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

Defina `:p_net_usd_per_dbu` = `P_net` do Passo 1. O resultado mostra **"quanto este mês teria custado a partir de fev/2027"**, que é o ponto de partida do run-rate.

## 6. Passo 4 — Segmentar os usuários em personas (para modelar cenários)

```sql
WITH per_user_month AS (
  SELECT DATE_TRUNC('MONTH', usage_date) AS month,
         identity_metadata.run_as        AS run_as,
         SUM(CASE WHEN sku_name <> 'GENIE_FREE_USAGE'
                  THEN usage_quantity / 0.75
                  ELSE usage_quantity END) AS dbus
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

Faixas de persona sugeridas (os limites vêm dos seus próprios percentis):

| Persona | Perfil típico | Regra prática |
|---|---|---|
| Iniciante | Perguntas ocasionais | ≤ p50, geralmente dentro da franquia de 150 DBUs → ~US$ 0 de LLM |
| Praticante | Uso regular, chat padrão | Entre p50 e p90 |
| Usuário intensivo | Agent mode, análises longas, criação com Genie Code | > p90. São esses usuários que concentram a maior parte da fatura |
| Service principal / aplicação | Integrações em produção (apps, MCP, batch) | 100% cobrável. Dimensione por aplicação |

Liste também os **20 maiores usuários e SPs** em DBUs (`ORDER BY dbus DESC LIMIT 20`) e confirme com cada área de negócio que o uso é legítimo e deve se repetir.

## 7. Passo 5 — Atribuir a computação do SQL warehouse ao Genie

O custo de LLM do Genie muitas vezes **não é a maior linha**: os warehouses que executam o SQL gerado podem custar mais. Use `query_source.genie_space_id` em `system.query.history` para identificar as queries dos Genie Agents e rateie o custo do warehouse pela participação delas no tempo de processamento:

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

Para detalhar **por Genie Agent**, agrupe `q` também por `query_source.genie_space_id`.

Ressalvas e recomendações:

- O rateio proporcional não captura o **tempo ocioso / auto-stop**. Se o warehouse for **dedicado ao Genie**, use 100% do custo dele. Essa é a configuração mais precisa e **a prática recomendada** para os Genie Agents em produção.
- As queries do Genie One podem não trazer `genie_space_id`. Use `client_application` / `executed_by` como aproximação e trate a computação do Genie One como estimativa. (Uma franquia gratuita de computação, em regime de melhor esforço, para o Genie One está em Beta.)

## 8. Passo 6 — Montar custos unitários (custo por pergunta / por usuário ativo)

Com custos unitários, a previsão passa a partir de **direcionadores de negócio** (usuários, agents, perguntas) em vez de DBUs.

**8.1 Identificar as ações de auditoria relevantes** (os nomes das ações são diferentes entre Genie Agents e Genie One):

```sql
SELECT service_name, action_name, COUNT(*) AS events
FROM system.access.audit
WHERE service_name IN ('aibiGenie', 'genieChat')
  AND event_date >= '2026-08-01'
GROUP BY ALL
ORDER BY events DESC;
```

**8.2 Perguntas e usuários ativos por mês, por Genie Agent.** Substitua a lista de ações pelas ações de criação de mensagem encontradas na 8.1:

```sql
SELECT DATE_TRUNC('MONTH', event_date)                  AS month,
       request_params['space_id']                       AS genie_space_id,
       COUNT(*)                                         AS questions,
       COUNT(DISTINCT user_identity.email)              AS active_users
FROM system.access.audit
WHERE service_name = 'aibiGenie'
  AND action_name IN ('<ações de criação de mensagem da 8.1>')
  AND event_date >= '2026-08-01'
GROUP BY ALL
ORDER BY month, questions DESC;
```

**8.3 Economia unitária**, combinando os Passos 2 a 5 e a 8.2:

| KPI | Fórmula |
|---|---|
| DBUs de LLM por pergunta (Agents) | `DBUs de GENIE_AGENTS / perguntas` |
| Custo de LLM por pergunta | `DBUs por pergunta × P_net` |
| Custo de warehouse por pergunta | `genie_attributed_cost_usd / genie_queries` (Passo 5) |
| **Custo total por pergunta** | LLM + warehouse |
| Custo por usuário ativo por mês | `(LLM cobrável + warehouse) / usuários ativos` |

Acompanhe esses KPIs por Genie Agent. Um custo por pergunta alto costuma ter uma causa corrigível, como uso pesado de Agent mode, instruções ou metadados fracos, ou um warehouse superdimensionado ou sempre ligado.

## 9. Passo 7 — Projetar o próximo ano fiscal (modelo de cenários)

Parta do run-rate dos Passos 3 e 5 e aplique os direcionadores mês a mês:

```
Custo mensal do Genie(m) =
    Σ_personas [ usuários_p(m) × max(0, DBU_médio_p(m) − 150) ] × P_net   ← LLM de humanos (todos os produtos)
  + Σ_apps     [ DBUs_SP_app(m) ] × P_net                                  ← service principals
  + Σ_agents   [ perguntas_a(m) × custo_warehouse_por_pergunta_a ]        ← computação SQL
  + novos_casos_de_uso(m)                                                  ← pipeline (Passo 8)
  × (1 + adicional de plataforma, ex.: ESC, se aplicável)
```

Onde `P_net = P_list × (1 − desconto contratual SRTI)`. A partir de fev/2027 não há mais fator promocional.

Observações sobre o calendário:

- **Jan/2027:** Genie Agents e Genie One ainda são gratuitos, e o Genie Code ainda tem a promoção de 25%.
- **Fev/2027 em diante:** valem as regras completas pós-promoção. Se o ano fiscal for de janeiro a dezembro, são **11 meses cobráveis** para Agents e One.

Monte três cenários:

| Cenário | Crescimento de usuários | DBU / usuário | Uso por SP / aplicações | Novos Genie Agents |
|---|---|---|---|---|
| Conservador | Usuários ativos atuais, estável | p50/p75 atuais | Atual | Nenhum |
| Base | Plano de expansão das áreas | +10–20% (mais Agent mode) | Aplicações planejadas | Pipeline confirmado |
| Agressivo | Toda a população-alvo | Cresce a proporção de usuários intensivos | Todas as aplicações planejadas em produção | Pipeline completo |

Dicas:

- O histórico só começa em meados de 2026, **curto demais para uma previsão estatística**. Use a série para calibrar os cenários. Se quiser uma linha de tendência, a função `ai_forecast()` do Databricks SQL projeta a série mensal, mas trate o resultado apenas como indicativo.
- Adicione uma **margem de 10–20%** para usuários intensivos e para a curva de adoção. A expansão do Genie One e novas funcionalidades (anexos de arquivos, busca em volumes, sub-agents) tendem a aumentar o uso.
- Mantenha uma **linha separada para o Genie Code** (desenvolvedores que criam e mantêm os Agents). É uma persona e um orçamento diferentes dos usuários consumidores.

## 10. Passo 8 — Dimensionar novos casos de uso ainda sem histórico

Os Genie Agents planejados para o próximo ano ainda não têm dados nas system tables. Use uma destas opções:

1. **Um piloto de 2 a 4 semanas** com um grupo representativo de usuários, medido com os Passos 2 a 8. É a opção mais confiável.
2. **A calculadora de dimensionamento de Genie Agents/One da Databricks.** O time de conta Databricks pode rodá-la junto com você: entra a quantidade de usuários por persona, sai a estimativa mensal de LLM. Ela **não inclui a computação SQL nem o Genie Code**, então some esses valores a partir do Passo 5 ou do Passo 8.
3. **Analogia:** use o custo unitário por pergunta de um Genie Agent parecido que já exista.

## 11. Passo 9 — Implementar controles **antes de 01/02/2027**

| Controle | Como | Recomendação |
|---|---|---|
| **Budget do Genie** | Account Console → *Usage → Budgets* → tipo de recurso **Unity Gateway**, tag `databricks-product = genie` (sem outras tags) | Crie agora. Durante a promoção ele acompanha o Genie Code. A partir de 01/02 passa a cobrir também Agents e One |
| **Limite compartilhado** (pool) | Pool mensal para todos os usuários no escopo | **Apenas alerta**, em 80% e 100%. Evite *Block usage* aqui, porque bloqueia todo mundo no escopo |
| **Limite por usuário** | Limite mensal padrão por usuário, além da franquia gratuita | Defina a partir do percentil de Iniciante/Praticante (Passo 4), com *Block usage* |
| **Overrides** | Por usuário ou grupo (até 100 por budget) | Um grupo de conta por persona (ex.: `genie-power-users`) com limite maior, mais um processo de aprovação para entrar no grupo |
| **Webhooks / e-mail** | Por limite | Envie para o FinOps e para o responsável da área |
| **Warehouses dedicados** | Um warehouse Serverless por área/domínio para os Genie Agents | Atribuição exata da computação e controle do auto-stop |
| **Padrão de identidade** | Prefira **OBO / repasse da identidade do usuário** a service principals em aplicações voltadas a usuários | Dá atribuição por usuário e aproveita a franquia de 150 DBUs de cada um. Uso por SP é 100% cobrável |

Limitações a conhecer:

- Os budgets **ainda não podem ser separados por produto** (Code vs Agents vs One), porque todos usam a mesma tag. Use `usage_metadata.genie.surface` nos relatórios.
- Para ter limites diferentes por produto hoje, crie **um grupo por público de cada produto** (ex.: `genie-code-users`, `genie-consumers`), cada um com seu próprio limite por usuário.
- Os budgets são **estimativas quase em tempo real**. A fonte oficial é `system.billing.usage`, atualizada a cada poucas horas.
- Os budgets acompanham o gasto a **preço de lista**. Incluem a promoção e os adicionais, mas **não o desconto contratual**, então defina os limites em termos de preço de lista.
- Um budget criado no meio do mês considera o uso desde o dia 1º.
- Admins de workspace podem gerenciar budgets dos próprios workspaces pelo Governance Hub (Beta), o que ajuda a dar autonomia a cada área.
- Até 31/01/2027, os budgets por usuário **não têm efeito** sobre o uso de Genie Agents e One por humanos, que é gratuito. Planeje **revisar os limites em janeiro de 2027** para que estejam prontos quando a cobrança começar.
- Os budgets não cobrem a computação dos warehouses. Para isso, use os budgets padrão de DBSQL e tags nos warehouses.

## 12. Passo 10 — Operacionalizar: dashboard mensal de FinOps do Genie

1. Salve as queries dos Passos 1 a 8 em um **dashboard AI/BI**, com páginas de *Run-rate*, *Por usuário/persona*, *Por Genie Agent*, *Atribuição de warehouse* e *Previsto vs Realizado*.
2. Agende uma atualização mensal e uma assinatura para o FinOps e os responsáveis das áreas.
3. Todo mês, compare o realizado com o cenário e recalibre a previsão, principalmente depois de fev/2027, quando a cobrança real começa.
4. Revise os usuários, SPs e Agents com maior custo por pergunta e otimize as instruções, o uso de Agent mode e o dimensionamento dos warehouses.

## 13. Premissas e pontos em aberto a confirmar com a Databricks

| # | Tema | Status |
|---|---|---|
| 1 | A promoção gratuita de Genie Agents e Genie One termina em **31/01/2027** | Release notes e documentação públicas |
| 2 | A franquia de 150 DBUs/usuário/mês é **compartilhada** entre todos os produtos Genie e **não vale para SPs** | Documentação pública |
| 3 | A promoção de 25% termina em 31/01/2027. Hoje os DBUs cobrados do Genie são reduzidos na medição (÷0,75 para normalizar) | Confirmado pela Databricks |
| 4 | Após 01/02, o SKU de cobrança de Agents e One é o mesmo SKU SRTI regional do Genie Code | Confirmado (um único SKU SRTI, identificado por produto). Confirme o SKU regional exato no Passo 1 |
| 5 | Genie Agents de alto volume (ex.: aplicações com SP) podem usar **Reserved Capacity / Provisioned Throughput** em vez do pay-as-you-go | Disponível sob consulta. Vale discutir com a Databricks se o volume de SP for grande e previsível |
| 6 | O adicional ESC / compliance incide sobre os $DBUs do Genie | Confirmar se se aplica aos seus workspaces |
| 7 | Computação do Genie One: franquia gratuita de melhor esforço (nível de conta) | Em Beta. Não conte com ela na previsão |
| 8 | Dados de custo mais granulares (por conversa/pergunta) nas system tables | No roadmap. Por enquanto, use as aproximações do Passo 6 |
| 9 | Futuros adicionais (ex.: Genie Ontology) | Não incluídos nesta previsão. Adicione como linha separada quando o preço for publicado |
| 10 | Desconto contratual `d` e consumo do commit | Confirmar com o executivo de conta da Databricks |

## Apêndice A — Modelo de previsão (preencher mês a mês)

| Mês | Usuários humanos ativos | DBU médio/usuário | DBUs cobráveis (humanos) | DBUs de SP | Custo LLM (US$) | Warehouse do Genie (US$) | Genie Code (US$) | Novos casos de uso (US$) | **Total (US$)** |
|---|---|---|---|---|---|---|---|---|---|
| Jan/27 (promoção) | | | 0 (Agents/One) | | | | (25% de desconto) | | |
| Fev/27 | | | | | | | | | |
| Mar/27 | | | | | | | | | |
| … | | | | | | | | | |
| Dez/27 | | | | | | | | | |
| **Total do ano** | | | | | | | | | |
