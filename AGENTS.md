# Instalação assistida do Clip Studio

1. Trabalhe na pasta extraída que contém `Instalar.cmd`. Leia [README.md](README.md) e [docs/INSTALACAO.md](docs/INSTALACAO.md).
2. Execute `Instalar.cmd --verificar`. Se faltar o ambiente local, use `powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\install.ps1`. Use `-InstallPrerequisites` quando precisar instalar Python/FFmpeg via WinGet. Adicione `-InstallOllama` se o usuário quiser modelo local.
3. Use a `.venv` da instalação. Preserve preferências, biblioteca particular e resultados. Escolha uma pasta de saída com espaço e comece no modo Leve.
4. Depois de instalar, verifique novamente, abra o painel com `Iniciar.cmd` e confirme o nome do atalho e as dependências. Se a interface gráfica estiver indisponível, registre essa limitação.
5. Se houver um vídeo local de teste, siga [Fazer o primeiro corte](README.md#fazer-o-primeiro-corte) e confira a exportação. O usuário opera login e publicação no Studio da plataforma.

[Mapa do sistema](docs/ARQUITETURA.md) · [Guia de publicação](docs/PUBLICAR-NO-GITHUB.md)
