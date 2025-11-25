---
layout: slide
title: "ESP32: correção rápida do código de drenagem"
---

- **Use pinos com `INPUT_PULLUP` real**: troque os sensores para GPIO 21 e 22 (ou 18/19). Eles aceitam pull-up interno; 34/35 não e 32/33 podem falhar sem resistor externo.
- **Fiação ativa em LOW**: botão entre pino e GND; deixe o outro terminal do botão livre (pull-up interno mantém HIGH). Sem resistor externo, não ligue o botão ao 3V3.
- **Ajuste os pinos no código**:
  ```cpp
  const int PIN_SENSOR_INF = 21;
  const int PIN_SENSOR_SUP = 22;
  ...
  pinMode(PIN_SENSOR_INF, INPUT_PULLUP);
  pinMode(PIN_SENSOR_SUP, INPUT_PULLUP);
  ```
- **Inicialize os estados logo após o `pinMode`** para evitar começar travado:
  ```cpp
  sInf.estadoAtual = (digitalRead(PIN_SENSOR_INF) == LOW);
  sSup.estadoAtual = (digitalRead(PIN_SENSOR_SUP) == LOW);
  sInf.ultimaLeituraFisica = sInf.estadoAtual ? LOW : HIGH;
  sSup.ultimaLeituraFisica = sSup.estadoAtual ? LOW : HIGH;
  sInf.tempoMudanca = sSup.tempoMudanca = millis();
  ```
- **No Wokwi**, ligue cada botão entre o pino (21/22) e GND; remova qualquer ligação ao 3V3. Se precisar manter 32/33 ou 34/35, adicione um resistor de 10 kΩ para VCC (pull-up externo) e mantenha o botão para GND.
- **Teste esperado**: ao manter os dois botões pressionados (LOW), LEDs verde/azul acesos e bomba/rele ligados; soltando o inferior (subindo a boia), o sistema desliga e imprime o relatório.
