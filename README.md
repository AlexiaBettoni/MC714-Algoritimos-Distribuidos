# MC714 — Algoritmos Distribuídos

Implementação de monitoramento por heartbeat e eleição Bully para o Trabalho 2.

## Executar a matriz experimental

Requisitos: Docker Engine/Desktop com Docker Compose v2 e Python 3.10 ou superior. Na raiz do repositório:

```bash
python3 scripts/run_experiments.py
```

No Windows (PowerShell), use `python` no lugar de `python3`. Apenas o atalho `run_kill.sh` exige bash (WSL ou Git Bash).

Por padrão, o script executa duas repetições com seeds independentes para:

- operação normal com cinco nós;
- crash do coordenador (`node5`) com cinco nós;
- três taxas de perda (0%, 5% e 15%) em ambos os cenários.

Isso totaliza 12 execuções: dois cenários × três níveis de perda × duas seeds. É a configuração mínima do script que cobre operação normal, falha do coordenador, três níveis de um parâmetro e repetições independentes. Duas repetições são o mínimo literal; cinco ou mais são preferíveis para estimativas mais confiáveis de variabilidade e percentis.

Cada execução espera quinze segundos de aquecimento, tempo maior que o período de graça inicial dos nós (`START_GRACE`, 8 segundos). Após o crash, observa o cluster por pelo menos oito segundos (ou três timeouts). O script constrói a imagem uma vez, gera um `compose.yaml` por execução, salva os metadados e os logs JSON brutos e remove os contêineres daquele ensaio.

Exemplo com cinco repetições por configuração:

```bash
python3 scripts/run_experiments.py \
  --nodes 5 --loss-rates 0,0.05,0.15 --repetitions 5 \
  --timeout 2 --interval 0.5 --warmup 15 --observe 8
```

Os resultados do relatório foram gerados com dez repetições (`--repetitions 10`).

Para estudar escalabilidade, passe três tamanhos, como `--nodes 3,5,7`. Isso aumenta a matriz proporcionalmente; não é necessário para cumprir o requisito de variar um parâmetro, já satisfeito pela perda de mensagens.

Para executar só o crash do coordenador com cinco nós:

```bash
python3 scripts/run_experiments.py --scenario coordinator_crash --nodes 5 --loss-rates 0 --repetitions 2
```

Os resultados são criados em `results/experiments/<data-hora>/`. Para rodar uma única repetição de falha, use o atalho (bash):

```bash
NODES=5 LOSS_RATE=0 SEED=1 scripts/run_kill.sh
```

## Analisar os resultados

Passe o diretório da execução indicado pelo script:

```bash
python3 scripts/analyze.py results/experiments/<data-hora>
```

O analisador gera `metrics.csv` (uma linha por execução) e `summary.json` (média, desvio padrão, p50 e p95 por cenário). As métricas incluem latência de detecção, tempo de convergência para o novo coordenador, suspeitas falsas e contagem de mensagens de eleição. Os logs brutos e o Compose gerado permanecem em cada diretório `run-*` para auditoria e reprodução.

Para verificar as propriedades de correção a partir dos logs (completude, tempo de detecção limitado, ausência de suspeitas falsas, acordo sobre o líder, líder único e convergência da eleição):

```bash
python3 scripts/check_properties.py results/experiments/<data-hora>
```

O script imprime `PASS`, `FAIL` ou `INFO` para cada execução e grava `checks.json`. Sem perda de mensagens, todas as verificações são estritas; com perda, apenas a completude e o tempo de detecção são estritos, e as demais aparecem como `INFO`. O código de saída é 1 se alguma verificação estrita falhar.

Para investigar uma execução (defasagem de partida dos nós, pausas entre heartbeats, erros de envio e primeiras suspeitas):

```bash
python3 scripts/diagnose_run.py results/experiments/<data-hora>/<diretório-run>
```

## Visualizar mensagens entre nós

Gere um diagrama de sequência SVG para uma execução:

```bash
python3 scripts/visualize_messages.py results/experiments/<data-hora>/<diretório-run>
```

O padrão mostra mensagens Bully (`ELECTION`, `OK` e `COORDINATOR`) e marca o momento em que o nó foi derrubado. A sequência é dividida em duas linhas cronológicas, cada uma avançando da esquerda para a direita; os nós ocupam linhas horizontais e as mensagens aparecem como setas coloridas entre elas, com timestamp relativo. A legenda identifica os tipos e o título inclui os parâmetros registrados para a execução. O SVG é salvo como `messages.svg` dentro do diretório da execução. Para incluir também heartbeats, use `--include-heartbeats`; como eles são frequentes, a figura limita-se a 500 setas por padrão e conserva as mensagens do início e do fim. Ajuste o espaço horizontal entre mensagens com `--spacing 110`, o limite com `--max-messages 1000` ou o arquivo com `--output figura.svg`. No Windows, se ocorrer `UnicodeEncodeError`, defina `PYTHONUTF8=1` antes de executar.

## Interpretação e limitações

`LOSS_RATE` descarta mensagens recebidas de forma pseudoaleatória, incluindo heartbeats e mensagens de eleição. No cenário normal, a perda ajuda a observar suspeitas falsas. No cenário de crash, ela também mostra o efeito da perda sobre detecção e eleição. O ensaio de crash mata o nó de maior ID para exercitar a eleição de um novo coordenador. Os nós são contêineres no mesmo host e não representam domínios de falha independentes. O seed é registrado; escalonamento de threads e rede local podem fazer execuções com o mesmo seed seguirem traços diferentes.

As mensagens `OK` e `COORDINATOR` são enviadas uma única vez, sem retransmissão, e os heartbeats não carregam informação de líder. Com perda de mensagens, um nó que perde o anúncio pode manter um líder desatualizado; por isso o acordo sobre o líder só é garantido sem perda. A ausência de suspeitas falsas sem perda pressupõe que todos os contêineres fiquem acessíveis dentro de `START_GRACE` segundos. O instante da falha é registrado antes de `docker compose kill`, então os tempos de detecção e de convergência incluem a latência desse comando. No cenário normal, o tempo de convergência inclui a criação dos contêineres e não deve ser lido como tempo de eleição.

Cada nó registra mensagens enviadas e recebidas, inclusive heartbeats. Para avaliar o custo do Bully, use a contagem de mensagens `ELECTION`, `OK` e `COORDINATOR`; não some heartbeats nessa métrica.