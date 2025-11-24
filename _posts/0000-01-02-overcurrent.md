---
layout: slide
title: "Monitoramento de corrente do relé"
---
* Integrar um sensor de corrente (ex.: ACS712) ou um shunt de feedback na saída do relé para acompanhar o consumo em tempo real.
* Definir faixa operacional esperada e desligar o relé imediatamente se a leitura sair desse intervalo.
* Registrar o evento e emitir notificação com o texto "sobrecorrente/sem carga" sempre que o alarme for disparado.

```c
float corrente = lerCorrenteACS712();
if (corrente < CORRENTE_MIN || corrente > CORRENTE_MAX) {
  desligarRele();
  registrarEvento("sobrecorrente/sem carga", corrente);
  enviarNotificacao("sobrecorrente/sem carga", corrente);
}
```
