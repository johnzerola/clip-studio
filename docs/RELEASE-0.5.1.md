# Clip Studio v0.5.1 — consulta a cada 20 minutos

O app verifica novas releases a cada 20 minutos enquanto estiver aberto. O cache e o agendamento usam o mesmo intervalo. A consulta inicial acontece logo após abrir o painel, respeitando o cache dos últimos 20 minutos.

O aviso apresenta as mudanças e oferece atualizar. Capturas, renders e envios continuam adiando o aviso até terminarem. O app precisa de internet para consultar o GitHub.

Quem usa v0.5.0 recebe esta versão pelo atualizador no intervalo antigo. Após instalar v0.5.1, passa a consultar a cada 20 minutos. Versões anteriores à v0.5.0 precisam da primeira instalação manual.

Validação: teste com relógio simulado confirmou ausência de nova consulta antes de 20 minutos e nova consulta ao atingir o intervalo; compilação dos módulos e verificação do pacote publicado.
