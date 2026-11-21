# Arquitetura e integrações

O Codex para Windows é híbrido. O launcher abre o painel React em uma janela do Edge, com Node local. Python coordena captura e edição e chama Streamlink, FFmpeg e FFprobe. Tkinter atende os seletores de arquivo e a marcação de trechos. A CLI e o MCP podem executar o motor diretamente. Os bancos SQLite e os arquivos de sessão ficam no disco escolhido pelo usuário.

## O que foi reaproveitado

| Origem | Como entra no Codex |
| --- | --- |
| Clip Studio v0.5.1 | Captura por blocos com Streamlink e FFmpeg, seleção local e edição V9. Painel, CLI e MCP apontam para a mesma fila. |
| Clip Studio v0.5.1 | Marcação de trechos por quadro em **Marcar início e fim** e acompanhamento em **Ver registro e plano**. O plano JSON e a timeline OTIO continuam no resultado quando gerados. |
| AI Video Director | Em **Modelar**, o perfil aprovado é conferido pelos hashes das referências. O plano registra o ritmo, o hash do preset e os hashes das fontes usados nessa edição. |
| AI Video Director | OpenFilm, FilmCraft, EffectCraft, análise quadro a quadro e Autopilot completo continuam no pacote do Director. O Codex usa o V9 para suas exportações. |

```mermaid
flowchart LR
    A["Arquivo ou fonte online"] --> B["Captura ou download"]
    B --> C["Triagem e análise"]
    C --> D["Plano de cortes e prévia"]
    D --> E["Render vertical e verificação"]
    E --> F["Clipes prontos"]
    E --> G["Fila de postagem"]
    G --> H["YouTube Studio ou TikTok Studio"]
    H --> I["Retenção registrada no painel"]
    I --> G
```

## Mapa do código

| Camada | Arquivos | Responsabilidade |
| --- | --- | --- |
| Instalação | `Instalar.cmd`, `Iniciar.cmd`, `scripts/install.ps1`, `scripts/launch.ps1`, `scripts/runtime.ps1`, `scripts/check.py` | Criar ambiente, localizar executáveis, verificar dependências e abrir o painel |
| Interface | `painel.py`, `tema.py`, `painel_visual.py`, `trim_preview.py`, `posting_panel.py` | Formulários, tema, prévia, biblioteca, estilos e navegação da fila |
| Entradas CLI | `cli.py`, `watch.py` | Arquivo local, lives e replays em terminal |
| Sessões | `sessions.py`, `runtime_profile.py`, `replay_library.py` | Agendamento interno, concorrência, prioridade e histórico de replays |
| Mídia | `engine.py`, `facecam.py`, `editorial.py` | Captura, inspeção audiovisual, transcrição, recorte e render |
| Triagem | `live_scout.py`, `viral_rank.py`, `final_screen.py`, `decision_bank.py` | Seleção, contagem de chat, avaliação editorial e revisão final |
| Acabamento | `finishing.py`, `audio_finish.py`, `v9_finish.py`, `broll_library.py`, `effects_bank.py`, `compression.py` | Legendas por palavra, transições, música, efeitos, inserts e compactação |
| Publicação assistida | `posting_queue.py`, `clip_quality.py` | Fila, similaridade, sugestões de texto e retenção |
| Intercâmbio | `review.py`, `makemyclip_adapter.py`, `effects_mcp.py` | OpenTimelineIO, adaptador e MCP de efeitos |

## Da fonte à entrega

1. **Entrada.** Streamlink resolve lives públicas de Twitch, Kick e YouTube. yt-dlp e FFmpeg atendem links compatíveis de TikTok e X. VOD remoto passa por download antes da edição. O DVR depende dos segmentos que a plataforma oferece.
2. **Seleção.** Áudio e movimento guiam a seleção inicial. Em live com triagem, o app analisa blocos de cerca de 15 s, usa Whisper Tiny e, na Twitch, conta mensagens recentes como sinal auxiliar. Ollama opcional avalia gancho, contexto, progressão e desfecho. Existem regras locais para fallback.
3. **Montagem.** O app aplica cortes manuais ou automáticos, cria a timeline por estilo e prepara legendas, voz, trilha e B-roll. A prévia manual busca quadros sob demanda e preserva as marcas de início e fim na edição.
4. **Exportação.** FFmpeg grava MP4 vertical. O perfil compacto Leve usa H.264 em uma etapa quando libx264 está disponível. Outros perfis podem transcodificar para H.264 ou H.265 e verificar o arquivo menor antes de substituir o temporário.
5. **Revisão.** Quando habilitada, verifica o MP4 e registra o motivo da aprovação ou rejeição. Similaridade usa hash exato, origem e intervalos, sequências da fala ou até três quadros reduzidos, conforme os dados disponíveis.
6. **Publicação.** O usuário confirma o envio no painel. O YouTube agenda por OAuth, e o TikTok segue no Studio. `publish_state.py` armazena o status local e `publish_panel.py` exibe os aprovados. [Guia de publicação](PUBLICACAO.md)

## Onde ficam os dados

| Local | Conteúdo |
| --- | --- |
| `preferencias.local.json`, `models/` | Preferências do painel e modelos Whisper da instalação |
| `biblioteca/`, `biblioteca.local/` | Exemplos do pacote e coleção particular |
| Pasta de saída › `AAAAmmdd_HHMMSS_ID/` | Sessão com `sessao.log`, `Capturas` e `Clipes prontos` |
| `Capturas/<fonte>/triagem.sqlite3` e `triagem.jsonl` | Sinais, notas, intervalos e motivos da triagem |
| `Clipes prontos/<fonte>/cortes.json` | Plano de edição e seus resultados |
| `clip_*.mp4` e `*.otio` | Vídeo entregue e, quando habilitada, timeline que referencia a mídia |
| `replays.sqlite3` | Histórico de gravações por plataforma e ID |
| `postagens.sqlite3` | Sugestões, similaridade, retenção e status |
| `tendencias.json`, `work/effect-previews/` | Termos informados pelo usuário e amostras de efeitos |

O JSON de edição versão 1 guarda `source`, `original_source`, `duration`, `method`, `unit` e `clips`. Cada clipe pode trazer `parts` em segundos, `removed`, `hook` e `variants`. `layouts` e `output` dão o plano principal e o arquivo principal. As variantes descrevem cada estilo, acabamento e revisão quando disponíveis. Em live, os tempos são relativos à mídia daquele bloco.

## Terminal no Windows

Rode na pasta instalada. Use uma pasta nova por execução de `cli.py`. Para consultar parâmetros, use `--help`.

```powershell
. .\scripts\runtime.ps1
Add-InstalledToolPaths
$py = ".\.venv\Scripts\python.exe"

# Planejar sem exportar
& $py -X utf8 .\cli.py "D:\Midia\live.mp4" --out "D:\Cortes\plano-01"

# Editar com legenda, webcam e limpeza
& $py -X utf8 .\cli.py "D:\Midia\live.mp4" --out "D:\Cortes\edicao-01" --style dynamic --auto-face --render --captions --cut-silence --cut-repeats --cut-fillers

# Monitorar um canal
& $py -X utf8 .\watch.py --performance leve --out "D:\Cortes" "https://www.twitch.tv/canal-exemplo"

# Repetir a busca de três gravações a cada duas horas
& $py -X utf8 .\watch.py --recent 3 --replay-hours 2 --replay-only --out "D:\Cortes" "https://kick.com/canal-exemplo"

# Exportar a timeline de um plano
& $py -X utf8 .\review.py "D:\Cortes\plano-01\cortes.json" --out "D:\Cortes\revisao.otio"
```

## Trabalhos compartilhados pelo painel, CLI e MCP

O registro local em `work/jobs.sqlite3` reúne as sessões iniciadas no painel, no `watch.py`, no `ClipJobs.cmd` e no MCP de trabalhos. A janela **Trabalhos CLI/MCP…** lê estado, eventos e caminho da sessão. Um trabalho controlado por vez evita que o painel e um cliente externo iniciem renderizações concorrentes. O processo de trabalho executa o mesmo motor do painel. [Guia da CLI e do MCP](CLI-MCP.md)

## Integrações opcionais

- **OpenTimelineIO.** A timeline aponta para a mídia de origem e referencia intervalos. Guarde a captura para editar depois. Confira a importação no editor de destino e use também o MP4 para ver efeitos compostos.
- **Banco de efeitos.** Use `effects_bank.py listar`, `effects_bank.py som impacto --pico -6` ou `effects_bank.py transicao dissolve` com o Python do projeto. Algumas transições funcionam como prévia pela ferramenta.
- **MCP.** Instale `requirements-mcp.txt` na mesma `.venv`. No cliente MCP, configure transporte stdio, a `.venv\Scripts\python.exe` como executável e o caminho de `effects_mcp.py` como argumento. FFmpeg precisa estar acessível ao cliente. As ferramentas incluem `list_effects`, `render_sound`, `render_transition`, `get_v9_reference` e `render_v9_accent`.
- **MakeMyClip.** `makemyclip_adapter.py clipe.mp4 --workspace pasta-nova` gera um plano de revisão para o MP4 composto. A execução externa exige uma instalação separada com `--node-entry`. Consulte `--help`. A compatibilidade depende da versão instalada.
- **V9.** A [skill de referência](../.agents/skills/alanzoka-v9-reference/SKILL.md) descreve enquadramento, transições e som. O vídeo original da referência fica com seu proprietário.

[Comparativo de repositórios](PESQUISA.md) · [Medições do perfil Leve](REVISAO-LEVE.md)
