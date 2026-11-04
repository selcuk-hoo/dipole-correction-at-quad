/**
 * @file basic_reading.ino
 * @brief ADS1263 Basic Reading Example
 * @version 3.0.0
 * 
 * @details Simple example demonstrating:
 *  - Device initialization
 *  - Continuous reading
 *  - Event-driven callbacks
 *  - Voltage conversion
 * 
 * @hardware
 *  - RP2350 Pico (or compatible)
 *  - ADS1263 module
 *  - Connections:
 *    - CS   → GPIO 10
 *    - DRDY → GPIO 9
 *    - RST  → GPIO 8
 *    - MOSI → GPIO 19 (SPI0)
 *    - MISO → GPIO 16 (SPI0)
 *    - SCK  → GPIO 18 (SPI0)
 * 
 * @author Production-Ready Implementation
 */

#include <ads1263.h>

// Pin definitions
#define ADS_CS_PIN      10
#define ADS_DRDY_PIN    9
#define ADS_RST_PIN     8

// Create ADS1263 instance
ADS1263 ads(ADS_CS_PIN, ADS_DRDY_PIN, ADS_RST_PIN);

// Data storage
volatile float current_voltage = 0.0f;
volatile bool new_data_available = false;
volatile uint32_t sample_count = 0;

/* ========================================================================== */
/*                          CALLBACK FUNCTIONS                                */
/* ========================================================================== */

/**
 * @brief Called when device initialization completes
 */
void onInitComplete(const ads1263_init_event_t* event) {
    if (event->success) {
        Serial.println("✓ ADS1263 initialized successfully!");
        Serial.print("  Device ID: 0x");
        Serial.println(event->device_id, HEX);
        Serial.print("  Init time: ");
        Serial.print(event->duration_us / 1000.0f, 2);
        Serial.println(" ms");
        Serial.println();
        
        // Configure ADC
        Serial.println("Configuring ADC...");
        ads.setGain(ADS1263_GAIN_1);              // Gain = 1 (±2.5V range)
        ads.setDataRate(ADS1263_RATE_100);        // 100 SPS
        ads.setFilter(ADS1263_FILTER_SINC3);      // Sinc3 filter
        ads.setChannel(ADS1263_INPUT_AIN0,        // AIN0 - AIN1 differential
                       ADS1263_INPUT_AIN1);
        
        // Start continuous conversions
        Serial.println("Starting continuous conversions...");
        ads.startContinuous();
        Serial.println();
    } else {
        Serial.println("✗ ADS1263 initialization FAILED!");
    }
}

/**
 * @brief Called when new ADC data is ready
 * @warning Keep this function SHORT! No blocking calls!
 */
void onDataReady(const ads1263_data_event_t* event) {
    // Store data for processing in loop()
    current_voltage = event->voltage;
    new_data_available = true;
    sample_count++;
    
    // Check for alarms (optional)
    if (event->status.ref_alarm) {
        Serial.println("⚠ Reference voltage alarm!");
    }
    if (event->status.pga_high || event->status.pga_low) {
        Serial.println("⚠ PGA overrange!");
    }
}

/**
 * @brief Called when an error occurs
 */
void onError(const ads1263_error_event_t* event) {
    Serial.print("✗ ERROR [");
    Serial.print(event->error_code);
    Serial.print("]: ");
    Serial.println(event->error_message);
}

/* ========================================================================== */
/*                          ARDUINO SETUP                                     */
/* ========================================================================== */

void setup() {
    // Initialize Serial
    Serial.begin(115200);
    while (!Serial && millis() < 3000); // Wait up to 3 seconds
    
    Serial.println();
    Serial.println("=====================================");
    Serial.println("  ADS1263 Basic Reading Example");
    Serial.println("  Event-Driven Non-Blocking Driver");
    Serial.println("=====================================");
    Serial.println();
    
    // Register event callbacks
    ads.onInitComplete(onInitComplete);
    ads.onDataReady(onDataReady);
    ads.onError(onError);
    
    // Initialize ADS1263 (non-blocking)
    Serial.println("Initializing ADS1263...");
    ads1263_error_t err = ads.begin(&SPI, 2000000); // 2 MHz SPI
    
    if (err != ADS1263_OK) {
        Serial.print("✗ Failed to start initialization: ");
        Serial.println(err);
        while (1); // Halt
    }
    
    Serial.println("Initialization started (waiting for callback)...");
    Serial.println();
}

/* ========================================================================== */
/*                          ARDUINO LOOP                                      */
/* ========================================================================== */

void loop() {
    // ★ CRITICAL: Must call update() regularly!
    ads.update();
    
    // Process new data when available
    if (new_data_available) {
        new_data_available = false;
        
        // Print voltage
        Serial.print("Voltage: ");
        Serial.print(current_voltage, 6);
        Serial.print(" V");
        
        // Print sample count
        Serial.print("  (Sample #");
        Serial.print(sample_count);
        Serial.println(")");
    }
    
    // Your other non-blocking code can go here
    // The ADC will continue sampling in the background
    
    // Example: Print statistics every 10 seconds
    static uint32_t last_stats_time = 0;
    if (millis() - last_stats_time >= 10000) {
        last_stats_time = millis();
        
        Serial.println();
        Serial.println("--- Statistics (10 seconds) ---");
        Serial.print("Total samples: ");
        Serial.println(sample_count);
        Serial.print("Sample rate: ");
        Serial.print(sample_count / 10.0f, 1);
        Serial.println(" SPS");
        Serial.println();
    }
}

/* ========================================================================== */
/*                          USAGE NOTES                                       */
/* ========================================================================== */

/**
 * @section usage Usage Instructions
 * 
 * 1. Connect ADS1263 to RP2350:
 *    - CS   → GPIO 10
 *    - DRDY → GPIO 9
 *    - RST  → GPIO 8
 *    - Connect SPI pins (MOSI, MISO, SCK)
 *    - Connect power (AVDD, AVSS, DVDD)
 * 
 * 2. Connect signal to measure:
 *    - Differential: AIN0 (+) and AIN1 (-)
 *    - Range: ±2.5V (with Gain=1 and internal 2.5V reference)
 * 
 * 3. Upload sketch and open Serial Monitor at 115200 baud
 * 
 * 4. You should see:
 *    - Initialization messages
 *    - Continuous voltage readings at 100 SPS
 *    - Statistics every 10 seconds
 * 
 * @section troubleshooting Troubleshooting
 * 
 * Problem: "Initialization FAILED"
 * Solution: Check SPI connections and power supply
 * 
 * Problem: No data readings
 * Solution: Ensure update() is being called in loop()
 * 
 * Problem: Unstable readings
 * Solution: Check reference voltage, try lower sample rate, enable chop mode
 * 
 * @section modifications Modifications
 * 
 * To change measurement range:
 *   ads.setGain(ADS1263_GAIN_16);  // For smaller signals (±156mV range)
 * 
 * To change sample rate:
 *   ads.setDataRate(ADS1263_RATE_1200);  // For faster sampling
 * 
 * To use single-ended input:
 *   ads.setChannel(ADS1263_INPUT_AIN0, ADS1263_INPUT_AINCOM);
 * 
 * To reduce noise:
 *   ads.setFilter(ADS1263_FILTER_SINC4);  // Better rejection
 *   ads.setChopMode(ADS1263_CHOP_INPUT);  // Enable chopping
 */
