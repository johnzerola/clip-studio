# Codex de edição de vídeo para Windows

O aplicativo x64 reúne o painel React do Hook Spark, o motor de cortes V9 e os perfis aprovados do AI Video Director. No Windows 10 ou 11, baixe **Clip-Studio-Setup.exe** em [Releases](https://github.com/johnzerola/clip-studio/releases/latest) e escolha onde instalar. A edição usa Python 3.13 x64 e FFmpeg. A interface abre em uma janela de aplicativo do Microsoft Edge com perfil próprio. O pacote já contém o Node e o painel compilado.

A partir da v0.7.1, os atalhos **Codex** e **Clip Studio**, `Iniciar.cmd`, `Codex.exe` e `Clip Studio.exe` abrem o mesmo painel Hook Spark. Se a janela estiver aberta, o atalho traz essa janela de volta. O painel, a CLI e o MCP usam a mesma fila V9.

| Área | O que acontece |
| --- | --- |
| Início | Escolha vídeos ou cole um link em **Analisar com IA**. Acompanhe a fila e use os cartões de clipes aprovados para assistir, baixar ou revisar antes de postar. |
| Gerar ou Enviar e cortar | Adicione arquivos ou links de gravações, escolha a saída e use **Montar, avaliar e exportar** ou **Gerar plano de cortes**. |
| Ao vivo | Acompanhe canais a cada uma, duas ou três horas, capture até 1080p e procure as últimas duas ou três gravações. Links de gravações também podem ser processados diretamente. |
| Modelar | Escolha o vídeo e a técnica aprovada. O Director confere a origem das referências. O V9 usa o ritmo do perfil no enquadramento dinâmico com facecam. |
| Editor e gerados | O Editor mantém as ferramentas de edição manual do Hook Spark. Em **Gerados**, veja a prévia e a nota dos MP4 aprovados pelo V9 e salve rascunhos na agenda local. Confirme o envio no Studio da rede. |
| Integrações | Confira e instale o Ollama opcional para a revisão dos cortes. |

Em **Memes, B-roll e fundo**, use o [acervo real incluído](../biblioteca/ORIGEM.md) ou selecione sua pasta de GIFs, fotos e vídeos autorizados. O nome do arquivo (por exemplo `olha-isso.gif`) serve de pista para a transcrição. A edição coloca até uma inserção breve por clipe. A moldura escura ou um fundo de mídia opcional entra nos closes e reações. Os planos de gameplay seguem a configuração V9.

Em **Modelar**, a biblioteca lê `media-manifest.json` do projeto selecionado do AI Video Director. Para autorização de uso automático, identifique as mídias reais aprovadas com uma tag `real-footage` ou com `sourceKind` igual a `camera`, `photograph`, `real-footage` ou `archival`. Uma tag como `cue:olha isso` define a fala de entrada. Os arquivos usados têm hash conferido. A origem fica em `cortes.json` e os créditos preenchidos no manifesto acompanham a descrição sugerida dos clipes aprovados.

A **Biblioteca visual** exibe prévias, fonte, licença e frases de entrada. Use **Adicionar mídia minha** para cadastrar o arquivo original e habilite **Usar na edição** depois de revisar. O cadastro é local e aponta para o arquivo existente. Mantenha-o acessível no caminho cadastrado.

Para um vídeo local, habilite **Revisar inserções antes de exportar**. As prévias de 360 × 640 ficam em **Gerados**, com opções para manter, trocar ou remover uma inserção. A exportação refaz o mesmo plano na resolução escolhida. Guarde o vídeo de origem durante a revisão.

Em **Gerados**, aprovações, descartes e retenção informada ajudam a calibrar a nota pela rede e pelo tema. O ajuste editorial usa pelo menos três decisões do mesmo tema. A revisão exibe a justificativa da análise inicial, as contribuições da retenção e das decisões e os cortes parecidos.

Em **Ajustes**, use **Ver uso do disco** para medir versões, caches e capturas monitoradas. Em um volume Windows compatível, atualizações com `requirements.txt` idêntico reaproveitam os arquivos de dependências por hard links. O instalador valida o ambiente antes de trocar os atalhos.

Escolha português, inglês, espanhol ou detecção automática para transcrever a fala. O modo Leve usa uma tarefa local por vez. A triagem de lives combina transcrição, áudio, movimento e, quando disponível, reações de espectadores distintos no chat. A nota é uma estimativa editorial de potencial. Ao atualizar, o Codex procura um modelo Whisper completo no cache compartilhado e nas instalações anteriores antes de baixar.

Em **Ao vivo**, use **Preparar captura** no canal ou cole o link em **Captura e corte local**. O desktop usa Streamlink/FFmpeg em segundo plano. **Assistir no Brave** abre apenas a transmissão para visualização. O modo Leve usa até dois canais pelo painel e reserva 256 MiB na unidade de destino. A triagem conserva uma janela curta do sinal e remove os blocos que deixam de ser necessários. Os MP4 finalizados aparecem em **Cortes gerados** assim que são salvos.

Para replays públicos, o Clip Studio transcreve a faixa de áudio separada e baixa somente os intervalos escolhidos. Na captura e nos replays, você pode selecionar até Full HD (1080p), 2K (1440p) ou 4K (2160p), conforme a oferta do provedor. A captura conserva a resolução recebida sem recodificar. O V9 usa o detalhe da fonte para recortar e ampliar a facecam e entrega o corte em até 1080 × 1920. Resoluções maiores consomem mais banda e disco. Provedores sem áudio separado ou sem acesso ao intervalo registram uma mensagem na sessão.

A revisão final dá uma nota de 0 a 100. Quando o Ollama e o modelo visual configurado estão acessíveis, o V9 também avalia a fala e três quadros do MP4 pronto. A fila registra se a nota veio de visão, texto ou regras locais.

**Configurar IA local** mostra os modelos instalados e oferece a instalação oficial do Ollama mediante confirmação. Escolha Qwen3.5 4B para revisão multimodal ou 2B para menor consumo de memória. O banco local de critérios combina sinais de fala, ação, enquadramento e chat com as métricas reais de retenção já registradas no Clip Studio. [Modelos Qwen3.5](https://ollama.com/library/qwen3.5)

**Aceleração automática** testa a codificação NVIDIA NVENC, Intel Quick Sync e AMD AMF. O V9 usa CPU se o encoder de GPU falhar. A transcrição tenta CUDA quando disponível e usa CPU se as bibliotecas necessárias estiverem ausentes. Com **Somente CPU**, o V9 evita codificação por GPU. Capturar uma live continua sendo uma cópia do sinal, sem nova codificação.

**Preparar cópia compacta** tenta reduzir fontes de pelo menos 100 MB antes de editar. A cópia deve ter a mesma resolução e faixas, duração equivalente e pelo menos 20% de economia. O Clip Studio amostra três trechos e usa VMAF, ou SSIM quando o FFmpeg não contém VMAF. A cópia fica em uma pasta temporária e o original fica disponível para revisão ou nova edição. A qualidade real e o tamanho variam com o conteúdo. [FFmpeg](https://github.com/FFmpeg/FFmpeg) · [Netflix VMAF](https://github.com/Netflix/vmaf)

Para uma evolução futura, meça primeiro o tempo no FFmpeg e na transcrição. O [whisper.cpp](https://github.com/ggml-org/whisper.cpp) é uma alternativa em C/C++ para testar quando o pacote CUDA atual for grande demais. O [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) pode acrescentar detecção de cortes e transições em replays. Um componente em Rust faz sentido se a medição apontar o controle de buffers e arquivos como gargalo. C# já hospeda a interface Windows.

### Atualizações

Enquanto a janela está aberta, o aplicativo consulta o canal público a cada 20 minutos. Ao aceitar uma atualização, ele verifica o pacote e instala em uma pasta irmã. A v0.5.1 recebe a migração pelo mesmo canal. Quem instalou uma versão anterior ao verificador pode usar o instalador. O ZIP mantém os nomes que o atualizador antigo reconhece e traz o runtime do painel compactado dentro dele.

### Dados e serviços

O painel usa uma origem estável em loopback e um perfil Edge próprio por usuário Windows. O perfil permanece entre atualizações da v0.7.0 em diante. A migração reaproveita a pasta de saída, fila V9 e preferências locais. Projetos do Editor guardados em um perfil de navegador anterior podem ser transferidos pela exportação e importação do Editor. As funções Lovable que dependem de autenticação, gateway ou conectores continuam sujeitas à configuração desses serviços.

A distribuição Windows contém o painel compilado. O código desta integração está em `desktop/` e `desktop_actions.py`. O código-fonte do painel e a receita de empacotamento permanecem no repositório de origem do Hook Spark. Ao desenvolver somente com o checkout público, `Iniciar.cmd` abre o painel clássico. Para abrir a interface unificada, use o pacote da release.

