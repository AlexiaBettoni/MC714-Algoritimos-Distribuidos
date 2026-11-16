# Relatório da bateria 20261116-155404-721367

## 1. Ambiente e configuração

| Item | Valor |
|---|---|
| Data/hora de início | 2026-11-16T15:54:04.721628-03:00 |
| Duração total | 14 min 30 s |
| Sistema operacional | Windows-11-10.0.26300-SP0 |
| Processador | Intel64 Family 6 Model 154 Stepping 4, GenuineIntel |
| CPUs lógicas | 12 |
| Python | 3.13.0 |
| Docker | Docker version 29.9.2, build a82e528 |
| Docker Compose | Docker Compose version v5.6.1 |
| Algoritmos | Detector de falhas por heartbeat (UDP) + eleição Bully |
| Cenários | normal, coordinator_crash |
| Nº de nós | 5 |
| Taxas de perda | 0, 0.05, 0.15 |
| Repetições por configuração | 5 (seeds 1–5) |
| Heartbeat / Timeout | 0.5 s / 2.0 s |
| Warmup / Observação | 15.0 s / 8.0 s |
| Total de execuções | 30 |
| Tolerância usada nos limites de tempo | 1 s (absorve a latência do `docker compose kill`) |

## 2. Resumo geral

- Execuções: 30 | Completas: 30 | Com falha estrita de propriedade: 6
- Execuções com erro/sem log: 0

Propriedades verificadas (aprovadas/aplicáveis):

| Propriedade | Sem perda | Com perda | Natureza |
|---|---|---|---|
| Sem falsa susp. | 10/10 | 16/20 | estrita só sem perda |
| Completude | 5/5 | 10/10 | estrita |
| Detecção limitada | 5/5 | 10/10 | estrita |
| Acordo de líder | 4/10 | 10/20 | estrita só sem perda |
| Líder único | 4/5 | 4/10 | estrita só sem perda |
| Convergência | 4/5 | 8/10 | estrita só sem perda |

Sob perda de mensagens, falhas não estritas são apenas informativas (INFO): o modelo de canal do detector não garante exatidão com perdas.

## 3. Resumo por configuração

Formato das células: média ± desvio · p50 · p95 (entre as repetições). Mensagens de eleição = ELECTION + OK + COORDINATOR enviadas após a falha (no cenário normal, desde o início, incluindo a eleição inicial).

| Cenário | N | Perda | Reps | Convergiu | Detecção máx (s) | Convergência (s) | Msgs eleição | Falsas susp. |
|---|---|---|---|---|---|---|---|---|
| coordinator_crash | 5 | 0 | 5 | 4/5 | 2.05 ± 0.14 · p50 2.03 · p95 2.19 | 3.96 ± 0.10 · p50 3.94 · p95 4.08 | 13.4 ± 11.2 · p50 13.0 · p95 25.4 | 0.0 ± 0.0 · p50 0.0 · p95 0.0 |
| coordinator_crash | 5 | 0.05 | 5 | 4/5 | 1.97 ± 0.09 · p50 1.98 · p95 2.08 | 3.93 ± 0.12 · p50 3.94 · p95 4.04 | 12.6 ± 9.3 · p50 8.0 · p95 24.0 | 0.0 ± 0.0 · p50 0.0 · p95 0.0 |
| coordinator_crash | 5 | 0.15 | 5 | 3/5 | 2.15 ± 0.06 · p50 2.17 · p95 2.19 | 4.24 ± 0.65 · p50 4.08 · p95 5.01 | 29.8 ± 14.6 · p50 30.0 · p95 46.8 | 0.6 ± 0.9 · p50 0.0 · p95 1.8 |
| normal | 5 | 0 | 5 | 0/5 | — | — | 10.8 ± 3.6 · p50 10.0 · p95 14.8 | 0.0 ± 0.0 · p50 0.0 · p95 0.0 |
| normal | 5 | 0.05 | 5 | 1/5 | — | — | 13.0 ± 10.1 · p50 6.0 · p95 26.2 | 0.0 ± 0.0 · p50 0.0 · p95 0.0 |
| normal | 5 | 0.15 | 5 | 2/5 | — | — | 23.6 ± 17.3 · p50 18.0 · p95 45.8 | 0.6 ± 0.9 · p50 0.0 · p95 1.8 |

## 4. Verificação de propriedades por execução

| Execução | Sem falsa susp. | Completude | Detecção limitada | Acordo de líder | Líder único | Convergência |
|---|---|---|---|---|---|---|
| run-001-normal-n5-loss0-seed1 | PASS | — | — | FAIL | — | — |
| run-002-normal-n5-loss0-seed2 | PASS | — | — | FAIL | — | — |
| run-003-normal-n5-loss0-seed3 | PASS | — | — | FAIL | — | — |
| run-004-normal-n5-loss0-seed4 | PASS | — | — | FAIL | — | — |
| run-005-normal-n5-loss0-seed5 | PASS | — | — | FAIL | — | — |
| run-006-normal-n5-loss0.05-seed1 | PASS | — | — | INFO | — | — |
| run-007-normal-n5-loss0.05-seed2 | PASS | — | — | INFO | — | — |
| run-008-normal-n5-loss0.05-seed3 | PASS | — | — | INFO | — | — |
| run-009-normal-n5-loss0.05-seed4 | PASS | — | — | PASS | — | — |
| run-010-normal-n5-loss0.05-seed5 | PASS | — | — | INFO | — | — |
| run-011-normal-n5-loss0.15-seed1 | PASS | — | — | INFO | — | — |
| run-012-normal-n5-loss0.15-seed2 | INFO | — | — | PASS | — | — |
| run-013-normal-n5-loss0.15-seed3 | INFO | — | — | PASS | — | — |
| run-014-normal-n5-loss0.15-seed4 | PASS | — | — | INFO | — | — |
| run-015-normal-n5-loss0.15-seed5 | PASS | — | — | INFO | — | — |
| run-016-coordinator_crash-n5-loss0-seed1 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-017-coordinator_crash-n5-loss0-seed2 | PASS | PASS | PASS | FAIL | FAIL | FAIL |
| run-018-coordinator_crash-n5-loss0-seed3 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-019-coordinator_crash-n5-loss0-seed4 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-020-coordinator_crash-n5-loss0-seed5 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-021-coordinator_crash-n5-loss0.05-seed1 | PASS | PASS | PASS | INFO | INFO | INFO |
| run-022-coordinator_crash-n5-loss0.05-seed2 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-023-coordinator_crash-n5-loss0.05-seed3 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-024-coordinator_crash-n5-loss0.05-seed4 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-025-coordinator_crash-n5-loss0.05-seed5 | PASS | PASS | PASS | PASS | PASS | PASS |
| run-026-coordinator_crash-n5-loss0.15-seed1 | PASS | PASS | PASS | INFO | INFO | PASS |
| run-027-coordinator_crash-n5-loss0.15-seed2 | INFO | PASS | PASS | INFO | INFO | INFO |
| run-028-coordinator_crash-n5-loss0.15-seed3 | INFO | PASS | PASS | PASS | INFO | PASS |
| run-029-coordinator_crash-n5-loss0.15-seed4 | PASS | PASS | PASS | PASS | INFO | PASS |
| run-030-coordinator_crash-n5-loss0.15-seed5 | PASS | PASS | PASS | PASS | INFO | PASS |

PASS = ok · FAIL = violação estrita · INFO = não estrita (esperado sob perda) · — = não se aplica

### Detalhes das falhas estritas

- `run-001-normal-n5-loss0-seed1` — leader_agreement: esperado node5, visões finais {'node2': 'node4', 'node3': 'node3', 'node4': 'node4'}
- `run-002-normal-n5-loss0-seed2` — leader_agreement: esperado node5, visões finais {'node1': 'node1'}
- `run-003-normal-n5-loss0-seed3` — leader_agreement: esperado node5, visões finais {'node1': 'node3', 'node2': 'node3', 'node3': 'node3'}
- `run-004-normal-n5-loss0-seed4` — leader_agreement: esperado node5, visões finais {'node2': 'node2', 'node3': 'node3'}
- `run-005-normal-n5-loss0-seed5` — leader_agreement: esperado node5, visões finais {'node3': 'node3'}
- `run-017-coordinator_crash-n5-loss0-seed2` — leader_agreement: esperado node4, visões finais {'node1': 'node3', 'node3': 'node3'}
- `run-017-coordinator_crash-n5-loss0-seed2` — single_leader: nós que se declararam líder após a falha: []
- `run-017-coordinator_crash-n5-loss0-seed2` — election_convergence: nem todos os nós adotaram o novo líder

## 5. Arquivos

- `events.csv` — eventos principais de cada execução (suspeita, falha, restauração, eleição…)
- `metrics.csv` — métricas por execução
- `manifest.json` — configuração da bateria
- `run-XXX-*/raw.jsonl` — logs brutos; `run-XXX-*/metadata.json` — parâmetros da execução
