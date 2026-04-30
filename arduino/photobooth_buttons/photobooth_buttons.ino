/*
 * photobooth_buttons.ino — firmware Arduino Nano pour 3 boutons-poussoirs
 * à LED intégrée (blanc à gauche, vert au centre, rouge à droite).
 *
 * Cible matériel : Arduino Nano (ATmega328P, 16 MHz).
 * Liaison hôte   : port série USB (115200 bauds, 8N1).
 *
 * ─── Câblage ACTUALISÉ (Retour Pin 9) ────────────────────────────────────
 *
 *   Bouton GAUCHE (blanc)   ── D2 (INPUT_PULLUP, contact au GND)
 *   Bouton MILIEU (vert)    ── D3
 *   Bouton DROITE (rouge)   ── D4
 *
 *   LED    GAUCHE (blanc)   ── D5  (PWM, anode via résistance série)
 *   LED    MILIEU (vert)    ── D6  (PWM)
 *   LED    DROITE (rouge)   ── D9  (PWM) <--- Retour sur la Pin 9
 *
 *   Toutes les masses communes (GND).
 *
 *   ⚠ Les interrupteurs-poussoirs à LED intégrée ont typiquement
 *   4 bornes : 2 pour le contact (NO), 2 pour la LED (anode/cathode).
 *   Voir docs/ARDUINO.md pour les schémas détaillés + calcul des résistances.
 *
 * ─── Protocole série ─────────────────────────────────────────────────────
 *
 *   Arduino  → PC  (émis par le firmware)
 *       READY\n            boot OK
 *       L\n                bouton gauche pressé
 *       M\n                bouton milieu pressé
 *       R\n                bouton droit pressé
 *       PONG\n             réponse à PING
 *
 *   PC       → Arduino   (commandes reçues)
 *       LED:L:OFF\n        éteint la LED gauche
 *       LED:L:ON\n         allume fixe
 *       LED:L:PULSE\n      respiration lente (invitation)
 *       LED:L:FAST\n       clignotement rapide (alerte)
 *       LED:M:...          idem pour la LED milieu
 *       LED:R:...          idem pour la LED droite
 *       LED:ALL:OFF\n      éteint les 3 d'un coup
 *       PING\n             demande de PONG (test de liaison)
 *
 *   La trame est terminée par '\n'. '\r' est toléré et ignoré.
 *
 * ─── Comportement LED ────────────────────────────────────────────────────
 *
 *   ON      : pleine intensité (LED_MAX_PWM).
 *   OFF     : éteint.
 *   PULSE   : sinusoïde douce ~0.5 Hz, 20 → 255 (respiration).
 *   FAST    : carré 4 Hz, 0 ↔ 255 (plus urgent).
 *
 *   Chaque LED a son propre état — la boucle principale met à jour les
 *   3 sorties PWM à chaque itération.
 */

#include <Arduino.h>

// ─── Configuration ───────────────────────────────────────────────────────

const uint8_t PIN_BTN_L = 2;
const uint8_t PIN_BTN_M = 3;
const uint8_t PIN_BTN_R = 4;

const uint8_t PIN_LED_L = 5;  // PWM (Blanc - Gauche)
const uint8_t PIN_LED_M = 6;  // PWM (Vert - Milieu)
const uint8_t PIN_LED_R = 9;  // PWM (Rouge - Droite) <--- Remis sur 9

const unsigned long BAUDRATE     = 115200;
const unsigned long DEBOUNCE_MS  = 30;     // anti-rebond logiciel
const uint8_t        LED_MAX_PWM  = 255;

// Vitesse des effets.
const float PULSE_SPEED_HZ = 0.5f;   // respiration : 0.5 cycle/s (2 s par respiration)
const float FAST_SPEED_HZ  = 4.0f;   // clignotement rapide : 4 Hz

// ─── État LED ────────────────────────────────────────────────────────────

enum LedMode : uint8_t { MODE_OFF = 0, MODE_ON = 1, MODE_PULSE = 2, MODE_FAST = 3 };

LedMode ledMode[3] = { MODE_OFF, MODE_OFF, MODE_OFF };
const uint8_t LED_PINS[3] = { PIN_LED_L, PIN_LED_M, PIN_LED_R };

// ─── État boutons ────────────────────────────────────────────────────────

struct Button {
  uint8_t pin;
  char    label;
  bool    lastStable;     // true = relâché (pullup)
  bool    lastRaw;
  unsigned long lastChangeMs;
};

Button buttons[3] = {
  { PIN_BTN_L, 'L', true, true, 0 },
  { PIN_BTN_M, 'M', true, true, 0 },
  { PIN_BTN_R, 'R', true, true, 0 },
};

// ─── Buffer de réception série ───────────────────────────────────────────

const uint8_t RX_BUF_SIZE = 32;
char rxBuf[RX_BUF_SIZE];
uint8_t rxLen = 0;

// ─── Setup ───────────────────────────────────────────────────────────────

void setup() {
  for (uint8_t i = 0; i < 3; i++) {
    pinMode(buttons[i].pin, INPUT_PULLUP);
    pinMode(LED_PINS[i], OUTPUT);
    analogWrite(LED_PINS[i], 0);
  }

  Serial.begin(BAUDRATE);

  // Petit auto-test visuel : les 3 LEDs s'allument 200 ms à l'ordre.
  for (uint8_t i = 0; i < 3; i++) {
    analogWrite(LED_PINS[i], LED_MAX_PWM);
    delay(200);
    analogWrite(LED_PINS[i], 0);
  }

  Serial.println(F("READY"));
}

// ─── Lecture boutons ─────────────────────────────────────────────────────

void pollButtons() {
  const unsigned long now = millis();
  for (uint8_t i = 0; i < 3; i++) {
    Button& b = buttons[i];
    bool raw = digitalRead(b.pin);

    if (raw != b.lastRaw) {
      b.lastRaw = raw;
      b.lastChangeMs = now;
    }

    if ((now - b.lastChangeMs) >= DEBOUNCE_MS && raw != b.lastStable) {
      b.lastStable = raw;
      if (!raw) {
        Serial.println(b.label);
      }
    }
  }
}

// ─── Pilotage LED ────────────────────────────────────────────────────────

uint8_t computePwm(LedMode mode, unsigned long nowMs) {
  switch (mode) {
    case MODE_OFF:
      return 0;
    case MODE_ON:
      return LED_MAX_PWM;
    case MODE_PULSE: {
      float phase = (float)(nowMs % 4000) / 4000.0f;
      float s = sin(phase * 2.0f * PI);
      float v = 0.5f * (s + 1.0f);
      return (uint8_t)(20 + v * (LED_MAX_PWM - 20));
    }
    case MODE_FAST: {
      return ((nowMs / 125) & 1) ? LED_MAX_PWM : 0;
    }
  }
  return 0;
}

void updateLeds() {
  const unsigned long now = millis();
  for (uint8_t i = 0; i < 3; i++) {
    analogWrite(LED_PINS[i], computePwm(ledMode[i], now));
  }
}

// ─── Traitement des commandes série ──────────────────────────────────────

int ledIndexForLabel(char c) {
  if (c == 'L') return 0;
  if (c == 'M') return 1;
  if (c == 'R') return 2;
  return -1;
}

LedMode parseMode(const char* s) {
  if (!strcmp(s, "OFF"))   return MODE_OFF;
  if (!strcmp(s, "ON"))    return MODE_ON;
  if (!strcmp(s, "PULSE")) return MODE_PULSE;
  if (!strcmp(s, "FAST"))  return MODE_FAST;
  return MODE_OFF;
}

void handleCommand(char* line) {
  if (!strcmp(line, "PING")) {
    Serial.println(F("PONG"));
    return;
  }
  if (!strncmp(line, "LED:", 4)) {
    char* p = line + 4;
    if (!strncmp(p, "ALL:", 4)) {
      LedMode m = parseMode(p + 4);
      for (uint8_t i = 0; i < 3; i++) ledMode[i] = m;
      return;
    }
    if (strlen(p) < 3 || p[1] != ':') return;
    int idx = ledIndexForLabel(p[0]);
    if (idx < 0) return;
    ledMode[idx] = parseMode(p + 2);
    return;
  }
}

void pollSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuf[rxLen] = '\0';
      if (rxLen > 0) handleCommand(rxBuf);
      rxLen = 0;
    } else if (rxLen < RX_BUF_SIZE - 1) {
      rxBuf[rxLen++] = c;
    } else {
      rxLen = 0;
    }
  }
}

// ─── Boucle principale ───────────────────────────────────────────────────

void loop() {
  pollButtons();
  pollSerial();
  updateLeds();
}
