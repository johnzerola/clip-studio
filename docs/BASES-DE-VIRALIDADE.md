# Como o Codex avalia cortes

O V9 usa áudio, movimento e chat para detectar candidatos durante a captura. Para gravações, o V9 transcreve em blocos, ordena candidatos locais e pede ao Ollama para escolher as bordas dos trechos mais promissores com base nas frases. Ele valida as bordas, reordena e remove sobreposições. Sem modelo disponível, usa as regras locais. Nas transmissões da Twitch, clipes de espectadores são um sinal opcional com `TWITCH_CLIENT_ID` e `TWITCH_CLIENT_SECRET`.

Em replays sem candidatos pela fala, o V9 examina até três trechos curtos em 480p por movimento. Baixa em alta qualidade apenas os intervalos pré-selecionados. Esse modo avalia uma amostra deliberadamente pequena da gravação. Definir `CODEX_GEMINI_GAMEPLAY_KEY` autoriza a opção de enviar ao Gemini até três quadros do clipe final sem fala, quando a avaliação local por visão estiver indisponível. `CODEX_GEMINI_GAMEPLAY_MODEL` permite configurar o modelo. Ambas as configurações ficam no ambiente do usuário. Gemini pode cobrar pela chamada.

Na nota final, a memória consulta as regras editoriais versionadas e, quando existem dados suficientes para encontrar correspondências, até dois exemplos parecidos da fila SQLite do usuário. Os exemplos vêm da retenção informada, visualizações e decisão editorial da conta. O corte ainda passa por verificação técnica e editorial. Retenção observada e nota editorial são medidas diferentes.

## Revisão com Qwen

Em **Cortes gerados**, a opção **Revisar até 5 com IA** avalia o MP4 de cada corte em sequência. O V9 decodifica o arquivo, transcreve a faixa final e apresenta ao Qwen quatro quadros com tempo, a transcrição e os critérios locais na mesma solicitação. Os quadros representam começo, evolução e final. A avaliação usa gancho (20), contexto (15), ritmo (15), desfecho (25), clareza (15) e originalidade (10).

Para receber **Recomendado**, o corte precisa de 75/100 ou do mínimo configurado, o que for maior. Precisa ainda de contexto, clareza e desfecho identificáveis, sem bloqueio editorial. Só cortes recomendados pela avaliação multimodal são elegíveis ao piloto de postagem. Um corte parecido pode ficar fora do filtro **Só recomendados** mesmo com nota alta. Clipes antigos ficam **Sem revisão de IA** até passar por esse fluxo, e a reavaliação conserva os MP4s existentes.

O V9 adapta o teste dos primeiros dois segundos, o requisito de fazer sentido fora da live e a regra de preservar a consequência descritos na [seleção do OpenShorts](https://github.com/mutonby/openshorts/blob/main/docs/architecture/clip-selection.md).

## Correção automática após a montagem

Com a IA local habilitada, uma captura ou montagem automática gera primeiro um arquivo temporário. O Qwen avalia o MP4 e pode indicar um ajuste de contexto, desfecho, ritmo, enquadramento ou fala. O V9 aplica no máximo um ajuste permitido ao material original disponível e avalia a nova versão. Se o corte receber **Recomendado**, o V9 salva a versão aprovada. Se ficar abaixo, fica apenas o registro da decisão. Uma falha do modelo é registrada como revisão indisponível. O arquivo temporário também é limpo nesse caso.

Em replays, o V9 pode baixar até cinco segundos de margem em cada ponta. Em lives, usa a margem que ainda existe na janela de captura. O ajuste não cria cenas. Para fala, o V9 reforça a voz e pode usar um modelo de transcrição mais preciso se ele já estiver em cache.

## O que pesquisamos

| Fonte | O que mede | Uso no Codex |
| --- | --- | --- |
| [QVHighlights e Moment-DETR](https://github.com/jayleicn/moment_detr) | Seleção de intervalos e relevância visual para uma consulta de texto | Referência para anotar momentos em GTA e avaliar acerto de início e fim. |
| [Lighthouse](https://github.com/line/lighthouse) | Biblioteca de avaliação de modelos de localização de momentos por vídeo e áudio | Comparar detectores offline em uma amostra própria, fora da captura ao vivo. |
| [TVSum](https://github.com/yalesong/tvsum) | Importância de segmentos anotada por pessoas | Avaliar se a lista curta cobre acontecimentos importantes. |
| [KuaiRand](https://github.com/chongminggao/KuaiRand) | Feedback de recomendação em vídeos curtos, com exposições aleatórias | Estudar efeito da distribuição e do comportamento. A população é diferente da audiência do canal. |
| [Beyond Views](https://ojs.aaai.org/index.php/ICWSM/article/view/15031) | Relação entre audiência e tempo assistido no YouTube | Fundamenta o uso de retenção observada separada de alcance. |
| [YouTube Analytics](https://developers.google.com/youtube/analytics/metrics) | Retenção da sua conta por duração média e percentual assistido | Métricas reais para medir clipes depois de publicados. Registre o percentual e as views no app. |

O OpenShorts usa prompts estruturados e referencia técnicas úteis de seleção. A base de critérios com fonte e a memória SQLite do Codex já estão no pacote. Os bancos públicos acima são referências de avaliação. Dados brutos, pesos externos e mídias de terceiros ficam nos respectivos projetos.

## Como comparar versões

Use as mesmas gravações de GTA e entrevistas, com exemplos de ação silenciosa, reação contextualizada, espera e trechos repetidos. Marque no original o início e fim que um editor escolheria. Compare quantos dos primeiros três candidatos são aproveitáveis, tempo por replay e quantos MP4s foram descartados após render. Para publicar, compare retenção por rede, duração e canal. Mantenha exemplos de avaliação de lives diferentes dos exemplos já usados na memória.

## Créditos

Integrações adaptadas do [OpenShorts](https://github.com/mutonby/openshorts/tree/e3e8a666e6ae912e47c5dfede6c07aa692eb5f89), com aviso MIT preservado em `vendor/openshorts/LICENSE`. A edição e a fila do V9 são o ponto de entrada do Codex.
