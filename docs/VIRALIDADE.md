# Pesquisa de 35 repositórios para detectar e revisar momentos

Revalidei o acesso aos 35 READMEs públicos e refiz o recorte da pesquisa anterior de [55 projetos](PESQUISA.md) com foco em selecionar bons momentos. Dividi a comparação entre detectores e componentes que os sustentam. A tabela descreve o mecanismo e a decisão para o Clip Studio. Consulte os READMEs para as licenças e parâmetros de cada implementação.

| Repositório | Como ajuda a encontrar ou revisar cortes | Decisão no Clip Studio |
| --- | --- | --- |
| [supoclip](https://github.com/FujiwaraChoki/supoclip) | Propõe cortes de VOD com base na fala | Usar transcrição e avaliação de contexto |
| [clips-studio](https://github.com/ColinGPT9/clips-studio) | Combina processamento local e análise com Ollama | Inferência opcional apenas na seleção e revisão |
| [clipmint](https://github.com/kleZ799/clipmint) | Pontua clipes e exibe sinais editoriais | Dar acesso ao motivo da nota |
| [PeakCut](https://github.com/haziqahmedqasmi/PeakCut) | Separa execução de live e VOD | Reaproveitar o mesmo fluxo de análise em ambas |
| [streamclipper](https://github.com/alokbaraii/streamclipper) | Recorta e reexporta trechos de stream | Manter revisão visual do clipe escolhido |
| [stream-clipper](https://github.com/sidgaikwad/stream-clipper) | Usa picos de chat da Twitch durante a gravação | Ranquear alternativas com chat antes de selecionar |
| [Dawassi AI Clipper](https://github.com/darryl-17/dawassi-ai-clipper) | Buffer contínuo e editor desacoplado | Manter gravação independente da análise |
| [twitch-clipbot](https://github.com/Higuy3000/twitch-clipbot) | Janelas de contexto em torno de um evento | Preservar preparação e consequência |
| [SharkyClips](https://github.com/utkualsir/sharkyclips) | Transcrição local e criação de cortes de VOD | Delimitar trechos por pausas e finais de frase |
| [live-clipper](https://github.com/akm72-bit/live-clipper) | Captura seguida de cortes em formato vertical | Manter a origem do fluxo atual |
| [Clipper](https://github.com/guleriaakshit/clipper) | Usa rajadas de chat, pessoas distintas e picos de voz | Dar bônus limitado por diversidade e atraso |
| [clipit](https://github.com/ataraxiiaa/clipit) | Usa sinais da transmissão e buffer para selecionar | Medir sinais antes de qualquer inferência maior |
| [Streamlink](https://github.com/streamlink/streamlink) | Entrega a mídia das transmissões a outros motores | Continuar com transporte separado |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Obtém vídeo, metadados e legendas disponíveis | Manter ingestão de VOD e captura de amostras |
| [ytarchive](https://github.com/Kethsar/ytarchive) | Grava partes disponíveis da janela de YouTube Live | Usar DVR para contexto quando disponível |
| [TwitchDownloader](https://github.com/lay295/TwitchDownloader) | Exporta clipes, VODs e chat de repetição | Referência para análise futura de chat arquivado |
| [Multi-Stream-Recorder](https://github.com/ManletPride/Multi-Stream-Recorder) | Monitora streams e mantém buffers por canal | Limitar captura e análise separadamente |
| [stream-archive](https://github.com/giou/stream-archive) | Organiza fontes gravadas por sessão | Conservar os motivos no histórico, por origem |
| [biliup](https://github.com/biliup/biliup) | Automatiza gravação e armazenamento de streams | Referência para continuidade e retomada |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Transcrição com tempos e VAD em CPU INT8 | Motor usado para localizar fala e suas bordas |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | Inferência nativa quantizada | Comparar com Tiny antes de trocar motor |
| [Whisper](https://github.com/openai/whisper) | Segmentação e reconhecimento de fala | Base de qualidade para transcrição |
| [WhisperX](https://github.com/m-bain/whisperX) | Alinhamento e diarização | Avaliar em conversas com várias vozes |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Encontra atividade de voz | Reusar o suporte do Faster Whisper |
| [py-webrtcvad](https://github.com/wiseman/py-webrtcvad) | Distingue voz e ausência de voz em blocos curtos | Alternativa se o custo da detecção subir |
| [Vosk](https://github.com/alphacep/vosk-api) | Reconhecimento incremental em CPU | Comparar tempo e erros em PT-BR numa etapa separada |
| [FFmpeg](https://github.com/FFmpeg/FFmpeg) | Detecta silêncio e congelamento e expõe amostras | Usar áudio e movimento no corte conservador |
| [Auto-Editor](https://github.com/WyattBlue/auto-editor) | Usa critérios de áudio e movimento para editar intervalos | Remover esperas preservando margens |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | Identifica mudanças de cena por diferenças de quadro | Referência para separar mudança visual de reação editorial |
| [MoviePy](https://github.com/Zulko/moviepy) | Manipula intervalos e composições | Usar como referência de protótipo, sem dependência nova |
| [PyAV](https://github.com/PyAV-Org/PyAV) | Acesso a frames e timestamps sem processo extra | Comparar se extração repetida virar gargalo |
| [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | Conserva intervalos e estrutura de edição | Permitir revisar as marcas selecionadas |
| [Ollama](https://github.com/ollama/ollama) | Serve modelos locais com saída estruturada | Usar Qwen para revisar a seleção e explicar a nota |
| [Moment-DETR](https://github.com/jayleicn/moment_detr) | Localiza intervalos relevantes e saliência em QVHighlights | Referência de avaliação de ranking, sem usar o dataset como prova de viralização |
| [Sentence Transformers](https://github.com/huggingface/sentence-transformers) | Recupera conteúdo por semelhança de embeddings | Reservar embeddings para bases maiores; cartões atuais cabem em busca lexical |

## Como o motor decide

1. **Durante a captura**, mede voz, movimento, repetições e picos. Com chat disponível, compara volume recente e diversidade de pessoas. O bônus vem antes da escolha do candidato, limitado a 8 pontos. A janela leva em conta o atraso aproximado do chat.
2. **Na edição**, corta esperas de pelo menos quatro segundos quando áudio, fala e movimento permanecem baixos. A regra preserva margens. A limpeza de hesitações e repetições continua separada. O modo conservador prioriza fala com contexto e ação visível.
3. **Na revisão**, recupera até três critérios editoriais da base `knowledge/viralidade.json` e manda ao Ollama junto com sinais e transcrição. A consulta é lexical e opcionalmente usa um arquivo `criterios.local.json` com a mesma estrutura. Se for configurado um modelo de visão, a revisão pode amostrar três quadros reduzidos. Os critérios recuperados ficam no registro.
4. **Na fila**, o resultado é expresso como potencial de 0 a 100. Retenção coletada após publicação pode ajustar a ordem por destino. O aplicativo tem critérios recuperáveis e inferência local; os pesos dos LLMs continuam os dos modelos instalados.

Use `ollama list` para conferir os nomes. `qwen3:4b` é uma opção de texto. Em **Configurações avançadas**, o campo **Modelo visual Ollama** aceita o nome de um modelo com visão, por exemplo Qwen3-VL. Deixe o campo visual em branco no modo Leve quando estiver usando o PC para jogar ou gravar. CLI e MCP aceitam `vision_model`, e `watch.py --keep-idle` desliga o filtro combinado de ociosidade. [API do Ollama](https://docs.ollama.com/api/chat)
