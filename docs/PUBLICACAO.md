# Clipes prontos e agendamento

## Operação pelo painel

1. Use **Lives e gravações → Procurar melhores momentos** e **Revisar vídeo pronto**. Deixe **Remover esperas sem fala nem ação** ligado para a edição da live aplicar o corte conservador.
2. Em **Prontos para postar**, escolha um vídeo, confira a nota, clique em **Entender a nota** e assista. A lista é atualizada a partir da pasta de saída atual. **Revisão completa…** abre o histórico com descartes e retenção.
3. Em **Publicar ou agendar…**, confirme destino, título e descrição. No YouTube, conecte o canal, preencha o horário local e indique o público. **Enviar e agendar** envia agora. Se o YouTube aceitar o horário, a plataforma publica na data mesmo que você feche o painel após a confirmação.
4. No TikTok, **Abrir Studio** copia a descrição e abre o fluxo do navegador. Faça o upload e conclua o agendamento no próprio Studio, quando a conta oferecer essa opção.

## Conectar um canal do YouTube

No Google Cloud, habilite YouTube Data API v3, configure a tela de consentimento e crie um cliente OAuth **Aplicativo para computador**. Baixe o JSON desse cliente e selecione em **Conectar YouTube…**. Conclua a autorização no navegador e confira o nome e o ID do canal que o painel mostrar. O token de atualização fica protegido pelo Windows, em `work/youtube-account.dpapi`.

O painel usa o horário local do Windows e o converte para UTC. Pedidos com data próxima demais são rejeitados. Se o envio perder a resposta ou o YouTube devolver um ID sem confirmar `publishAt`, confira o Studio. A fila impede reenviar o mesmo clipe automaticamente quando o resultado estiver incerto. Projetos de API sujeitos a auditoria podem ter uploads limitados ao privado. [OAuth desktop](https://developers.google.com/identity/protocols/oauth2/native-app) · [Inserção de vídeos](https://developers.google.com/youtube/v3/docs/videos/insert) · [Regras de auditoria do YouTube](https://developers.google.com/youtube/data/revision_history)

O Direct Post do TikTok exige revisão do aplicativo e impõe restrições a utilitários internos. O fluxo incluído usa o Studio com revisão humana. [Diretrizes do TikTok](https://developers.tiktok.com/docs/en/content-sharing-guidelines)

## Sinal de chat

- **Twitch** usa a leitura do chat existente quando o serviço a permite. Volume de mensagens e diversidade de remetentes ficam em memória. O texto e os nomes não são armazenados.
- **YouTube** pode consultar o chat oficial quando a fonte usa `youtube.com/live/ID` e há uma conta conectada ou a variável de ambiente local `CLIP_STUDIO_YOUTUBE_CHAT_KEY`. A aplicação respeita o intervalo de consulta informado pelo YouTube. [API de mensagens de chat](https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list)
- **Kick** usa fala, áudio e movimento nesta versão. Os outros sinais continuam ativos quando o chat de uma plataforma não está disponível.

[Pesquisa e critérios da nota](VIRALIDADE.md)
