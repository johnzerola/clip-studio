# Integração Clip Studio e OpenShorts

A cópia de referência está em `G:\clip-studio\work\openshorts-reference`, no commit
`b3cd947bc48ad1fc8093bb8f8291b9fb02e9bb2f`. O código MIT reaproveitado fica em
`vendor/openshorts/`, com a licença original. A hospedagem comercial em
`cloud/` permanece na cópia de referência e fica fora do pacote do Clip Studio.
O painel usa o desenho e os componentes nativos do Clip Studio.

| Área no OpenShorts | Integração instalada |
| --- | --- |
| `clip_selection.py`, `hook_grounding.py`, `transcribe_backends.py` | O filtro MIT de sobreposição participa da seleção de VOD. Whisper e Ollama mantêm a análise local com marcações de tempo. O texto de gancho pode vir da fala ou ser digitado no painel. |
| `editor.py`, `pro_mode.py`, `remotion/` | O Ollama recomenda entre edição suave, movimento ou reação. O FFmpeg aplica o acabamento escolhido. Efeitos generativos do editor Gemini/Remotion continuam no projeto de referência. |
| `reframe_v2.py`, `scene_detection.py`, `active_speaker.py` | **Reenquadrar rosto 9:16** procura um rosto estável em até três quadros por plano e faz um recorte mantendo proporção. Nos demais planos, continua o enquadramento do Clip Studio. |
| `thumbnail.py` e YouTube Studio | **Studio** na galeria sugere títulos, grava título e descrição, exporta uma miniatura JPG 1280 × 720 e exibe a prévia. Envio via OAuth tenta aplicar a miniatura onde a API aceitar. |
| `social_platforms.py`, `yt_account.py`, `social_metrics.py` | Mapeamento MIT de campos por rede, envio multipart com agendamento, identificação por perfil e proteção contra envio duplicado. O painel distingue recebimento pelo serviço e confirmação da rede. |
| `saasshorts.py` e rotas de UGC | A janela **Ator de IA** conecta ao OpenShorts local, submete roteiro, acompanha o trabalho, abre a prévia e salva MP4. |
| `dashboard/`, `cli/`, `mcp_stdio.py`, `examples/`, `tests/` | A galeria preserva o visual local e concentra Studio, Agendar, Ator de IA, Piloto e nota. CLI e MCP do Clip Studio aceitam campos de gancho, efeitos e reenquadramento. |

## Uso no painel

- **Edição** — preencha o gancho em até 64 caracteres. Ative **Efeitos por IA** e selecione um modelo Ollama nas configurações de análise para deixar o motor escolher o acabamento. **Reenquadrar rosto 9:16** é opcional e é especialmente útil em filmagens horizontais de uma pessoa. **@ do canal** aplica sua assinatura ao render.
- **Postagens → Studio** — o botão abre o editor para o clipe selecionado. Escolha o segundo, gere e revise a miniatura e salve o texto. O JPG fica na pasta de resultados, em `.studio-thumbnails/`.
- **Postagens → Agendar** — escolha o navegador, YouTube OAuth ou Upload-Post. O provedor exige chave e um perfil conectado às redes. Selecione e confirme o destino e horário. O envio imediato fica disponível com a data em branco no diálogo do provedor.
- **Postagens → Piloto automático** — autorize a rede, perfil, horário e nota mínima antes de iniciar a próxima sessão. A revisão final precisa estar ativa. O piloto agenda até um novo corte aprovado por horário diário e evita clipes marcados como semelhantes. A autorização vale durante a execução do painel. Encerrar o painel desativa novas submissões locais. O provedor mantém os agendamentos que já recebeu.
- **Postagens → Ator de IA** — inicie o Docker Desktop no modo de contêineres Linux. A partir da pasta do Clip Studio, execute `powershell -NoProfile -ExecutionPolicy RemoteSigned -File scripts/start-openshorts.ps1`. Use a porta 8000. A janela pede descrição de ator fictício, roteiro, chave fal.ai e chave ElevenLabs. A geração pode ser cobrada. O MP4 fica disponível para baixar após concluir.

## Verificação

O ambiente local já inclui Pillow e httpx. Validei a miniatura e o fluxo de edição com um MP4 real e Qwen 3 4B. Os caminhos de postagem e de UGC foram verificados com respostas simuladas. A configuração do Docker passou na validação, e o motor Linux do Docker Desktop estava parado durante o teste. A geração de um ator e o agendamento em conta real ainda dependem das credenciais do usuário e de um teste autorizado.

- [OpenShorts e requisitos de uso](https://github.com/mutonby/openshorts)
- [Upload-Post, envio e agendamento de vídeos](https://docs.upload-post.com/api/upload-video/)
- [YouTube, miniaturas via API](https://developers.google.com/youtube/v3/docs/thumbnails/set)
- [YouTube, disponibilidade de miniaturas personalizadas](https://support.google.com/youtube/answer/72431)
