# Clip Studio · Lives, revisão e postagens

## Do canal à fila

1. Abra **Lives e gravações** e cole um canal por linha. Para Twitch e Kick, use o link do canal. Para YouTube, use `https://www.youtube.com/@canal/live`.
2. Para monitorar, deixe a captura sem duração fixa e marque **Aguardar novas lives**. **Buscar nova live a cada** controla a espera quando o canal está offline. Use **1 h** ou **2 h** para checagens espaçadas. O valor **0** verifica a cada 45 segundos. Uma queda recente durante uma transmissão usa reconexão mais curta.
3. Para editar o passado, cole o link de um VOD público ou escolha um arquivo local em **Adicionar arquivos…**. Para um link do YouTube no formato `/live/ID` que já terminou, marque a opção correspondente. A busca de replays por canal aceita 2 ou 3 gravações.
4. Com **Transcrever a gravação inteira** ativo, o Whisper salva `transcricao.txt` com os tempos das frases, e `transcricao.jsonl` com a posição de cada palavra. Abra as transcrições pela mesma aba. Os candidatos são escolhidos em blocos pelo áudio, movimento e frases. Se o Ollama estiver disponível, ele avalia o gancho, o contexto, a progressão e o desfecho de até quatro trechos por gravação.
5. Em **Postagens**, use **Ver** para abrir o MP4 e **Nota** para ver o motivo da nota de 0 a 100. **Agendar** abre os dados para a plataforma selecionada. Alterar a plataforma pode mudar a nota quando existe histórico suficiente naquele destino.

**Visão geral** mostra o estado dos canais do trabalho ativo na pasta selecionada. O indicador verde aparece quando a captura começa. O texto “editando” acompanha a atividade real do worker. Com o aplicativo fechado ou o computador suspenso, abra o painel e inicie novamente o monitoramento do painel. Trabalhos iniciados pela CLI ou pelo MCP usam o mesmo registro.

## Publicar com a conta do navegador

Em **Agendar**, escolha YouTube, TikTok, Instagram, Facebook ou X. Guarde o rascunho e abra o site oficial. O Clip Studio copia a descrição e oferece botões para copiar o título e o caminho do MP4. Selecione o vídeo, finalize o agendamento disponível para sua conta e registre a confirmação no painel. O rascunho local guarda o horário pretendido e reutiliza o mesmo MP4.

O agendamento automático existente do YouTube usa OAuth, com opção de envio e confirmação explícita. TikTok tem API de publicação e aprovação do cliente. Instagram e Facebook abrem o Meta Business Suite. O X abre o compositor. Os recursos de agendamento variam por conta e destino.

- [YouTube Studio · agendar a publicação](https://support.google.com/youtube/answer/1270709)
- [YouTube Data API · videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)
- [TikTok · Content Posting API](https://developers.tiktok.com/products/content-posting-api/)
- [Meta Business Suite](https://business.facebook.com/latest/)

## Aprender com clipes publicados

Em **Visão geral → Registrar métricas**, registre a retenção e as visualizações do Analytics de cada rede. A tela destaca os cinco clipes de maior retenção entre os que têm dados lançados. Os temas são sugeridos pelo título e pela descrição. Curiosidade, conversa, jogada, reação e história servem como sinais editoriais.

A amostra precisa de três clipes do tema e três de outros temas, com pelo menos 100 visualizações por clipe. A diferença de retenção altera a nota em até cinco pontos. Uma média das tendências registradas para YouTube e TikTok também ajusta os candidatos da próxima sessão. A nota estima potencial editorial. O histórico sugere padrões sem isolar causa, distribuição ou tamanho do público.

## Modelos e consumo

| Opção | Uso |
| --- | --- |
| Whisper Tiny | Transcrição em CPU e INT8 no modo Leve. A gravação é analisada em blocos de dois minutos, com contexto entre blocos. |
| Qwen 3 4B | Juiz de texto local já instalado. É o padrão do painel para escolher e explicar trechos. |
| Qwen 3 VL 2B | Visão opcional para amostras de clipes finalizados. Deixe o campo visual vazio quando estiver jogando. |
| Qwen 3.5 2B | Candidato a teste em PT-BR. O pacote de 2,7–3,1 GB pode ocupar mais disco que o Qwen 3 4B instalado. Compare latência, RAM e concordância editorial antes de trocar. |

O painel usa Tk nativo, quatro prévias por página e no máximo 16 miniaturas em memória. O modo **Leve · uso diário** roda uma renderização por vez e limita os threads dos motores. Monitorar um canal offline custa menos que transcrever, capturar ou renderizar. Comece com um canal ativo durante jogos. A opção **Liberar espaço após exportar** atua em arquivos temporários gerados pelo app. Os arquivos locais indicados pelo usuário continuam na pasta original.

- [Qwen 3 no Ollama](https://ollama.com/library/qwen3)
- [Qwen 3.5 no Ollama](https://ollama.com/library/qwen3.5)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Referências de produto

| Referência | O que entrou ou falta |
| --- | --- |
| [Apple HIG](https://developer.apple.com/design/human-interface-guidelines/sidebars) | Navegação lateral estável, hierarquia tipográfica e destaque na seção ativa. |
| [OpenShorts](https://github.com/mutonby/openshorts) | Galeria de clipes, ações junto da prévia e fluxo de revisão antes de publicar. A instalação local reaproveita o pipeline do Clip Studio. |
| [OpusClip](https://www.opus.pro/) | Nota com motivos e escolha por destino. Marcação manual de início e fim direto na galeria é um ponto em aberto. |
| [Eklipse](https://eklipse.gg/help/how-does-eklipse-automatically-create-clips/) | Combinação de áudio, chat e eventos do jogo. Reconhecer HUD e eventos de GTA por OCR amostrado é uma oportunidade. |
| [Streamlink](https://streamlink.github.io/plugins.html) e [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Bases existentes da captura e ingestão. O suporte varia conforme o acesso à origem e o estado dos extratores. |

O [levantamento de 55 projetos](PESQUISA.md) detalha ferramentas de captura, retenção, análise de fala e edição. As skills usadas foram `apple-design`, `frontend-design` e `videoai-studio-entry`. O MCP local **clip-studio** é a integração pertinente para iniciar, acompanhar e obter os arquivos de um trabalho do Codex. A [CLI e o MCP](CLI-MCP.md) usam o mesmo motor do painel.
