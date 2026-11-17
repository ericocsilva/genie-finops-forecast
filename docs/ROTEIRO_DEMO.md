# Roteiro de demonstração — Genie FinOps & Previsão FY2027

**Duração sugerida:** 30–40 min · **Público:** plataforma/FinOps e responsáveis das áreas
**Objetivo:** mostrar, com os **dados reais das system tables do cliente**, como prever hoje o gasto com Genie no próximo ano fiscal,
usando apenas recursos nativos (system tables, SQL, AI/BI dashboards e budgets).

> Todos os números vêm das system tables do workspace/conta em que o bundle foi implantado. Os únicos valores digitados são as
> **premissas da previsão** (desconto contratual, adicional ESC, margem e crescimento por cenário), editáveis na tabela `forecast_assumptions`/`forecast_scenarios`.

---

## 0. Preparação (antes da reunião)

1. Garanta que o job rodou hoje: o agendamento é diário às 06:00. Se precisar, rode `databricks bundle run genie_finops_views -t <target>`.
2. Ajuste as premissas com os valores comerciais do cliente (desconto SRTI e SQL, ESC), ou deixe 0% para mostrar o preço de lista:
   `src/sql/08_what_if_premissas.sql`.
3. Abra em abas:
   - O dashboard **"Genie FinOps & Previsão FY2027"**, já atualizado (abra uma vez antes para aquecer o cache).
   - O SQL Editor com o catálogo do bundle e o esquema `genie_finops` selecionados.
   - Os arquivos `src/sql/*.sql` na pasta do bundle no workspace (abrem direto no SQL Editor).
   - (Opcional) Account Console → **Usage → Budgets**.
4. Ligue o SQL warehouse do dashboard.


---

## 1. Abertura — o que muda em 01/02/2027 (3 min)

Aba **Visão geral**, texto do topo:

- Até **31/01/2027**: Genie Agents e Genie One são gratuitos para usuários humanos. O Genie Code tem **150 DBUs/usuário/mês grátis** e **25% de desconto** no excedente.
- A partir de **01/02/2027**: **um único pool de 150 DBUs/usuário/mês** para Code + One + Agents. O excedente é cobrado no SKU **Serverless Real-Time Inference**, sem promoção.
- **Service principals nunca têm franquia** e já são cobrados hoje.
- **Computação SQL** é um custo separado e não entra no budget do Genie.

> 💬 "O Genie já mede tudo hoje, inclusive o uso gratuito, desde 20/07/2026. Então vamos olhar os dados de vocês, não premissas."

## 2. Passo 0 — As fontes (3 min) · `00_explorar_fontes.sql`

- `system.billing.usage` com `billing_origin_product = 'GENIE'`: o SKU `GENIE_FREE_USAGE` e as superfícies `GENIE_AGENTS`, `GENIE_ONE` e `GENIE_CODE`.

## 3. Passo 1 — SKU e preço (2 min) · `01_sku_e_preco.sql`

- O SKU SRTI em que o Genie é faturado, o preço de lista de `system.billing.list_prices` e o **preço líquido** com as premissas.

## 4. Passo 2 — Linha de base (4 min) · `02_linha_de_base.sql` + **Visão geral**

- `free_dbus` de `GENIE_AGENTS`/`GENIE_ONE` é o volume que **passa a ser cobrável** a partir de fevereiro.
- Linhas `SERVICE_PRINCIPAL` com `billed_dbus` > 0 são **custo que já existe hoje**.
- Gráfico **"DBUs já faturados hoje, por tipo de identidade"**.

> 💬 Ponto de atenção para aplicações em produção: com service principal, todo DBU é cobrado. Com **OBO** (repasse da identidade do usuário), o uso vai para o usuário final, que tem os 150 DBUs dele.

## 5. Passo 3 — Reprecificar com as regras de fev/2027 (5 min) · `03_reprecificar_pos_promocao.sql`

- As três regras:
  1. Franquia **por usuário**.
  2. Service principals pagam 100%.
  3. DBUs cobrados hoje ÷ 0,75 para remover a promoção.
- Defina `p_net_usd_per_dbu` com o valor de `srti_net_price_with_addon` (Passo 1.3).
- No dashboard:
  - KPIs **"Custo Genie hoje"** vs **"Mesmo uso com regras de fev/2027"**.
  - Gráfico **"Custo mensal: hoje vs regras de fev/2027"**.
  - KPI **"% usuários dentro da franquia"**.

## 6. Passo 4 — Personas (5 min) · `04_personas.sql` + **Usuários & personas**

- Percentis p50/p90 por mês, usuários por faixa de DBUs e a tabela **Top 25 identidades**.
- Mensagem: poucos usuários intensivos concentram a maior parte do custo. O **limite por usuário** do budget sai do percentil de Praticante, e os **overrides** ficam para os intensivos.

## 7. Passo 5 — Computação SQL (4 min) · `05_atribuicao_warehouse.sql` + **Genie Agents & warehouses**

- Custo de warehouse atribuído a cada Genie Agent (rateio pelo tempo de task).
- Warehouses **dedicados** ao Genie dão atribuição exata. Nos compartilhados, o rateio é proporcional.

## 8. Passo 6 — Custo por pergunta (3 min) · `06_custos_unitarios.sql`

- Tabela **"Economia unitária por Genie Agent"**: LLM/pergunta, warehouse/pergunta, total/pergunta e % Agent mode.

## 9. Passo 7 — Previsão FY2027 (5 min) · `07_previsao_fy.sql` + **Previsão FY2027**

- Os três cenários, com margem. A linha vertical em 31/01/2027 marca o fim da promoção (janeiro ainda é promocional).
- Barras do cenário Base por componente e a tabela mensal, que preenche o **Apêndice A** do guia.
- `ai_forecast()` como tendência indicativa (histórico curto).

## 10. Passo 8 — What-if ao vivo (3 min) · `08_what_if_premissas.sql` + **Premissas**

1. Aplique o desconto contratual real → **Refresh** no dashboard.
2. Ajuste o crescimento do cenário Base conforme o plano de expansão das áreas → **Refresh**.

## 11. Fechamento — controles antes de 01/02/2027 (3 min)

- **Account Console → Usage → Budgets**: tipo **Unity Gateway**, tag `databricks-product = genie`.
  - Limite compartilhado **só com alerta**.
  - Limite **por usuário** com *Block usage*.
  - Overrides por grupo de persona.
- Lembretes:
  - Budgets usam **preço de lista**.
  - Budgets não separam Code/Agents/One (use um grupo por público).
  - Budgets não cobrem warehouse.
- Próximos passos:
  1. Validar as premissas com o comercial.
  2. Rever o padrão de identidade das aplicações (OBO vs SP).
  3. Criar os budgets em janeiro/2027.

---

## Perguntas frequentes

| Pergunta | Resposta curta |
|---|---|
| Os 150 DBUs são por produto? | Não. É um único pool por usuário/mês, compartilhado entre Code, One e Agents (a partir de 01/02/2027). |
| O uso via API conta para a franquia? | Sim, se a identidade do usuário chegar ao Genie (OBO). Se for service principal, é 100% cobrado. |
| Português custa mais? | Sim. Conteúdo em outros idiomas além do inglês usa mais tokens por pergunta. |
| O Genie One chamando um Genie Agent cobra em dobro? | Não. O trabalho de dados vai para `GENIE_AGENTS` e a orquestração para `GENIE_ONE`. |
| Por que o nome do Genie Agent aparece como ID? | As system tables não trazem o título do Agent. O dashboard mostra `workspace / id`. |
| O custo de warehouse entra no budget do Genie? | Não. Use budgets/tags de DBSQL e warehouses dedicados. |
