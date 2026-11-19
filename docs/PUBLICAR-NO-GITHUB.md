# Publicar o Clip Studio no GitHub

O GitHub renderiza `README.md` e carrega as imagens de `docs/img`. Publique o conteúdo da pasta extraída para que a documentação apareça ao rolar a página do projeto.

## Pelo GitHub Desktop

1. Extraia o ZIP em uma pasta nova, fora da sua instalação de trabalho.
2. Abra o Prompt de Comando na pasta interna onde estão `README.md` e `Instalar.cmd`. Rode `git init -b main`.
3. Em GitHub Desktop, use **File → Add Local Repository** e selecione a pasta interna.
4. Confira a lista, faça o primeiro commit e clique em **Publish repository**. Escolha **privado** se for compartilhar só com convidados. Nesse caso, conceda acesso à conta do seu amigo.
5. Abra a página e confira que o README e as imagens aparecem. Ao receber o link, seu amigo usa **Code → Download ZIP** e segue a instalação.

## Pelo terminal

Crie um repositório vazio no GitHub. Substitua o endereço de exemplo pela URL do seu repositório.

```powershell
git init -b main
git add .
git status --short
git commit -m "Publica o Clip Studio com guias e instalador"
git remote add origin https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git
git push -u origin main
```

## Distribuir também em Releases

No GitHub, abra **Releases → Draft a new release**. Escolha a tag, escreva o resumo e anexe o ZIP. O mesmo arquivo pode ser enviado diretamente. O README da página vem dos arquivos extraídos que estão na raiz do repositório.

## Conferência antes de subir

- A raiz precisa ter `README.md`, `Instalar.cmd`, `Iniciar.cmd`, `AGENTS.md` e `LICENSE`.
- Mantenha `docs/img`, `scripts`, os arquivos Python, `requirements.txt` e `biblioteca`.
- Use a pasta extraída para o primeiro commit. Credenciais, cookies, bancos reais, `.venv`, modelos, capturas e mídias pessoais ficam na instalação de origem.
- Depois de publicar, faça um download de teste em outra pasta. Execute `Instalar.cmd` e `Instalar.cmd --verificar`.

[Publicar repositório local](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) · [Criar uma release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository) · [Convidar colaborador](https://docs.github.com/en/account-and-profile/how-tos/account-management/inviting-collaborators-to-a-personal-repository)
