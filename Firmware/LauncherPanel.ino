#include <Arduino.h>

/*
  El flujo principal es:
    1. Configuraciones de los pines y estado inicial.
    2. Lee los comandos por Serial (LED|x|modo|periodo, PING).
    3. Escanea botones con debounce y generar eventos DOWN/UP/HOLD.
    4. Actualizar el parpadeo de los LEDs según el modo seleccionado.
*/

// Orden de pines físicos asociados a cada botón (activos en LOW por pull-up interno)
const uint8_t BUTTON_PINS[4] = {2, 3, 4, 5};
// LEDs correspondientes a los botones para señalización visual
const uint8_t LED_PINS[4] = {8, 9, 10, 11};
// Ventana mínima para aceptar un cambio de estado estable
const unsigned long DEBOUNCE_MS = 25;
// Intervalo para reenviar eventos HOLD mientras el botón continúa presionado
const unsigned long HOLD_REPEAT_MS = 1500;
// Periodo por defecto para parpadeo de LEDs en modo BLINK
const unsigned long DEFAULT_BLINK_MS = 500;

// Enumeración de los modos disponibles para cada LED
enum LedMode { LED_OFF, LED_ON, LED_BLINK };

struct LedState {
  LedMode mode = LED_OFF;
  unsigned long period = DEFAULT_BLINK_MS;
  unsigned long lastToggle = 0;
  bool level = LOW;
};

bool buttonReading[4];
bool buttonState[4];
unsigned long lastDebounce[4];
unsigned long lastHoldSent[4];
LedState leds[4];

char serialBuffer[64];
uint8_t bufferIndex = 0;

void sendButtonEvent(uint8_t buttonIndex, const char *eventName) {
  Serial.print("BTN|");
  Serial.print(buttonIndex + 1);
  Serial.print('|');
  Serial.println(eventName);
}

void applyLedState(uint8_t idx, bool level) {
  leds[idx].level = level;
  digitalWrite(LED_PINS[idx], level ? HIGH : LOW);
}

void setLedMode(uint8_t idx, LedMode mode, unsigned long period = DEFAULT_BLINK_MS) {
  leds[idx].mode = mode;
  leds[idx].period = period;
  leds[idx].lastToggle = millis();
  switch (mode) {
    case LED_OFF:
      applyLedState(idx, LOW);
      break;
    case LED_ON:
      applyLedState(idx, HIGH);
      break;
    case LED_BLINK:
      applyLedState(idx, HIGH);
      break;
  }
}

// Recibe el comando LED|id|modo|periodo y actualiza la configuración del LED indicado
void handleLedCommand(uint8_t ledId, const String &modeToken, const String &argToken) {
  if (ledId == 0 || ledId > 4) {
    return;
  }
  uint8_t idx = ledId - 1;
  String modeUpper = modeToken;
  modeUpper.toUpperCase();

  if (modeUpper == "ON") {
    setLedMode(idx, LED_ON);
  } else if (modeUpper == "OFF") {
    setLedMode(idx, LED_OFF);
  } else if (modeUpper == "BLINK") {
    unsigned long period = argToken.length() ? argToken.toInt() : DEFAULT_BLINK_MS;
    if (period < 100) {
      period = 100;
    }
    setLedMode(idx, LED_BLINK, period);
  }
}

// Procesa comandos recibidos por Serial (LED y PING por ahora)
void processCommand(const String &command) {
  if (command.length() == 0) {
    return;
  }
  int first = command.indexOf('|');
  String topic = first == -1 ? command : command.substring(0, first);
  topic.toUpperCase();

  if (topic == "LED") {
    int second = command.indexOf('|', first + 1);
    if (second == -1) return;
    int third = command.indexOf('|', second + 1);

    uint8_t ledId = command.substring(first + 1, second).toInt();
    String modeToken;
    String argToken;

    if (third == -1) {
      modeToken = command.substring(second + 1);
    } else {
      modeToken = command.substring(second + 1, third);
      argToken = command.substring(third + 1);
    }
    handleLedCommand(ledId, modeToken, argToken);
  } else if (topic == "PING") {
    Serial.println("PONG");
  }
}

// Acumula caracteres recibidos hasta detectar \n/\r y luego procesa el comando completo
void readSerialInput() {
  while (Serial.available()) {
    char incoming = Serial.read();
    if (incoming == '\n' || incoming == '\r') {
      if (bufferIndex > 0) {
        serialBuffer[bufferIndex] = '\0';
        processCommand(String(serialBuffer));
        bufferIndex = 0;
      }
    } else {
      if (bufferIndex < sizeof(serialBuffer) - 1) {
        serialBuffer[bufferIndex++] = incoming;
      } else {
        bufferIndex = 0;
      }
    }
  }
}

// Alterna el estado de los LEDs en modo BLINK respetando su periodo
void updateBlinking(unsigned long now) {
  for (uint8_t i = 0; i < 4; ++i) {
    if (leds[i].mode == LED_BLINK) {
      if (now - leds[i].lastToggle >= leds[i].period) {
        leds[i].lastToggle = now;
        applyLedState(i, !leds[i].level);
      }
    }
  }
}

// Escanea botones con debounce, envía eventos DOWN/UP/HOLD y controla la cadencia HOLD
void monitorButtons(unsigned long now) {
  for (uint8_t i = 0; i < 4; ++i) {
    bool pressed = digitalRead(BUTTON_PINS[i]) == LOW;
    if (pressed != buttonReading[i]) {
      lastDebounce[i] = now;
      buttonReading[i] = pressed;
    }

    if ((now - lastDebounce[i]) > DEBOUNCE_MS) {
      if (pressed != buttonState[i]) {
        buttonState[i] = pressed;
        if (pressed) {
          sendButtonEvent(i, "DOWN");
          lastHoldSent[i] = now;
        } else {
          sendButtonEvent(i, "UP");
        }
      } else if (pressed && (now - lastHoldSent[i]) > HOLD_REPEAT_MS) {
        sendButtonEvent(i, "HOLD");
        lastHoldSent[i] = now;
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    ;
  }

  // Configuración inicial: pines de botones como entradas con pull-up y LEDs como salidas
  for (uint8_t i = 0; i < 4; ++i) {
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    pinMode(LED_PINS[i], OUTPUT);
    digitalWrite(LED_PINS[i], LOW);
    bool pressed = digitalRead(BUTTON_PINS[i]) == LOW;
    buttonReading[i] = pressed;
    buttonState[i] = pressed;
    lastDebounce[i] = 0;
    lastHoldSent[i] = 0;
    setLedMode(i, LED_OFF);
  }

  Serial.println("READY|ARDUINO");
}

void loop() {
  unsigned long now = millis();
  readSerialInput();   // Prioridad: atender comandos entrantes tan pronto como aparezcan
  monitorButtons(now); // Luego actualizar el estado de botones y emitir eventos
  updateBlinking(now); // Finalmente, recalcular parpadeo de LEDs según corresponda
}
