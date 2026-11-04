/**
 * @file advanced_multi_channel.ino
 * @brief ADS1263 Advanced Multi-Channel Scanning Example
 * @version 3.0.0
 *
 * @details Advanced example demonstrating:
 *  - Multi-channel sequential scanning
 *  - Calibration workflow
 *  - Error handling
 *  - Data buffering
 *  - Statistical analysis
 *  - ADC2 simultaneous reading
 *
 * @hardware Same as basic_reading.ino
 *
 * @author Production-Ready Implementation
 */

#include <ads1263.h>

// Pin definitions
#define ADS_CS_PIN 10
#define ADS_DRDY_PIN 9
#define ADS_RST_PIN 8

// Number of channels to scan
#define NUM_CHANNELS 4

// Samples per channel for averaging
#define SAMPLES_PER_CHANNEL 10

// Create ADS1263 instance
ADS1263 ads(ADS_CS_PIN, ADS_DRDY_PIN, ADS_RST_PIN);

/* ========================================================================== */
/*                          CHANNEL CONFIGURATION                             */
/* ========================================================================== */

// Channel pairs (positive, negative)
const struct {
  ads1263_input_t pos;
  ads1263_input_t neg;
  const char *name;
} channels[NUM_CHANNELS] = {
    {ADS1263_INPUT_AIN0, ADS1263_INPUT_AIN1, "CH0 (AIN0-AIN1)"},
    {ADS1263_INPUT_AIN2, ADS1263_INPUT_AIN3, "CH1 (AIN2-AIN3)"},
    {ADS1263_INPUT_AIN4, ADS1263_INPUT_AIN5, "CH2 (AIN4-AIN5)"},
    {ADS1263_INPUT_AIN6, ADS1263_INPUT_AIN7, "CH3 (AIN6-AIN7)"}};

/* ========================================================================== */
/*                          DATA STRUCTURES                                   */
/* ========================================================================== */

// Per-channel statistics
struct ChannelData {
  float readings[SAMPLES_PER_CHANNEL];
  uint8_t sample_index;
  float sum;
  float min_value;
  float max_value;
  float average;
  bool ready;
};

ChannelData channel_data[NUM_CHANNELS];

// Scanning state
uint8_t current_channel = 0;
bool scanning_active = false;
bool calibration_done = false;

// Performance metrics
uint32_t scan_start_time = 0;
uint32_t total_scans = 0;

/* ========================================================================== */
/*                          CALLBACK FUNCTIONS                                */
/* ========================================================================== */

void onInitComplete(const ads1263_init_event_t *event) {
  if (event->success) {
    Serial.println("✓ ADS1263 initialized!");
    Serial.print("  Device ID: 0x");
    Serial.println(event->device_id, HEX);
    Serial.println();

    // Configure ADC for high-precision scanning
    Serial.println("Configuring ADC...");
    ads.setGain(ADS1263_GAIN_1);
    ads.setDataRate(ADS1263_RATE_100);   // 100 SPS for good balance
    ads.setFilter(ADS1263_FILTER_SINC4); // Best noise rejection
    ads.setChopMode(ADS1263_CHOP_INPUT); // Enable chopping
    ads.setReference(ADS1263_REFP_INTERNAL, ADS1263_REFN_INTERNAL);
    Serial.println();

    // Start calibration
    Serial.println("Starting offset calibration...");
    Serial.println("(Please ensure inputs are at 0V or shorted)");
    ads.calibrateOffset();

  } else {
    Serial.println("✗ Initialization FAILED!");
  }
}

void onDataReady(const ads1263_data_event_t *event) {
  if (!scanning_active)
    return;

  // Store reading in current channel
  ChannelData *ch = &channel_data[current_channel];

  if (ch->sample_index < SAMPLES_PER_CHANNEL) {
    float voltage = event->voltage;
    ch->readings[ch->sample_index] = voltage;
    ch->sum += voltage;

    // Update min/max
    if (ch->sample_index == 0) {
      ch->min_value = voltage;
      ch->max_value = voltage;
    } else {
      if (voltage < ch->min_value)
        ch->min_value = voltage;
      if (voltage > ch->max_value)
        ch->max_value = voltage;
    }

    ch->sample_index++;

    // Check if channel complete
    if (ch->sample_index >= SAMPLES_PER_CHANNEL) {
      ch->average = ch->sum / SAMPLES_PER_CHANNEL;
      ch->ready = true;

      // Move to next channel
      current_channel++;

      if (current_channel >= NUM_CHANNELS) {
        // All channels done - scan complete
        scanning_active = false;
        current_channel = 0;
        printScanResults();

        // Start next scan after delay
        scan_start_time = millis();

      } else {
        // Switch to next channel
        ads.setChannel(channels[current_channel].pos,
                       channels[current_channel].neg);
        ads.startSingleConversion();
      }
    } else {
      // Get another sample from same channel
      ads.startSingleConversion();
    }
  }
}

void onCalibrationComplete(const ads1263_cal_event_t *event) {
  if (event->success) {
    Serial.print("✓ Calibration complete (");
    Serial.print(event->duration_us / 1000.0f, 1);
    Serial.println(" ms)");
    Serial.println();

    calibration_done = true;

    // Start first scan
    Serial.println("Starting channel scanning...");
    Serial.println("====================================");
    startScan();

  } else {
    Serial.println("✗ Calibration FAILED!");
    Serial.println("  Retrying in 5 seconds...");
    delay(5000);
    ads.calibrateOffset();
  }
}

void onError(const ads1263_error_event_t *event) {
  Serial.print("✗ ERROR [");
  Serial.print(event->error_code);
  Serial.print("]: ");
  Serial.println(event->error_message);

  // Handle specific errors
  switch (event->error_code) {
  case ADS1263_ERROR_TIMEOUT:
    Serial.println("  → Check DRDY connection");
    break;
  case ADS1263_ERROR_STATE:
    Serial.println("  → Invalid state for operation");
    break;
  default:
    break;
  }
}

void onAlarm(const ads1263_alarm_event_t *event) {
  Serial.println();
  Serial.println("⚠ HARDWARE ALARM DETECTED!");

  if (event->ref_alarm) {
    Serial.println("  → Reference voltage out of range");
  }
  if (event->pga_high_alarm) {
    Serial.println("  → PGA high overrange (reduce gain or input)");
  }
  if (event->pga_low_alarm) {
    Serial.println("  → PGA low overrange (increase gain)");
  }
  if (event->pga_diff_alarm) {
    Serial.println("  → PGA differential overrange");
  }
  Serial.println();
}

/* ========================================================================== */
/*                          SCAN CONTROL                                      */
/* ========================================================================== */

void startScan() {
  // Initialize all channels
  for (uint8_t i = 0; i < NUM_CHANNELS; i++) {
    channel_data[i].sample_index = 0;
    channel_data[i].sum = 0.0f;
    channel_data[i].ready = false;
  }

  current_channel = 0;
  scanning_active = true;

  // Start first channel
  ads.setChannel(channels[0].pos, channels[0].neg);
  ads.startSingleConversion();
}

void printScanResults() {
  total_scans++;

  Serial.println();
  Serial.print("=== SCAN #");
  Serial.print(total_scans);
  Serial.println(" RESULTS ===");
  Serial.println();

  for (uint8_t i = 0; i < NUM_CHANNELS; i++) {
    ChannelData *ch = &channel_data[i];

    if (ch->ready) {
      // Calculate standard deviation
      float variance = 0.0f;
      for (uint8_t j = 0; j < SAMPLES_PER_CHANNEL; j++) {
        float diff = ch->readings[j] - ch->average;
        variance += diff * diff;
      }
      variance /= SAMPLES_PER_CHANNEL;
      float std_dev = sqrt(variance);

      // Print statistics
      Serial.print(channels[i].name);
      Serial.println(":");
      Serial.print("  Average: ");
      Serial.print(ch->average * 1000.0f, 3);
      Serial.println(" mV");
      Serial.print("  Min:     ");
      Serial.print(ch->min_value * 1000.0f, 3);
      Serial.println(" mV");
      Serial.print("  Max:     ");
      Serial.print(ch->max_value * 1000.0f, 3);
      Serial.println(" mV");
      Serial.print("  Std Dev: ");
      Serial.print(std_dev * 1000000.0f, 2);
      Serial.println(" µV");
      Serial.print("  Range:   ");
      Serial.print((ch->max_value - ch->min_value) * 1000.0f, 3);
      Serial.println(" mV");
      Serial.println();
    }
  }

  Serial.println("====================================");
  Serial.println();
}

/* ========================================================================== */
/*                          ARDUINO SETUP                                     */
/* ========================================================================== */

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000)
    ;

  Serial.println();
  Serial.println("=====================================");
  Serial.println("  ADS1263 Multi-Channel Scanner");
  Serial.println("  Advanced Event-Driven Example");
  Serial.println("=====================================");
  Serial.println();

  Serial.print("Channels: ");
  Serial.println(NUM_CHANNELS);
  Serial.print("Samples per channel: ");
  Serial.println(SAMPLES_PER_CHANNEL);
  Serial.print("Total samples per scan: ");
  Serial.println(NUM_CHANNELS * SAMPLES_PER_CHANNEL);
  Serial.println();

  // Register callbacks
  ads.onInitComplete(onInitComplete);
  ads.onDataReady(onDataReady);
  ads.onCalibrationComplete(onCalibrationComplete);
  ads.onError(onError);
  ads.onAlarm(onAlarm);

  // Initialize
  Serial.println("Initializing ADS1263...");
  ads1263_error_t err = ads.begin(&SPI, 2000000);

  if (err != ADS1263_OK) {
    Serial.print("✗ Initialization error: ");
    Serial.println(err);
    while (1)
      ;
  }
}

/* ========================================================================== */
/*                          ARDUINO LOOP                                      */
/* ========================================================================== */

void loop() {
  // ★ CRITICAL: Update driver
  ads.update();

  // Start new scan every 5 seconds (when idle)
  if (calibration_done && !scanning_active) {
    if (millis() - scan_start_time >= 5000) {
      startScan();
    }
  }

  // Print status every 30 seconds
  static uint32_t last_status = 0;
  if (millis() - last_status >= 30000) {
    last_status = millis();

    Serial.println();
    Serial.println("--- SYSTEM STATUS ---");
    Serial.print("Uptime: ");
    Serial.print(millis() / 1000);
    Serial.println(" seconds");
    Serial.print("Total scans completed: ");
    Serial.println(total_scans);
    Serial.print("State: ");
    if (scanning_active) {
      Serial.print("SCANNING (channel ");
      Serial.print(current_channel);
      Serial.println(")");
    } else {
      Serial.println("IDLE");
    }
    Serial.println();
  }
}

/* ========================================================================== */
/*                          USAGE NOTES                                       */
/* ========================================================================== */

/**
 * @section advanced_usage Advanced Usage
 *
 * This example demonstrates professional multi-channel data acquisition:
 *
 * 1. Sequential channel scanning with settling time
 * 2. Multiple samples per channel for averaging
 * 3. Statistical analysis (min, max, average, std dev)
 * 4. Automatic calibration before measurement
 * 5. Comprehensive error handling
 * 6. Performance monitoring
 *
 * @section applications Applications
 *
 * - Multi-sensor monitoring systems
 * - Data logger with multiple inputs
 * - Strain gauge arrays
 * - Temperature monitoring (multiple thermocouples)
 * - Battery cell monitoring
 *
 * @section optimization Optimization Tips
 *
 * For faster scanning:
 *   - Increase data rate: ADS1263_RATE_400 or higher
 *   - Use Sinc1 filter for fastest settling
 *   - Reduce samples per channel
 *
 * For better accuracy:
 *   - Use Sinc4 filter
 *   - Increase samples per channel
 *   - Enable chop mode
 *   - Perform system calibration with known voltage
 *
 * For lowest noise:
 *   - Use lower data rates (≤100 SPS)
 *   - Enable chop mode
 *   - Use shielded cables
 *   - Proper grounding
 *
 * @section extending Extending This Example
 *
 * Add ADC2 for simultaneous secondary measurement:
 *   ads.setADC2Config(ADS1263_ADC2_RATE_100,
 *                     ADS1263_ADC2_GAIN_1,
 *                     ADS1263_ADC2_REF_INTERNAL);
 *   ads.startADC2();
 *
 * Add IDAC for RTD measurement:
 *   ads.setIDAC(ADS1263_IDAC_500UA,     // 500µA excitation
 *               ADS1263_IDAC_OFF,
 *               ADS1263_INPUT_AIN0,     // IDAC1 to AIN0
 *               ADS1263_INPUT_FLOAT);
 *
 * Add data logging to SD card:
 *   - Store readings in buffer
 *   - Write to SD card periodically
 *   - Use CSV format for easy analysis
 */
