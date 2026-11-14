# Rascunho do relatório — detector de falhas e eleição Bully

> Texto-base para adaptação ao formato IEEE. Os resultados experimentais ainda devem ser preenchidos após a execução da matriz; não interpretar os campos entre colchetes como resultados medidos.

## Arquitetura e modelo do sistema

O sistema combina dois algoritmos distribuídos: um detector de falhas baseado em heartbeat e o algoritmo de eleição Bully. Cada nó lógico executa em um contêiner independente. Os nós se comunicam diretamente por datagramas UDP na rede privada do Docker Compose, com associação completa conhecida previamente por meio da variável `PEERS`. Os identificadores são ordenáveis (`node1` a `nodeN`), e o maior identificador representa a maior prioridade na eleição.

Cada nó transmite heartbeats a cada `HB_INTERVAL` segundos e registra o horário do último heartbeat recebido de cada participante. Se o silêncio exceder `HB_TIMEOUT`, o nó registra uma suspeita. Uma suspeita é uma inferência local, não uma prova de falha: perda de pacotes ou atraso de escalonamento também podem causar suspeitas falsas. Se o nó suspeitar do coordenador, inicia uma eleição.

Na eleição Bully, o iniciador envia `ELECTION` aos nós de maior prioridade. Um nó superior responde `OK` e inicia sua própria eleição. Se o iniciador não receber `OK` até o timeout, anuncia a si mesmo com `COORDINATOR`. Caso receba `OK`, aguarda o anúncio de um nó superior; se o anúncio não chegar, tenta novamente. Os tipos de mensagem e eventos do protocolo são registrados em JSON nos logs dos contêineres.

O modelo adotado é parcialmente síncrono: heartbeats e mensagens são esperados dentro de prazos configurados, mas os timeouts podem expirar diante de atraso ou perda. UDP não garante entrega nem retransmissão. O experimento injeta perdas aleatórias configuráveis na aplicação e falhas crash-stop ao encerrar um contêiner. Não são modeladas falhas bizantinas nem recuperação de estado após reinício; todos os contêineres executam no mesmo host, portanto não representam domínios de falha físicos independentes. O código usa relógio de parede para timestamps dos logs e relógio monotônico para esperas de eleição; o estado do coordenador é mantido em memória.

As propriedades a avaliar são: (1) em uma execução sem falha e sem perda, o detector não deve suspeitar de nós ativos; (2) após a queda do coordenador, os nós sobreviventes devem suspeitá-lo e convergir para o maior identificador sobrevivente; (3) o custo e a latência devem ser medidos sob diferentes probabilidades de perda. Essas propriedades dependem da hipótese de que mensagens entre nós sobreviventes eventualmente sejam entregues e processadas.

## Ambiente e reprodução

O ambiente de referência é Docker Compose v2 em uma única máquina. `scripts/run_experiments.py` constrói a imagem da aplicação, gera uma configuração Compose isolada por execução, inicia os nós, injeta a falha quando aplicável, captura os logs e encerra os contêineres. Cada execução salva o Compose gerado, metadados e log JSON bruto. A seed, parâmetros e versões de Python, Docker e Compose são registrados no manifesto do lote. `scripts/analyze.py` produz métricas por execução em CSV e estatísticas agrupadas em JSON. `scripts/visualize_messages.py` gera um diagrama SVG das mensagens Bully para uma execução individual.

Com Docker Engine/Desktop, Compose v2 e Python 3.10 ou superior, a matriz mínima configurada é iniciada na raiz do repositório com:

```bash
python3 scripts/run_experiments.py
```

O padrão fixa cinco nós, usa `HB_INTERVAL=0,5 s` e `HB_TIMEOUT=2 s`, aquece cada execução por 6 s e observa a operação normal por 8 s. Após a falha, a observação dura pelo menos 8 s ou três timeouts, o que for maior. Os resultados são gravados em `results/experiments/<data-hora>/`. Para analisar um lote:

```bash
python3 scripts/analyze.py results/experiments/<data-hora>
```

## Plano experimental e métricas

A matriz padrão contém 12 execuções: dois cenários (`normal` e `coordinator_crash`), três taxas de perda (`0`, `0,05` e `0,15`) e duas seeds independentes por configuração. No cenário de falha, o nó de maior prioridade (`node5`) é encerrado após o aquecimento; o resultado esperado é a convergência dos sobreviventes para `node4`. A variação de perda fornece três níveis de um parâmetro relevante para ambos os algoritmos. Uma variação adicional do número de nós (por exemplo, 3, 5 e 7) pode ser executada com `--nodes 3,5,7`, mas não faz parte da matriz mínima.

Os resultados devem ser apresentados separadamente para cada algoritmo, mesmo quando provêm das mesmas execuções:

| Algoritmo | Evidência nos cenários | Métricas |
|---|---|---|
| Detector por heartbeat | Ausência de suspeitas em operação sem perda; detecção do nó encerrado; suspeitas falsas sob perda | Latência de detecção, suspeitas falsas |
| Eleição Bully | Eleição inicial; adoção de `node4` após queda de `node5`; mensagens perdidas e convergência sob perda | Tempo de convergência, mensagens `ELECTION` + `OK` + `COORDINATOR` |

Para um nó encerrado em `t_kill`, a latência de detecção é `t_first_suspect − t_kill`. O tempo de convergência é o instante em que o último nó sobrevivente registra o novo coordenador, menos `t_kill`; deve ser reportado como não convergido se algum sobrevivente não o adotar durante a janela. A contagem de mensagens Bully inclui os três tipos de eleição enviados após o evento de interesse e exclui heartbeats. Para cada configuração, reportar média, desvio padrão e percentis de latência (p50 e p95). Duas seeds são o mínimo configurado; cinco ou mais são recomendadas para estimativas mais estáveis.

Além das métricas agregadas, os logs devem ser verificados quanto às propriedades de correção: inexistência de suspeitas indevidas na execução sem perda e convergência de todos os sobreviventes ao coordenador esperado nos cenários de crash. O analisador atual calcula métricas, mas ainda não produz um veredito automático de aprovação/reprovação dessas propriedades; os resultados devem ser conferidos nos eventos `suspect`, `coordinator_elected` e `coordinator_changed`.

## Resultados a preencher

- Hardware, sistema operacional e versões das ferramentas: [copiar do manifesto e complementar com os detalhes do host].
- Execuções concluídas por configuração: [número; registrar falhas de execução ou logs incompletos].
- Detector de falhas — detecção e suspeitas falsas por nível de perda: [inserir tabela/gráfico e interpretação].
- Bully — convergência e mensagens por nível de perda: [inserir tabela/gráfico e interpretação].
- Limitações observadas, incluindo falsos positivos e execuções sem convergência: [preencher].

Figuras sugeridas: (1) diagrama de sequência SVG de uma eleição após crash; (2) latência de detecção e convergência por taxa de perda, com pontos por seed; (3) suspeitas falsas e mensagens Bully por taxa de perda. Não incluir valores antes de executar e analisar os ensaios.

## Referências

[1] M. van Steen e A. S. Tanenbaum, *Distributed Systems*, 4ª ed., 2023.

[2] Enunciado do Trabalho 2, MC714 — Sistemas Distribuídos, 2º semestre de 2026.
