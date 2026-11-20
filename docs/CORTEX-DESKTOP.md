# Cortex Clip Studio para Windows

O aplicativo x64 combina o painel React do Hook Spark, o motor de cortes V9 e os perfis aprovados do AI Video Director. No Windows 10 ou 11, baixe **Clip-Studio-Setup.exe** em [Releases](https://github.com/johnzerola/clip-studio/releases/latest). Ao abrir, escolha onde instalar. A preparação usa Python 3.13 x64, FFmpeg e o Microsoft Edge WebView2 Evergreen Runtime. O painel acompanha o pacote com uma cópia do Node. O primeiro preparo das dependências precisa de internet.

| Área | O que acontece |
| --- | --- |
| Início, Gerar ou Enviar e cortar | **Escolher vídeo e montar em 9:16** coloca o arquivo na fila Python. Selecione a pasta de destino. O motor V9 cuida dos cortes, fala, trilha e acabamento. |
| Ao vivo | Escolha até 480p, HD (720p) ou Full HD (1080p). **Capturar e editar** usa os provedores do Clip Studio em segundo plano. O motor escolhe uma variante disponível até o limite selecionado. Em Full HD, os cortes saem em 1080 × 1920. Use **Abrir no navegador** para acompanhar a transmissão. |
| Modelar | **Aplicar perfil aprovado a um vídeo** verifica os hashes das referências do Director. O ritmo aprovado orienta o enquadramento dinâmico do V9 quando há facecam. A montagem de cenas do Modelar pode usar o ritmo mediano dos perfis aprovados. |
| Editor e galeria | As ferramentas de edição manual, prévia e exportação visual continuam no painel Hook Spark. Os resultados V9 ficam na pasta escolhida e abrem por **Assistir** na lista de trabalhos recentes. |
| Controles avançados | Acesso ao painel clássico para configurações detalhadas, agenda, publicação e trabalhos CLI/MCP. |

Escolha português, inglês, espanhol ou detecção automática para transcrever a fala. O modo Leve usa uma tarefa local por vez. A triagem de lives combina transcrição, áudio, movimento e, quando disponível, reações de espectadores distintos no chat. A nota é uma estimativa editorial de potencial.

Durante a live, o gravador copia o sinal para blocos temporários no disco. A triagem descarta os blocos antigos e conserva uma janela curta para achar o início do corte. Ao encerrar, remove as sobras da captura. Depois da tentativa de edição, remove os candidatos temporários e conserva os MP4 finais e os registros de diagnóstico.

Para replays públicos, o Clip Studio transcreve a faixa de áudio separada e baixa somente os intervalos escolhidos. Escolha limite de 1440p (2K) ou 1080p (Full HD). O V9 usa a resolução disponível na fonte para recortar e ampliar a facecam e entrega o corte em até 1080 × 1920. Provedores sem áudio separado ou sem acesso ao intervalo registram uma mensagem na sessão.

A revisão final dá uma nota de 0 a 100. Quando o Ollama e o modelo visual configurado estão acessíveis, o V9 também avalia a fala e três quadros do MP4 pronto. A fila registra se a nota veio de visão, texto ou regras locais.

### Atualizações

Enquanto a janela está aberta, o aplicativo consulta o canal público a cada 20 minutos. Ao aceitar uma atualização, ele verifica o pacote e instala em uma pasta irmã. A v0.5.1 recebe a migração pelo mesmo canal. Quem instalou uma versão anterior ao verificador pode usar o instalador. O ZIP mantém os nomes que o atualizador antigo reconhece e traz o runtime do painel compactado dentro dele.

### Dados e serviços

O painel usa uma origem estável em loopback e um perfil WebView2 próprio por usuário Windows. Não copie tokens para o aplicativo. As funções Lovable que dependem de autenticação, gateway ou conectores continuam sujeitas à configuração desses serviços. A montagem V9 e os perfis do Director funcionam no computador. Projetos do navegador, histórico do motor local e trabalhos da fila têm armazenamentos próprios.

A distribuição Windows contém o painel compilado. O código desta integração está em `desktop/` e `desktop_actions.py`. O código-fonte do painel e a receita de empacotamento permanecem no repositório de origem do Hook Spark. Ao desenvolver somente com o checkout público, `Iniciar.cmd` abre o painel clássico. Para abrir a interface unificada, use o pacote da release.

