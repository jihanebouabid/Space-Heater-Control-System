#include <Wire.h>

#define ADS1115_ADDRESS 0x48

// ===================== CONFIG GENERAL =====================
const float VREF = 4.096;
const float LSB  = VREF / 32768.0;
const float CURRENT_K = 30.0;

// LM35 en A2 (AIN2)
#define LM35_CHANNEL 2
const float LM35_K = 18.5;
const float T_REF_ROOM = 25.0;

// ===================== RELAY CONTROL =====================
#define RELAY_PIN 12
bool heaterOn = false;

const float HEATER_THRESHOLD = 40.0;
const float HYST = 2.0;

// ===================== VARIABLES =====================
unsigned long time_ant = 0;
unsigned long act_time = 0;
unsigned long difTime = 0;

double quadratic_sum_rms = 0.0;
int quadratic_sum_counter = 0;
double freq = 50.0;

double accumulated_current = 0.0;
int accumulated_counter = 0;

double v_calib = 0.0;
float temp_offset_C = 0.0;

unsigned long lastTempRead = 0;
const unsigned long tempInterval = 5000;

// ===================== ADS1115 =====================
void ads1115_start_single(uint8_t channel) {
  uint8_t muxBits;

  switch (channel) {
    case 0: muxBits = 0b100; break;
    case 1: muxBits = 0b101; break;
    case 2: muxBits = 0b110; break;
    case 3: muxBits = 0b111; break;
    default: muxBits = 0b101; break;
  }

  uint16_t config = 0;
  config |= (1 << 15);
  config |= (muxBits << 12);
  config |= (0b010 << 9);
  config |= (1 << 8);
  config |= (0b111 << 5);
  config |= 0x0003;

  Wire.beginTransmission(ADS1115_ADDRESS);
  Wire.write(0x01);
  Wire.write((uint8_t)(config >> 8));
  Wire.write((uint8_t)(config & 0xFF));
  Wire.endTransmission();
}

float ads1115_read_voltage() {
  while (true) {
    Wire.beginTransmission(ADS1115_ADDRESS);
    Wire.write(0x01);
    Wire.endTransmission();

    Wire.requestFrom(ADS1115_ADDRESS, 2);
    uint16_t cfg = (Wire.read() << 8) | Wire.read();
    if (cfg & 0x8000) break;
    delayMicroseconds(100);
  }

  Wire.beginTransmission(ADS1115_ADDRESS);
  Wire.write(0x00);
  Wire.endTransmission();

  Wire.requestFrom(ADS1115_ADDRESS, 2);
  int16_t raw = (Wire.read() << 8) | Wire.read();

  return raw * LSB;
}

// ===================== CURRENT MEASUREMENT =====================
float read_current_instant_voltage() {
  ads1115_start_single(1);
  float v = ads1115_read_voltage();
  v -= v_calib;

  if (fabs(v) < 0.015) v = 0.0;
  return v;
}

// ===================== TEMPERATURE MEASUREMENT =====================
float read_lm35_temperature() {
  ads1115_start_single(LM35_CHANNEL);
  float v = ads1115_read_voltage();
  float temp_raw = v * LM35_K;
  return temp_raw + temp_offset_C;
}

// ===================== HEATER CONTROL =====================
void controlHeater(float temp) {

  if (!heaterOn && temp < (HEATER_THRESHOLD - HYST)) {
      digitalWrite(RELAY_PIN, LOW);
      heaterOn = true;
  }

  if (heaterOn && temp > HEATER_THRESHOLD) {
      digitalWrite(RELAY_PIN, HIGH);
      heaterOn = false;
  }
}

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);
  Wire.begin();
  delay(200);

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);

  const int samples = 400;
  double sum = 0;
  for (int i = 0; i < samples; i++) {
    ads1115_start_single(1);
    sum += ads1115_read_voltage();
    delay(3);
  }
  v_calib = sum / samples;

  const int tempSamples = 200;
  double sumT = 0;
  for (int i = 0; i < tempSamples; i++) {
    ads1115_start_single(LM35_CHANNEL);
    sumT += ads1115_read_voltage();
    delay(5);
  }

  float v_temp_calib = sumT / tempSamples;
  float temp_measured = v_temp_calib * LM35_K;
  temp_offset_C = T_REF_ROOM - temp_measured;
}


void loop() {

  act_time = micros();
  difTime = act_time - time_ant;

  if (difTime > 1000) {
    time_ant = act_time;

    float Vint = read_current_instant_voltage();
    float Iint = Vint * CURRENT_K;

    quadratic_sum_rms += Iint * Iint * (difTime / 1000000.0);
    quadratic_sum_counter++;
  }

  if (quadratic_sum_counter >= 20) {
    double Irms = sqrt(quadratic_sum_rms * freq);

    quadratic_sum_rms = 0;
    quadratic_sum_counter = 0;

    if (Irms < 0.05) Irms = 0.0;

    accumulated_current += Irms;
    accumulated_counter++;
  }

  if (millis() - lastTempRead >= tempInterval) {
    lastTempRead = millis();

    float tempC = read_lm35_temperature();

    double Irms_filt =
      (accumulated_counter > 0) ?
      accumulated_current / accumulated_counter : 0;

    accumulated_current = 0;
    accumulated_counter = 0;

    // --------------- FORMATTING ----------------
    Serial.print("TEMP:");
    Serial.print(tempC, 2);
    Serial.print(",CURR:");
    Serial.println(Irms_filt, 3);

    // -------- CONTROL HEATER --------
    controlHeater(tempC);
}
}

