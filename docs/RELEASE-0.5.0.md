# Clip Studio v0.5.0 — Modelar e atualização assistida

- Modelar importa presets aprovados do AI Video Director e encaminha cortes para a fila com motor V9.
- Consulta diária de releases durante o uso e ao iniciar, sem bloquear o painel.
- Aviso com notas da versão e instalação automática após clicar em Atualizar agora.
- Download com checksum SHA-256, extração com limites de caminhos e instalação numa pasta nova.
- Preferências, pasta de saída, fila e credencial YouTube protegida pelo Windows preservadas. A instalação anterior permanece disponível.
- O atalho muda após o diagnóstico; o app novo abre automaticamente. Capturas, renders e envios devem terminar antes de atualizar.

## Primeira atualização

Quem usa v0.4.0 deve baixar este ZIP, extrair e executar Instalar.cmd uma vez. O atualizador automático vale para versões futuras a partir da v0.5.0. Não existe atualização retroativa de código já instalado.

## Validação e limites

Compilação dos módulos, testes de checksum, extração, URLs, preservação de preferências e falha do instalador passaram. A troca de instalação e a abertura foram verificadas com processos simulados; a instalação completa em outro Windows ainda precisa de validação. O render V9 é o motor existente; esta mudança não revalida sua qualidade artística.

O Modelar aceita perfis aprovados v2/v3 e verifica hashes. O ritmo importado serve para revisão; tipografia, cor e movimentos inferidos não são aplicados automaticamente. O novo painel GitHub ainda não fornecido permanece fora desta integração.
