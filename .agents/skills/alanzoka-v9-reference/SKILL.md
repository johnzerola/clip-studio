---
name: alanzoka-v9-reference
description: Reproduz a linguagem de edição do Alanzoka V9 em clipes verticais de gameplay e reação. Use quando o pedido citar o V9 ou pedir seus enquadramentos, legendas, dissolução, animação do cartão ou mix pontual.
---

# Referência Alanzoka V9

Leia [o mapa segundo a segundo](references/mapa.md) para montagem e [a referência estruturada](references/v9.json) para tempos de quadro, áudio e composição. Os tempos pertencem ao vídeo de referência. Em outra live, associe cada mudança à fala ou ação equivalente.

- Abra com uma reação compreensível e um gancho curto. Use a tela dividida para explicar, gameplay para mostrar e close para destacar a resposta. Mostre a webcam redonda no alto à direita durante a gameplay quando o rosto ainda acrescentar contexto.
- Use cortes secos para manter o ritmo. Faça a dissolução de cinco quadros na entrada do close principal, com movimento em ambos os lados. Aplique as legendas depois da transição para manter uma palavra ativa por vez. Preserve o J-cut quando houver pré-rolagem limpa.
- Anime o cartão de rádio na menção verbal. Use entrada e saída por opacidade. Sincronize o efeito `radio` a −15 dBFS de pico no efeito isolado e use `impacto` a −12 dBFS para preparar o close. Repita esses efeitos apenas quando cumprirem a mesma função.
- Mantenha a fala à frente da trilha, preserve áudio do jogo e confira o master perto de −16 LUFS com pico verdadeiro abaixo de −1 dBTP. Níveis do efeito isolado, ganho da trilha e volume final são medidas distintas.
- Prefira a captura original no close para preservar o detalhe. Mantenha cabelo, óculos e queixo no quadro. Confira o centro da gameplay e o minimapa ao reenquadrar.

## Com o MCP local

No projeto Clip Studio, use `get_v9_reference` para consultar o plano completo ou o segundo escolhido. Use `render_v9_accent` para testar a dissolução de cinco quadros com a batida antecipada. Use `render_sound` com `name=radio` e `peak_db=-15` para o cartão. A prévia usa imagens sintéticas e gera um novo arquivo em `work/effect-previews`.

Na montagem FFmpeg, sobreponha cinco quadros do plano de saída ao plano de entrada com `xfade=transition=fade`. Preserve a duração do master planejando a sobreposição na timeline. Em After Effects, o equivalente é sobrepor duas camadas e animar a opacidade da camada superior de 0% a 100% durante cinco quadros, com a legenda acima.

Valide pela decodificação completa, por quadros antes, durante e depois do acento e por medição de loudness. Ouça a fala, a batida e o cartão no volume normal de reprodução antes da aprovação artística.
