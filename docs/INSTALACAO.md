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

A partir da v0.5.1, o painel verifica releases a cada 20 minutos, enquanto estiver aberto ou ao iniciar. A consulta acontece em segundo plano. Quando encontra uma versão estável mais recente, exibe as notas e pergunta se deseja atualizar. Durante captura, render ou envio, o aviso aguarda os trabalhos terminarem.

Ao aceitar, o painel salva as preferências e fecha. Uma janela de atualização baixa o ZIP e o checksum da release oficial, valida o SHA-256, extrai numa pasta irmã e prepara o ambiente Python usando o instalador. O atalho da Área de Trabalho só é direcionado para a nova versão depois de o diagnóstico passar. O app novo abre automaticamente.

A versão anterior permanece intacta. Preferências, pasta de saída, histórico da fila e credencial YouTube protegida pelo Windows são preservados. Modelos, biblioteca particular e resultados permanecem na pasta antiga; não a apague. Selecione ou copie sua biblioteca local quando necessário. Dependendo do motor, a nova instalação pode precisar baixar o modelo novamente.

Se a instalação falhar, o atalho anterior permanece disponível e a janela informa o erro e o registro da instalação. A atualização requer internet e permissão de escrita na pasta que contém o app. O Windows pode solicitar intervenção conforme suas políticas locais.

Versões anteriores à v0.5.0 precisam desta primeira atualização manual: baixe o ZIP em [Releases](https://github.com/johnzerola/clip-studio/releases/latest), extraia numa pasta nova e execute Instalar.cmd. A v0.4.0 oferece abrir a página; ela não instala automaticamente.

Para desinstalar, feche o app e preserve os resultados, biblioteca e preferências que quiser guardar antes de remover a pasta e o atalho.
