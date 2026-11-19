# Pesquisa de 55 repositórios para o Clip Studio

**19 de novembro de 2026.** Consultei o README e os metadados públicos de cada repositório via GitHub. As colunas separam capacidade documentada e decisão para este app. A pesquisa compara projetos. Os testes de execução se referem ao Clip Studio.

Interpretei “OpenSClip” como **OpusClip**, o produto comercial com recorte semântico, reenquadramento, legendas e pontuação de potencial. O painel local cobre a criação e revisão. Os principais pontos em aberto são tracking de múltiplos sujeitos, feedback de retenção comparável e uma interface para aparar o corte depois do render. [Referência oficial do OpusClip](https://www.opus.pro/pricing)

## O que entrou no produto

- **Modo Leve.** Uma renderização, Whisper INT8 com um thread, até dois downloads de fragmentos DVR por canal, preferência por captura em 480p/360p e prioridade abaixo da normal nos processos filhos de mídia do Windows. Pula transcrição de blocos silenciosos e estáticos. Continua usando o resultado dos sinais de imagem e áudio.
- **UX de operação.** Entrada de fontes e pasta de saída à vista, controles agrupados em abas, registro da sessão e fila de postagem. Distribuição em código-fonte com instalação isolada, diagnóstico e documentação.

## Próximas prioridades

| Prioridade | Capacidade | Como caberia neste PC |
|---|---|---|
| 1 | Controle de custo por canal, com prévia do atraso e tempo de fila | Persistir medidas da sessão. Acionar triagem mais espaçada quando a fila encher. |
| 2 | Editor de borda e reenquadramento manual com prévia | Usar proxies só para a prévia. Render final lê a mídia original. |
| 3 | Duplicatas semânticas e feedback editorial | Começar com texto, intervalos e hashes. Adicionar embeddings apenas a candidatos parecidos. |
| 4 | Tracking de múltiplos rostos e diarização | Testar apenas nos clipes escolhidos e medir ganho de qualidade em PT-BR. |
| 5 | Revisão por sinais de retenção e histórico por destino | Alimentar o banco já existente com métricas observadas após publicar. |

Para uso diário em um PC de quatro núcleos, a meta inicial é monitorar um canal ativo em **Leve**, manter espaço no G: e observar o atraso da fila antes de adicionar outro. Os tetos do programa limitam simultaneidade. Hardware, tráfego e atividade do canal influenciam o tempo.

## Seleção de cortes

| Repositório | Capacidade | Aplicação no Clip Studio | Licença detectada |
|---|---|---|---|
| [FujiwaraChoki/supoclip](https://github.com/FujiwaraChoki/supoclip/blob/main/README.md) | Seleção semântica, recorte vertical e legendas | Referência para revisão e UX de VOD | não classificada |
| [ColinGPT9/clips-studio](https://github.com/ColinGPT9/clips-studio/blob/main/README.md) | Pipeline de clips com Ollama, áudio e facecam | Comparar sinais e operação local | AGPL-3.0 |
| [kleZ799/clipmint](https://github.com/kleZ799/clipmint/blob/main/README.md) | Ranking, pós-edição e sinais medidos | Usar explicação de nota e aferição por resultado | MIT |
| [haziqahmedqasmi/PeakCut](https://github.com/haziqahmedqasmi/PeakCut/blob/main/README.md) | Seleção de live e VOD, com chave própria | Separar gravação contínua da análise | MIT |
| [alokbaraii/streamclipper](https://github.com/alokbaraii/streamclipper/blob/main/README.md) | Cortes de stream com exportação e ajustes | Referência de controle de enquadramento | AGPL-3.0 |
| [sidgaikwad/stream-clipper](https://github.com/sidgaikwad/stream-clipper/blob/canary/README.md) | Segmentação com sinais do chat em streams | Usar chat como um sinal adicional | sem SPDX |
| [darryl-17/dawassi-ai-clipper](https://github.com/darryl-17/dawassi-ai-clipper/blob/main/README.md) | Buffer da live e editor local | DVR e edição sem esperar VOD | MIT |
| [Higuy3000/twitch-clipbot](https://github.com/Higuy3000/twitch-clipbot/blob/main/README.md) | Janelas de pré e pós-rolagem na Twitch | Manter contexto em torno do evento | sem SPDX |
| [utkualsir/sharkyclips](https://github.com/utkualsir/sharkyclips/blob/main/README.md) | Transcrição local e seleção de momentos em VOD | Comparar sinais de reação e marcadores | MIT |
| [akm72-bit/live-clipper](https://github.com/akm72-bit/live-clipper/blob/main/README.md) | Captura de live e produção de clipes | Projeto de origem para comparar o fluxo | MIT |

## Captura e ingestão

| Repositório | Capacidade | Aplicação no Clip Studio | Licença detectada |
|---|---|---|---|
| [streamlink/streamlink](https://github.com/streamlink/streamlink/blob/master/README.md) | Plugins e transporte de transmissões | Manter como motor primário de live | BSD-2-Clause |
| [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/README.md) | Extração, listagem e download | Manter para replays e fallback da Kick | Unlicense |
| [Kethsar/ytarchive](https://github.com/Kethsar/ytarchive/blob/dev/README.md) | Arquivo de YouTube Live desde o trecho disponível | Alternativa em falhas de DVR | MIT |
| [lay295/TwitchDownloader](https://github.com/lay295/TwitchDownloader/blob/master/README.md) | VODs, clipes e processamento do chat | Importação de chat de replay numa etapa futura | MIT |
| [ManletPride/Multi-Stream-Recorder](https://github.com/ManletPride/Multi-Stream-Recorder/blob/main/README.md) | Monitor multicanal e buffer DVR | Separar supervisão, captura e edição | MIT |
| [giou/stream-archive](https://github.com/giou/stream-archive/blob/main/README.md) | Gravação e gestão de streams | Referência para gestão de sessões longas | MIT |
| [biliup/biliup](https://github.com/biliup/biliup/blob/master/README.md) | Gravação automática organizada por stream | Referência para reconexão e arquivos por sessão | MIT |
| [streamlink/streamlink-twitch-gui](https://github.com/streamlink/streamlink-twitch-gui/blob/master/README.md) | Interface de streams sobre Streamlink | Separar configurações do motor da ação principal | MIT |
| [mifi/lossless-cut](https://github.com/mifi/lossless-cut/blob/master/README.md) | Remux e corte com poucas recodificações | Preservar o transporte e recodificar no render | GPL-2.0 |
| [obsproject/obs-studio](https://github.com/obsproject/obs-studio/blob/master/README.rst) | Gravação, buffer e cenas | Referência para prévia e fonte local | GPL-2.0 |

## Fala e legendas

| Repositório | Capacidade | Aplicação no Clip Studio | Licença detectada |
|---|---|---|---|
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper/blob/master/README.md) | Whisper acelerado e INT8 | Manter Tiny para triagem e Base no acabamento | MIT |
| [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp/blob/master/README.md) | Implementação nativa e quantização | Alternativa se benchmark mostrar ganho | MIT |
| [openai/whisper](https://github.com/openai/whisper/blob/main/README.md) | Modelo de transcrição de referência | Baseline de precisão e segmentação | MIT |
| [m-bain/whisperX](https://github.com/m-bain/whisperX/blob/main/README.md) | Alinhamento de palavras e diarização | Melhorar trechos com várias vozes sob demanda | BSD-2-Clause |
| [snakers4/silero-vad](https://github.com/snakers4/silero-vad/blob/master/README.md) | Detecção leve de atividade de voz | Reaproveitar a filtragem já disponível no Faster Whisper | MIT |
| [wiseman/py-webrtcvad](https://github.com/wiseman/py-webrtcvad/blob/master/README.rst) | VAD simples por blocos curtos | Comparar antes de adicionar outro modelo | não classificada |
| [alphacep/vosk-api](https://github.com/alphacep/vosk-api/blob/master/README.md) | Reconhecimento offline incremental | Possível modo de baixa latência com benchmark PT-BR | Apache-2.0 |
| [rhasspy/piper](https://github.com/rhasspy/piper/blob/master/README.md) | Síntese local leve | Opcional para narrar mídia própria | MIT · arquivado |
| [SubtitleEdit/subtitleedit](https://github.com/SubtitleEdit/subtitleedit/blob/main/README.md) | Editor e validação de legendas | Referência para correção manual | MIT |
| [tkarabela/pysubs2](https://github.com/tkarabela/pysubs2/blob/master/README.md) | Manipulação de arquivos ASS e outros formatos | Útil para exportar legendas editáveis | MIT |

## Edição e render

| Repositório | Capacidade | Aplicação no Clip Studio | Licença detectada |
|---|---|---|---|
| [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg/blob/master/README.md) | Composição, filtros, encode e decodificação | Manter a etapa principal de render e verificação | não classificada |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor/blob/master/README.md) | Cortes orientados a segmentos e timeline | Inspiração para edição não destrutiva de pausas | Unlicense |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect/blob/main/README.md) | Detecção de mudança de cena | Verificar corte e transições apenas em pré-selecionados | BSD-3-Clause |
| [Zulko/moviepy](https://github.com/Zulko/moviepy/blob/master/README.md) | Composição de vídeo em Python | Protótipos e materiais curtos | MIT |
| [PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV/blob/master/README.md) | Acesso Python aos frames e streams de FFmpeg | Reavaliar quando subprocessos forem o gargalo | BSD-3-Clause |
| [AcademySoftwareFoundation/OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/README.md) | Intercâmbio de timelines | Manter exportação editável como opção | Apache-2.0 |
| [mltframework/mlt](https://github.com/mltframework/mlt/blob/master/README.md) | Motor de composição e playback | Referência para prévia de timelines | LGPL-2.1 |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion/blob/main/README.md) | Composição programável e motion graphics | Efeitos elaborados opcionais por custo de render | não classificada |
| [opencv/opencv](https://github.com/opencv/opencv/blob/5.x/README.md) | Visão e análise de movimento | Manter amostragem leve e detecção de facecam | Apache-2.0 |
| [google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe/blob/master/README.md) | Modelos de face e outras tarefas de percepção | Testar tracking em casos que Haar perde | Apache-2.0 |
| [HandBrake/HandBrake](https://github.com/HandBrake/HandBrake/blob/master/README.markdown) | Codificação e perfis de exportação | Referência de presets nativos | não classificada |
| [AOMediaCodec/SVT-AV1](https://github.com/AOMediaCodec/SVT-AV1/blob/main/README.md) | Encoder AV1 escalável | Opção de arquivo, com benchmark de compatibilidade | BSD-3-Clause-Clear |

## Ranking e runtime

| Repositório | Capacidade | Aplicação no Clip Studio | Licença detectada |
|---|---|---|---|
| [ollama/ollama](https://github.com/ollama/ollama/blob/main/README.md) | Execução local e saída estruturada | Manter inferência em shortlist | MIT |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/README.md) | Inferência local quantizada | Alternativa se o servidor Ollama for inadequado | MIT |
| [jayleicn/moment_detr](https://github.com/jayleicn/moment_detr/blob/main/README.md) | Localização de momentos e QVHighlights | Referência de avaliação, não de previsão comercial de viral | MIT |
| [huggingface/sentence-transformers](https://github.com/huggingface/sentence-transformers/blob/main/README.md) | Embeddings e comparação semântica | Detecção de cortes parecidos em uma etapa futura | Apache-2.0 |
| [numpy/numpy](https://github.com/numpy/numpy/blob/main/README.md) | Operações vetorizadas sobre amostras | Usar quando medir áudio e movimento | não classificada |

## Infra e distribuição

| Repositório | Capacidade | Aplicação no Clip Studio | Licença detectada |
|---|---|---|---|
| [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app/blob/main/README.md) | Fila e agendamento com contas conectadas | Referência para histórico por destino | AGPL-3.0 |
| [microsoft/playwright-python](https://github.com/microsoft/playwright-python/blob/main/README.md) | Automação e testes de navegador | Validar interfaces próprias; manter login no Studio | Apache-2.0 |
| [celery/celery](https://github.com/celery/celery/blob/main/README.rst) | Jobs e workers distribuídos | Útil só se houver vários PCs, evita dependência agora | não classificada |
| [agronholm/apscheduler](https://github.com/agronholm/apscheduler/blob/master/README.rst) | Agendamentos com recorrência | Referência para persistir horários em futura expansão | MIT |
| [pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller/blob/develop/README.rst) | Empacotamento de aplicações Python | Avaliar tamanho e definição de dependências antes de usar | não classificada |
| [microsoft/winget-cli](https://github.com/microsoft/winget-cli/blob/master/README.md) | Instalação rastreável de pré-requisitos | Instalador Windows opcional para binários | MIT |
| [python/cpython](https://github.com/python/cpython/blob/main/README.rst) | Biblioteca padrão, Tkinter e SQLite | Base do painel e persistência local | não classificada |
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md) | SDK para MCP local por stdio | Manter ferramenta de referência e efeitos opcional | MIT |

## Critério de integração

Nenhum código desses repositórios foi incorporado nesta etapa. IDs SPDX vêm da detecção do GitHub. Licenças múltiplas ou não classificadas requerem a leitura dos termos do próprio repositório. A comparação por famílias permite reutilizar motores existentes em vez de instalar várias pilhas para a mesma tarefa.


## Medição local do modo Leve

Em um trecho de 12 segundos no Intel i5-4590, Tiny mais amostragem audiovisual levou 6,02 s no Equilibrado e 5,89 s no Leve, com 53 palavras nos dois. Confirmei as classes de prioridade Windows normal e abaixo da normal, respectivamente. Foi uma amostra curta em uma máquina. Ela comprova a configuração e serve como evidência de funcionamento, sem estimar uso de CPU ou estabilidade em 24 horas. O ganho esperado para outros aplicativos vem dos limites de concorrência e da prioridade dos processos.
