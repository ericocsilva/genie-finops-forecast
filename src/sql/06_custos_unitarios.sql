-- Genie FinOps — passo a passo do guia de previsão. Fonte: system tables.
-- Passos 0–6 leem direto de system.*; passos 1.3, 6.3, 7 e 8 leem as views criadas pelo job no esquema do bundle
-- (selecione no SQL Editor o catálogo/esquema configurados no bundle; padrão do esquema: genie_finops).
-- Para limitar a workspaces específicos, acrescente: AND workspace_id IN ('<id1>', '<id2>')
-- Passo 6.1 — Quais ações de auditoria existem para o Genie?
SELECT service_name, action_name, COUNT(*) AS events
FROM system.access.audit
WHERE service_name IN ('aibiGenie', 'genieChat')
  AND event_date >= '2026-08-01'
GROUP BY ALL
ORDER BY events DESC;

-- Passo 6.2 — Perguntas e usuários ativos por Genie Agent/mês
SELECT DATE_TRUNC('MONTH', event_date)          AS month,
       request_params['space_id']               AS genie_space_id,
       COUNT(*)                                 AS questions,
       COUNT(DISTINCT user_identity.email)      AS active_users
FROM system.access.audit
WHERE service_name = 'aibiGenie'
  AND action_name IN ('genieStartConversationMessage', 'genieCreateConversationMessage', 'createConversationMessage',
                      'genieCreateAgenticResponse', 'createAgenticResponse')
  AND event_date >= '2026-08-01'
GROUP BY ALL
ORDER BY month, questions DESC;

-- Passo 6.3 — Economia unitária consolidada (view da demo)
SELECT month, agent_name, questions, ROUND(agent_mode_share, 3) AS agent_mode_share,
       ROUND(llm_cost_per_question_usd, 3) AS llm_usd, ROUND(warehouse_cost_per_question_usd, 3) AS warehouse_usd,
       ROUND(total_cost_per_question_usd, 3) AS total_usd
FROM v_unit_costs ORDER BY month DESC, total_usd DESC;
