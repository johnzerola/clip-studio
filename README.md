# Clip Studio

Painel local para escolher os melhores candidatos de uma live da Twitch, VOD público ou vídeo do disco e gerar clipes verticais MP4. A seleção automática classifica atividade de áudio e movimento. A decisão de que uma jogada ou conversa merece publicação ainda depende da revisão do material.

## Windows

1. Tenha Python 3.13 e FFmpeg com FFprobe no PATH. O FFmpeg precisa de libx264 ou libopenh264 e do filtro ASS para legendas.
2. Extraia o ZIP e abra **Instalar.cmd** uma vez.
3. Abra **Iniciar.cmd**. Adicione os canais, URLs de VOD ou arquivos, um por linha.
4. Use **Somente analisar** para gerar o plano em JSON, ou **Analisar e renderizar** para gerar os MP4. Abra a pasta pelo botão **Abrir resultados**.

Até oito canais Twitch são capturados em paralelo. O padrão é 30 minutos por live, com blocos de cerca de 3 minutos. Cada bloco fechado entra na fila de análise enquanto a live segue. A fila limita o número de trabalhos de análise e render ativos. As legendas usam Faster Whisper local, modelo base CPU/int8 e download inicial automático. Para testar a edição sem esse download, desmarque **Legendas**.

VODs Twitch são baixados integralmente antes da análise. Os originais baixados e os blocos de live ficam na pasta de resultados para permitir revisão. A velocidade da captura ao vivo acompanha a transmissão. A análise de gravações usa miniaturas de 32 × 18 a cada dois segundos e uma faixa de áudio reduzida, embora ainda precise decodificar a fonte. O projeto não mede ganho de tempo em oito canais reais.

## Três estilos

| Estilo | Imagem 9:16 | Legendas |
|---|---|---|
| Dinâmico | Alterna rosto em tela, gameplay em tela ou os dois, conforme atividade de áudio e movimento | Meio no conjunto rosto/jogo e abaixo nas telas individuais |
| Rosto em cima + jogo embaixo | Mantém os dois em faixas verticais | Entre as duas áreas |
| Reação em tela + jogo no canto | Rosto em tela com gameplay inteira numa janela pequena à esquerda ou à direita | Abaixo |

O recorte de facecam usa quatro números normalizados para definir posição e tamanho no vídeo original, como `0.75,0.72,0.24,0.25`. O recorte de gameplay é opcional e usa o quadro original por padrão. Um canal com webcam embutida pode manter essa webcam dentro da gameplay se ela não for excluída pelo recorte. Se a facecam estiver em branco, a fonte sai como gameplay. Defina recortes diferentes por fonte com `canal | recorte_face | recorte_jogo`. A localização da facecam é manual nesta versão.

## Escolha dos cortes

- A duração alvo padrão é 90 segundos. A montagem busca três partes na mesma janela e as junta na ordem original. Desmarque a montagem para cortes contínuos.
- Para montar a sequência desejada com precisão, informe `1:25-1:40, 1:48-2:00, 2:36-2:49` em **Cortes manuais** com um único vídeo ou VOD.
- A pontuação considera energia relativa do áudio e mudança entre quadros amostrados. Ainda não há leitura de chat, reconhecimento de eliminações, análise semântica ou continuidade narrativa automática entre blocos de live. Picos de música, menus, cortes de cena e telas animadas também podem pontuar alto.
- Blocos e fontes curtos podem gerar menos clipes ou vídeos mais curtos. Os tempos da live em `cortes.json` são relativos ao arquivo de cada bloco.

## Integração com outro painel

O painel chama os mesmos motores que a CLI. Um projeto de edição pode executar a CLI em segundo plano e abrir o JSON resultante para revisão. A CLI aceita arquivo local e exige uma pasta nova por execução.

```powershell
.\.venv\Scripts\python.exe .\cli.py D:\Midia\live.mp4 --out D:\Midia\cortes-01 --style dynamic --face 0.75,0.72,0.24,0.25 --render --captions
```

`cortes.json` versão 1 registra fonte, duração, método e tempos em segundos. Cada clipe contém `parts` com início, fim e pontuação, e `layouts` com intervalos e enquadramento. Quando renderizado, `output` aponta para o MP4 na mesma pasta. O aplicativo integrador pode reutilizar os intervalos como cortes numa timeline ou mandar renderizar um plano revisado com `--ranges`.

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

O código do painel e dos motores é implementação própria. A pesquisa comparou comportamentos e padrões de edição.
