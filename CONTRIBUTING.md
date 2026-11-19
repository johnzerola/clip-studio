# Contribuir com o Clip Studio

Você pode ajudar testando links de plataformas, propondo melhorias de edição, simplificando telas, documentando a instalação ou enviando código. Pessoas, equipes e empresas podem participar pelo mesmo fluxo público.

## Por onde começar

| Área | O que ajuda |
| --- | --- |
| Captura e replays | Relatos reproduzíveis sobre links públicos, atrasos, reconexão e espaço em disco |
| Edição | Melhorar enquadramento, legibilidade de legendas, cortes de fala e mixagem |
| Painel | Simplificar prévia, acessibilidade, navegação e revisão dos resultados |
| Desempenho | Medir tempo, RAM, uso de disco e concorrência com a mesma mídia e configuração |
| Documentação | Melhorar os guias, atualizar capturas e validar a instalação em outro PC |

1. [Abra uma issue](https://github.com/johnzerola/clip-studio/issues/new/choose) com o objetivo ou o erro. Para um erro, inclua versão do Windows, Python e FFmpeg, passos, resultado esperado, resultado obtido e o trecho relevante do log.
2. Faça um fork e uma branch curta. Prefira uma mudança por pull request. Uma issue é útil antes de propor uma nova dependência, serviço ou mudança grande no fluxo.
3. Instale com `Instalar.cmd` e use `Instalar.cmd --verificar`. Se mudar a edição, exporte um vídeo local curto e confira imagem, áudio, duração e o `cortes.json`. Para mudanças visuais, inclua uma captura em dados de demonstração.
4. Abra o pull request com um resumo, os passos para testar e os limites da validação. Atualize o guia do painel ou o mapa técnico quando o comportamento mudar.

Use amostras que você pode redistribuir, como mídia sintética ou material com licença documentada. Remova cookies, tokens, caminhos pessoais, perfis do navegador e dados identificáveis de logs e capturas.

## Trabalhar com Claude, ChatGPT ou outra IA

Indique [AGENTS.md](AGENTS.md), [a arquitetura](docs/ARQUITETURA.md) e a issue ao assistente. [CLAUDE.md](CLAUDE.md) aponta o Claude Code para as mesmas instruções.

Uma tarefa de exemplo:

> Leia a issue e as instruções do projeto. Faça uma alteração pequena na prévia. Rode o diagnóstico, teste com um vídeo sintético e registre o antes e o depois. Preserve configurações locais e mantenha a postagem sob revisão humana.

Revise o diff, execute os testes relevantes e descreva o que foi validado. A pessoa que envia a contribuição responde pelo código, pelos resultados e pelas licenças do que foi incluído.

## Medições de desempenho

Compare a mesma fonte, estilo, duração e configuração de áudio. Informe hardware, perfil, versões e número de execuções. Meça duração total, tamanho da entrega e, quando disponível, pico de RAM. O [guia do modo Leve](docs/REVISAO-LEVE.md) registra as medições atuais e as lacunas.
