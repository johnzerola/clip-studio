# Alanzoka V9 — mapa de referência

Master vertical de 720 × 1280, 30 fps, 435 quadros e 14,5 segundos. Tempos no MP4 final. Numeração dos quadros começa em zero.

| Tempo (s) | Imagem | Montagem e animação | Áudio |
|---|---|---|---|
| 0–1 | Close com fundo difuso e gancho sobre a rádio | Gancho na abertura e legenda inferior por palavra | Fala à frente da trilha |
| 1–2 | Close até 1,733 s, seguido de rosto em cima e jogo embaixo | Corte seco após a promessa de conflito | A fala do plano seguinte entra cerca de 130 ms antes |
| 2–3 | Rosto em cima, direção da moto embaixo | Legenda perto da junção entre as duas imagens | Fala e gameplay |
| 3–4 | Cartão da rádio entra sobre a direita da gameplay | Fade de entrada de três quadros, feito na menção às músicas | Dois pulsos em 3,020 s |
| 4–5 | Cartão sai e o quadro abre para gameplay em 4,933 s | Fade curto do cartão e corte seco do layout | Fala contínua na troca de layout |
| 5–6 | Gameplay ocupa o quadro com extensão desfocada | Legenda inferior, foco na manobra da moto | Som do jogo e narração |
| 6–7 | Gameplay mantém a virada e a passagem iluminada | Deixe a ação seguir dentro do mesmo plano | Fala e trilha contínuas |
| 7–8 | Webcam redonda aparece no alto à direita em 7,100 s | Corte seco para outro trecho de gameplay com a câmera | Entrada antecipada da voz do próximo trecho |
| 8–9 | Gameplay com webcam dissolve para close a partir de 8,700 s | Sobreposição de cinco quadros. Uma camada de legenda | Batida grave em 8,670 s e J-cut |
| 9–10 | Close com cabelo, óculos e queixo visíveis | Sustente a reação e a legenda na zona inferior | Fala retoma o primeiro plano logo após a batida |
| 10–11 | Retorno ao dividido em 10,467 s | Corte seco ao voltar à explicação | Fala antecipada em cerca de 130 ms |
| 11–12 | Dividido acompanha a explicação e o avanço pela rua | Legenda perto da junção do layout | Fala sobre a trilha |
| 12–13 | Dividido mantém a composição; corte de continuidade em 12,833 s | Salto de origem mantendo o enquadramento | J-cut acompanha o salto |
| 13–14 | O streamer conclui o que fará com a música | Mantenha rosto e ação legíveis até a resolução | Voz e jogo |
| 14–14,5 | Dividido até o último quadro | Última legenda acompanha a palavra final | A resolução termina junto com o corte final |

## Pontos para reproduzir

- O cartão tem 290 × 164 px e fica em x=382, y=680 no quadro de 720 px. Começa em aproximadamente 3,023 s com fade de 0,10 s. Fica visível por 1,15 s, incluindo fade de saída de 0,12 s. Escale as coordenadas com o canvas. O desenho de barras permanece fixo dentro do cartão.
- A dissolução começa no quadro 261. Nos quadros 262–265 as duas imagens aparecem juntas. A partir do 266 fica o close. Preserve o movimento de saída e de entrada e aplique as legendas acima da dissolução.
- O efeito `radio` entra em 3,020 s com pico isolado de −15 dBFS. O `impacto` entra em 8,670 s com pico isolado de −12 dBFS, cerca de um quadro antes da virada visual. Ambos correspondem aos efeitos do banco local.
- A imagem faz o destaque com a troca de enquadramento. Os percentuais de zoom descritos para versões anteriores são parâmetros opcionais do banco, sem medição equivalente neste V9.
- Use branco com contorno escuro e amarelo na palavra ativa. Agrupe até quatro palavras. No dividido, a legenda fica perto da separação. No close, jogo e webcam circular, fica abaixo do assunto.

## Evidência

Inspeção visual a cada segundo e quadro a quadro em volta da dissolução. Para o cartão, comparei pixels da região com a receita de composição. Os tempos dos efeitos foram medidos no stem original e comparados com o banco local. O áudio do V9 corresponde aos mesmos pacotes AAC do V8. FFmpeg ebur128 mediu −15,9 LUFS integrados e pico verdadeiro de −2,3 dBTP no V9. Escuta artística fica para a aplicação em cada novo clipe.
