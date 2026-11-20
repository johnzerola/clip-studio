# Modelar e AI Video Director

Ponte opcional entre o Clip Studio e os presets aprovados do AI Video Director, localizado na conversa “Criar projeto Edição painel GTA 6”. O novo painel GitHub do usuário ainda não foi fornecido: esta integração é do motor local, sem presumir sua API futura.

## Painel

Abra **Modelar…** na barra superior. Escolha a pasta do projeto AI Video Director, depois um JSON em `analises/approved-techniques`. A ponte aceita `approved-editing-technique-v1`, com perfil de técnicas v2 ou v3, política de revisão e hashes das referências correspondentes. Os caminhos ficam confinados ao projeto selecionado. Os hashes são conferidos por leitura em fluxo numa thread temporária. Não copia as referências nem instala o AI Video Director.

Depois da verificação, o painel informa o ritmo observado e pede a escolha de um vídeo. O trabalho entra na mesma fila do painel, CLI e MCP. Acompanha-se em **Trabalhos CLI/MCP…**. O pedido salvo inclui a origem do preset, seu hash, fontes, ritmo e observações.

## Edição

O render usa o fluxo existente de jobs: modo Leve, um corte, estilo dinâmico, legendas, transição V9, tratamento de voz, trilha automática, compactação e revisão final. A revisão pode rejeitar o resultado. O ritmo do preset é uma orientação de revisão, não substitui a direção de câmera aprovada. Cor, tipografia, zoom e som inferidos das referências não são reproduzidos automaticamente por esta ponte.

## CLI

```powershell
.venv/Scripts/python.exe modelar_bridge.py --project "C:/MeuProjeto" --preset "C:/MeuProjeto/analises/approved-techniques/preset.json"
.venv/Scripts/python.exe modelar_bridge.py --project "C:/MeuProjeto" --preset "C:/MeuProjeto/analises/approved-techniques/preset.json" --source "C:/Videos/live.mp4" --output "C:/Cortes" --ranges "30-90" --submit
```

Sem `--submit`, apenas verifica e devolve o perfil. Com `--submit`, inicia a edição. `--ranges` opcional delimita um trecho; sem marcas, o motor seleciona os momentos.

## MCP

A ferramenta `modelar_reference(project, preset)` verifica o perfil e devolve o resumo. O fluxo existente de jobs continua disponível para plano, render, consulta e cancelamento.

## Validação desta entrega

Compilação dos módulos modificados e testes com arquivos sintéticos: leitura do perfil v3 aprovado, composição do pedido V9, rejeição de fonte alterada, ritmo não finito e caminho fora do projeto. Sem novas dependências. Não foi executado render nem testada a janela nesta máquina: a instalação G: está indisponível e a cópia recuperada não tem o ambiente de vídeo instalado.
