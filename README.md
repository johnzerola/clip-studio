# Clip Studio

Painel local para selecionar candidatos de uma live da Twitch, Kick ou X, VOD público da Twitch ou Kick ou arquivo do disco, editar por atividade audiovisual e transcrição e gerar clipes verticais MP4.

## Windows

1. Tenha Python 3.13 e FFmpeg com FFprobe no PATH. O FFmpeg precisa de libx264 ou libopenh264 e do filtro ASS para legendas.
2. Extraia o ZIP e abra **Instalar.cmd** uma vez.
3. Abra **Iniciar.cmd**. Adicione canais da Twitch/Kick, links de transmissões públicas do X, URLs de VOD da Twitch/Kick ou arquivos, um por linha.
4. Deixe **Buscar facecam** e **Legendas** ativados. Escolha **GTA / Reação**, **Conversa** ou **Sem limpeza**.
5. Escolha a **Pasta de saída** e clique **Analisar e renderizar**. Os MP4 vão para **Clipes prontos** dentro da sessão. Com **Somente analisar**, essa mesma pasta guarda os planos em JSON. **Abrir resultados** abre a pasta selecionada.

Até oito transmissões Twitch/Kick/X são capturadas em paralelo. **Live = 0** acompanha até encerrar ou clicar **Parar captura**. **Aguardar início** tenta a conexão durante o período escolhido se a fonte ainda estiver offline. Após capturar mídia o painel tenta se reconectar brevemente se a conexão fechar. O PC e o painel precisam continuar ligados.

### Triagem ao vivo

- Com **Triagem ao vivo**, o gravador fecha blocos de aproximadamente 15 s. Faster Whisper Tiny em CPU transcreve os blocos enquanto a captura continua. As palavras aparecem em trechos no log. O primeiro candidato precisa de três blocos consecutivos; a janela mantém até quatro. É transcrição por blocos, com atraso do HLS e da fila, e não palavra a palavra instantânea.
- A nota combina atividade/movimento, densidade de fala, reações expressas e picos de chat quando disponíveis. O Ollama local pode revisar gancho, clareza, progressão e desfecho. O padrão é o modelo já instalado `qwen3:4b`. Deixe o campo vazio para usar só a heurística. Se o modelo não responder a tempo, a captura continua e a regra local decide. O texto vai somente para o Ollama no endereço local.
- O chat público anônimo disponível é **Twitch**. Só contam horários e quantidade de mensagens; o app não salva nem envia o conteúdo do chat. Kick e X seguem com análise audiovisual e transcrição. A correlação entre chat e captura é aproximada por causa do atraso da live.
- Com **Limpar blocos rejeitados**, cada canal mantém até quatro blocos fechados em contexto, cinco em espera, o bloco em gravação e o que estiver em análise. Se a fila encher, perde prioridade o bloco temporário mais antigo. Candidatos aprovados são copiados para um MP4 separado antes de liberar os fragmentos temporários. MP4 publicados e fontes externas nunca entram nessa limpeza. O armazenamento de candidatos aprovados fica sob controle do operador.
- Os aprovados entram na fila de edição e ganham MP4 9:16, legendas opcionais e OTIO. A edição final usa modelo Base; oito capturas em paralelo não equivalem a oito transcrições simultâneas. Sem a triagem, a edição continua em blocos de aproximadamente dois minutos.
- `Capturas/<fonte>/triagem.sqlite3` guarda decisões e notas. Use `decision_bank.py caminho/triagem.sqlite3` para listar, ou `--id candidato_... --retention 72 --views 1200` para registrar números medidos de um clipe aprovado. A nota é editorial e não prevê visualizações. Não há treinamento automático com o banco.

Na Twitch, cole o canal ou a URL. Na Kick, cole `https://kick.com/nome-do-canal` ou o link público do VOD. Twitch e Kick usam Streamlink. No X, use `https://x.com/i/broadcasts/ID` ou o link da publicação pública que contém a transmissão ativa. A captura do X usa o extrator do yt-dlp seguido de FFmpeg. Vídeos privados, transmissões inacessíveis, Spaces só de áudio e replays do X não entram nesse fluxo; para analisar um replay, use o arquivo local.

VODs da Twitch e da Kick são baixados integralmente antes da análise. Os originais baixados e os blocos de live ficam na pasta de resultados para permitir revisão. A velocidade da captura ao vivo acompanha a transmissão. A análise de gravações usa miniaturas de 64 × 36 a cada dois segundos e uma faixa de áudio reduzida, embora ainda precise decodificar a fonte. O projeto não mede ganho de tempo em oito canais reais.

## Três estilos

| Estilo | Imagem 9:16 | Legendas |
|---|---|---|
| Dinâmico | Alterna reação com rosto ampliado, gameplay em destaque, facecam redonda sobre o jogo e rosto em cima com jogo embaixo | Meio na tela dividida e abaixo nos outros enquadramentos |
| Rosto em cima + jogo embaixo | Mantém os dois em faixas verticais | Entre as duas áreas |
| Reação em tela + jogo no canto | Rosto em tela com gameplay inteira numa janela pequena à esquerda ou à direita | Abaixo |
| Jogo em tela + facecam redonda | Gameplay em destaque sobre fundo desfocado, com rosto redondo à esquerda ou à direita | Abaixo |

**Exportar os três estilos** renderiza a mesma timeline em Dinâmico, Dividido e Reação. O layout redondo entra como recurso do Dinâmico ou pode ser escolhido sozinho. Áudio e transcrição são analisados uma vez por montagem.

**Visual Shorts GTA** preenche a composição dividida, usa legendas curtas em caixa alta com palavra em destaque e permite um cartão nos primeiros segundos formado a partir da fala. **Clássico** mantém o quadro ajustado à faixa. O modo Shorts pode recortar laterais do jogo na tela dividida; o enquadramento só de gameplay preserva o quadro da região selecionada.

**Transições e som** limita os acentos a três por clipe, separados por pelo menos 12 segundos. O insert dissolve na própria camada, a câmera troca sem escurecer a tela inteira e o efeito sonoro é sintetizado localmente. O áudio permanece contínuo quando a edição muda só o enquadramento. A captura MPEG-TS é copiada para MP4 antes da busca de frames, mantendo a mídia editável como `midia-revisao.mp4`. **Centro do close** desloca o recorte horizontal de 0 (esquerda) a 1 (direita). Também pode ser definido por fonte com `canal | rosto | jogo | centro`.

**B-roll local** aceita um diretório de imagens e vídeos autorizados. Nomeie um arquivo com uma palavra da fala, por exemplo `musicas.png`. Quando essa palavra é reconhecida num trecho de gameplay ou tela dividida com tempo suficiente, aparece um insert curto e sem o áudio do arquivo. É usado no máximo um insert por versão e o motor procura somente na pasta escolhida. A transcrição é processada localmente.

### Áudio e continuidade

**Tratar e nivelar áudio** equilibra o nível entre trechos, aplica filtro de graves, redução moderada de ruído, equalização e compressão. O master tem alvo de −16 LUFS e −1,5 dBTP antes da compressão AAC. Se a live tiver voz, jogo e rádio em uma única faixa, esses filtros atuam na faixa misturada. Desmarque a opção quando quiser preservar o balanço original da captura.

**J-cut (ms)** antecipa parte da faixa de áudio da próxima cena quando existe uma mudança real no tempo da origem e som suficiente no trecho anterior à entrada. Trocas de câmera não quebram a faixa. Cortes pequenos de limpeza, silêncio antes da entrada e a posição zero da fonte podem fazer o motor pular o J-cut. **Trilha** aceita um arquivo local. O volume é reduzido enquanto o áudio principal está ativo. Os efeitos sonoros são sintetizados e os acentos de câmera têm zoom curto na abertura e nas reações selecionadas. O JSON de cada variante registra J-cuts, zooms, ganho e trilha realmente usados.

**Buscar facecam** usa OpenCV local para procurar um rosto frontal pequeno e estável nos cantos e nas laterais, por amostragem. Se o detector não encontrar uma facecam plausível, exporta gameplay. O recorte manual tem prioridade e usa `x,y,largura,altura` normalizados, como `0.75,0.72,0.24,0.25`. Defina recortes diferentes por fonte com `canal | recorte_face | recorte_jogo`. Quando possível, um recorte lateral evita duplicar a webcam embutida na captura. Isso descarta parte da borda; uma fonte única não tem os pixels do jogo encobertos pela câmera. O recorte de jogo manual tem prioridade.

A câmera dinâmica compara atividade da webcam, movimento da gameplay e energia do áudio, com pistas de reação da transcrição. A troca é por blocos curtos e funde blocos vizinhos iguais. O sistema não distingue com precisão quem está falando no áudio misturado, nem identifica a história do jogo ou um momento tenso pela semântica.

## Escolha dos cortes

- A duração alvo padrão antes da limpeza é 90 segundos. A montagem busca até três partes na mesma janela e as mantém na ordem original. Com **Juntar pela fala**, tenta ajustar os cortes a pausas e pontuação próximas e favorece vocabulário compartilhado entre os trechos. Desmarque a montagem para selecionar um trecho contínuo antes da limpeza.
- Para montar a sequência desejada com precisão, informe `1:25-1:40, 1:48-2:00, 2:36-2:49` em **Cortes manuais** com um único vídeo ou VOD.
- **Cortar silêncio** usa FFmpeg com pausa mínima e limiar em dBFS ajustáveis. **Tirar repetições** elimina a primeira de duas palavras ou frases exatamente iguais e próximas. **Tirar hesitações** remove interjeições isoladas reconhecidas pelo Whisper. **Encurtar pausas sem fala** usa marcas de transcrição e pode cortar mesmo quando há música de fundo. Por isso vem desativado em **GTA / Reação** e ativado em **Conversa**.
- Os candidatos iniciais ainda são classificados por áudio/movimento. Não há leitura de chat, reconhecimento de eliminações, decisão semântica sobre relevância ou histórias que cruzem blocos da live. Repetições intencionais e reconhecimento de fala imperfeito podem afetar a edição. O relatório lista tempos e motivos da limpeza.
- Blocos e fontes curtos podem gerar menos clipes ou vídeos mais curtos. Os tempos da live em `cortes.json` são relativos ao arquivo de cada bloco.

## Integração com outro painel

O painel chama os mesmos motores que a CLI. Um projeto de edição pode executar a CLI em segundo plano e abrir o JSON resultante para revisão. A CLI aceita arquivo local e exige uma pasta nova por execução.

```powershell
.\.venv\Scripts\python.exe .\cli.py D:\Midia\live.mp4 --out D:\Midia\cortes-01 --style all --auto-face --render --captions --cut-silence --cut-repeats --cut-fillers --link-speech
```

`cortes.json` versão 1 registra fonte, duração, método e tempos em segundos. Cada clipe contém `parts` com início, fim e pontuação, `removed` com os motivos da limpeza, e `variants` com enquadramentos e arquivos por estilo. Os campos `layouts` e `output` continuam representando a primeira versão. Um painel externo pode reutilizar os intervalos numa timeline ou usar `--ranges` para aplicar um plano revisado. Para o FilmCraft, a integração proposta é ler esses intervalos e aplicar os cortes numa sequência nova via CLI ou MCP; nenhum serviço externo é necessário para executar o Clip Studio.

O adaptador `makemyclip_adapter.py clipe.mp4 --workspace pasta-nova` escreve um plano para importar o MP4 vertical no MakeMyClip. Com `--node-entry caminho/da/cli.js`, executa os comandos em uma instalação local do MakeMyClip. Use `--node caminho/para/node.exe` para um Node 24 portátil e `--export --ffmpeg caminho/para/ffmpeg.exe` para exportar com libx264. Esse caminho revisa o render já composto; os cortes editáveis continuam no OTIO. Jumpcut serve como referência de agrupamento por palavra e Auto-Editor como comparação de silêncio; não entram como processos obrigatórios.

Cada vídeo renderizado recebe uma timeline local **OpenTimelineIO** com cortes de vídeo e áudio. Use `review.py cortes.json --out revisao.otio` para exportar um plano manualmente. O OTIO guarda referências à mídia e indicações de enquadramento. Para rever os efeitos completos, abra também o MP4 e o JSON. Suporte à importação precisa ser conferido no editor de destino.

## Referências de desenvolvimento

| Referência | Aplicação ao projeto |
|---|---|
| [Live Clipper](https://github.com/akm72-bit/live-clipper) | Ponto de partida para captura segmentada, clipe vertical e legenda local |
| [stream-clipper](https://github.com/st1fo/stream-clipper) | Pipeline live/VOD e recortes ajustáveis por fonte |
| [LocalClip](https://github.com/MarkyADHD/LocalClip) | VOD local e enquadramento vertical de facecam sobre gameplay |
| [ClipForge de Brettillian](https://github.com/Brettillian123/clipforge) | Pontuação editorial, ritmo do áudio e painel de revisão |
| [ClipForge de Avilash](https://github.com/Avilash2001/ClipForge) | Escolha de layout e fallback para gameplay |
| [TwitchDownloader](https://github.com/lay295/TwitchDownloader) | Possível importador de chat de VOD para uma próxima etapa |
| [Eklipse](https://eklipse.gg/help/how-to-use-and-customize-templates/) | Modelos de recorte de gameplay e facecam |
| [OpusClip Gameplay](https://www.opus.pro/tools/gaming-video-editor) | Composição empilhada e troca de layout por trecho |
| [Auto-Editor](https://github.com/WyattBlue/auto-editor) | Margens para conservar o começo e o fim da fala nos cortes de silêncio |
| [MakeMyClip](https://github.com/MakeMyClip/editor) | Referência de CLI e MCP que editam uma timeline pela transcrição, com revisão e desfazer |
| [Jumpcut](https://github.com/Kawwshall/jumpcut) | Uma transcrição com tempo por palavra alimenta limpeza e legenda |
| [Unsaid](https://github.com/Necromancervbh/unsaid) | Margem junto aos fonemas e remoção de hesitações |
| [Twitch Portrait Clips](https://help.twitch.tv/s/article/how-to-use-clips) | Referência visual para webcam e gameplay em regiões empilhadas |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) | Resolução de transmissões de vídeo públicas do X |
| [Clipit](https://github.com/ataraxiiaa/clipit) | Buffer circular, captura desacoplada e julgamento local |
| [LocalClip](https://github.com/MarkyADHD/LocalClip) | Triagem de fala, picos de chat e shortlist editorial |
| [stream-clipper](https://github.com/st1fo/stream-clipper) | Limites de aceitação, múltiplas plataformas e metadados de decisão |
| [whisper-rs](https://docs.rs/crate/whisper-rs/latest) | Alternativa Rust a comparar com Tiny/CTranslate2 em um benchmark equivalente; não instalada |
| [Tutorial de facecam circular para OBS](https://www.youtube.com/watch?v=kxiZoEkOI6Y) | Máscara redonda de webcam sobre gameplay |
| [Cortes do GMF](https://www.youtube.com/watch?v=xfRTVw-T5v8) e [StoryCut GTA RP](https://www.storycut.com/use-cases/gta-rp-clips) | Referências de GTA RP e estrutura curta de preparação e reação |
| [Exemplos visuais de legenda da OpusClip](https://www.opus.pro/pt-br/tools/auto-caption-generator) | Legenda de fala em blocos curtos com destaque da palavra atual |

O código do painel e dos motores é implementação própria. A pesquisa comparou comportamentos e padrões de edição.
