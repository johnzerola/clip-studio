# Instalação no Windows

## Antes de começar

Use Windows 10 ou 11 x64, Python 3.13 x64 com Tkinter, FFmpeg e FFprobe. O FFmpeg precisa de encoder H.264 e filtro de legendas `ass`. O FFplay é opcional para reproduzir a prévia com áudio. Uma conexão à internet é necessária para baixar o ambiente Python, os modelos de transcrição no primeiro uso e as mídias remotas.

- [Python para Windows](https://www.python.org/downloads/windows/)
- [FFmpeg](https://ffmpeg.org/download.html)
- [WinGet e App Installer](https://learn.microsoft.com/windows/package-manager/winget/)

## Instale e verifique

1. Baixe **Code → Download ZIP** ou o arquivo do aplicativo na página de **Releases**.
2. Use **Extrair tudo**. Abra a pasta interna que contém `Instalar.cmd`. Mantenha `scripts`, `docs` e `biblioteca` junto ao código.
3. Execute **Instalar.cmd**. Se faltar Python ou FFmpeg, rode `Instalar.cmd --automatico` no Prompt de Comando, naquela pasta. A opção automática usa WinGet para instalar os componentes ausentes.
4. Rode `Instalar.cmd --verificar`. A saída deve identificar o Python, as bibliotecas de vídeo, H.264 e o suporte a ASS.
5. Abra o atalho **Clip Studio**, ou `Iniciar.cmd`. Se já houver um atalho apontando para outra instalação, o instalador cria um nome com a pasta da nova cópia.
6. Faça um corte com um MP4 local curto seguindo o [guia do painel](GUIA-DO-PAINEL.md). Verifique o vídeo e o áudio na pasta **Clipes prontos**. Esse teste pode baixar o modelo Whisper na primeira transcrição.

Com os pré-requisitos instalados, o instalador cria `.venv` e instala `requirements.txt` localmente. O Windows pode marcar scripts baixados. Confirme a origem e, se confiar no ZIP, use **Propriedades → Desbloquear** antes de extrair, caso a opção apareça. O instalador usa `RemoteSigned` para o processo.

## Ollama e MCP opcionais

Com o Ollama instalado e em execução, baixe `qwen3:4b` e confira o nome em **Configurações avançadas → Modelo Ollama**. Use um modelo menor que já tenha instalado se precisar poupar memória. Deixe o campo vazio para usar a avaliação local por regras.

```powershell
ollama pull qwen3:4b
```

Instalar pré-requisitos, instalar Ollama junto ou preparar uma cópia sem atalho:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\install.ps1 -InstallPrerequisites
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\install.ps1 -InstallOllama
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\install.ps1 -SkipShortcut
```

O MCP serve ao banco de efeitos e à referência V9. Instale `requirements-mcp.txt` na `.venv` apenas se for usar um cliente MCP. Veja a configuração em [Arquitetura e integrações](ARQUITETURA.md). [Ollama no Windows](https://docs.ollama.com/windows)

## Erros comuns

| Sintoma | O que conferir |
| --- | --- |
| `Instalar.cmd` não aparece | Extraia o ZIP e entre na pasta interna do projeto |
| Python, FFmpeg ou FFprobe ausente | Use `Instalar.cmd --automatico` ou instale pelo site oficial e reabra o terminal |
| O painel abre e fecha pelo atalho | Execute `Instalar.cmd --verificar` para ler a etapa que falhou |
| Preview por quadro funciona, reprodução com áudio indisponível | Confira a presença de `ffplay` na distribuição do FFmpeg |
| Primeiro vídeo demora para transcrever | Aguarde o modelo baixar e confira a conexão e o espaço livre |
| Live não abre ou gravação não aparece | Confira se a fonte está pública, o link tem o formato do [README](../README.md) e o extrator é compatível |
| Nenhum MP4 aparece | Confira o registro, o limite de nota e se a sessão gerou um plano ou uma edição |
| Pouco espaço | Troque a pasta de saída, use o perfil Leve e ative **Liberar espaço após exportar** para capturas gerenciadas |

## Atualizar e preservar dados

O painel consulta a release pública uma vez por dia, em segundo plano. Se houver uma versão mais nova, oferece abrir a página no GitHub para baixar. A verificação usa a API pública, sem chave; falha de rede não bloqueia o app. Releases também podem gerar notificações do GitHub para quem acompanha o repositório.

Para atualizar, feche a sessão antes de mexer na instalação. Baixe a nova versão em [Releases](https://github.com/johnzerola/clip-studio/releases/latest) e extraia em outra pasta. Execute o instalador e abra a nova cópia. Selecione a pasta de saída anterior para manter acesso aos resultados e ao histórico. As preferências ficam em `preferencias.local.json` dentro de cada instalação. Se você usa `biblioteca.local`, copie essa pasta para a nova instalação. Os modelos Whisper ficam em `models`.

Versões anteriores à `0.4.0` não incluem o verificador automático. Para a primeira atualização, baixe esta versão pela página de Releases; a partir dela o painel avisa sobre futuras versões.

Para desinstalar, feche o app, remova o atalho da instalação e apague a pasta instalada depois de copiar as mídias, os resultados e as preferências que quiser guardar. Resultados em outra unidade permanecem na pasta escolhida.

Para instalação com ajuda de ChatGPT ou outra IA, abra a pasta extraída no assistente e indique [AGENTS.md](../AGENTS.md).
