#include <WiFi.h>

// Configurações de rede
const char *SSID = "COLOQUE_SUA_REDE_AQUI";
const char *PASSWORD = "COLOQUE_SUA_SENHA_AQUI";

// LED de status para indicar tentativa de reconexão
constexpr uint8_t STATUS_LED_PIN = 2;

// Controle de reconexão com tempos de espera crescentes (backoff exponencial)
constexpr unsigned long RECONNECT_DELAY_INITIAL_MS = 500;
constexpr unsigned long RECONNECT_DELAY_MAX_MS = 10000;
constexpr unsigned long LED_BLINK_INTERVAL_MS = 250;

// Controle de notificações e cooldowns
constexpr unsigned long NOTIFICATION_COOLDOWN_MS = 60000; // Ajuste conforme necessário
unsigned long ultimoEnvioNotificacao = 0;

unsigned long proximaTentativaReconexao = 0;
unsigned long atrasoReconexaoAtual = RECONNECT_DELAY_INITIAL_MS;
unsigned long proximaMudancaLed = 0;
bool reconectando = false;

bool prontoParaNovaNotificacao(unsigned long agora)
{
  return ultimoEnvioNotificacao == 0 || (agora - ultimoEnvioNotificacao) >= NOTIFICATION_COOLDOWN_MS;
}

void resetarCooldowns()
{
  ultimoEnvioNotificacao = 0;
}

void enviarNotificacaoRestabelecimento()
{
  // Substitua pelo envio real (MQTT, HTTP, etc.).
  Serial.println("WiFi restabelecido. Cooldowns resetados.");
}

void indicarReconexaoPisca()
{
  unsigned long agora = millis();
  if (agora - proximaMudancaLed >= LED_BLINK_INTERVAL_MS)
  {
    proximaMudancaLed = agora;
    digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN));
  }
}

void conectarWiFi()
{
  Serial.print("Conectando ao WiFi: ");
  Serial.println(SSID);
  WiFi.begin(SSID, PASSWORD);
}

void monitorarWiFi()
{
  wl_status_t statusAtual = WiFi.status();
  unsigned long agora = millis();

  if (statusAtual == WL_CONNECTED)
  {
    if (reconectando)
    {
      reconectando = false;
      atrasoReconexaoAtual = RECONNECT_DELAY_INITIAL_MS;
      proximaTentativaReconexao = 0;
      proximaMudancaLed = agora;

      // LED ligado de forma contínua para indicar conexão saudável
      digitalWrite(STATUS_LED_PIN, HIGH);

      // Reseta cooldowns para permitir novos alertas imediatamente após o restabelecimento
      resetarCooldowns();
      if (prontoParaNovaNotificacao(agora))
      {
        ultimoEnvioNotificacao = agora;
        enviarNotificacaoRestabelecimento();
      }
    }
    return;
  }

  // Quando desconectado
  if (!reconectando)
  {
    reconectando = true;
    proximaTentativaReconexao = 0;
    atrasoReconexaoAtual = RECONNECT_DELAY_INITIAL_MS;
    digitalWrite(STATUS_LED_PIN, LOW); // Apaga inicialmente
  }

  // Pisca o LED para indicar que está tentando reconectar
  indicarReconexaoPisca();

  // Tenta reconectar respeitando o backoff exponencial
  if (agora - proximaTentativaReconexao >= atrasoReconexaoAtual)
  {
    proximaTentativaReconexao = agora;
    WiFi.disconnect();
    conectarWiFi();
    atrasoReconexaoAtual = min(atrasoReconexaoAtual * 2, RECONNECT_DELAY_MAX_MS);
  }
}

void setup()
{
  Serial.begin(115200);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);
  conectarWiFi();
}

void loop()
{
  monitorarWiFi();
  // Demais tarefas da aplicação podem ser chamadas aqui
}

