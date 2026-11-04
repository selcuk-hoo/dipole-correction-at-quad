# ADS1263 Library Bug Fixes - Verification Report

## Cross-Check Against Datasheet SBAS661C (May 2021)

---

## ✅ FIX 1: INTERFACE Register STATUS Bit Position (CRITICAL)

**Original Bug:** `ADS1263_INTERFACE_STATUS = 0x20` (bit 5)

**Datasheet Reference:** Table 9-37, p.90
```
Bit 2: STATUS - Status Byte Enable (R/W, Reset=1)
```

**Fixed Value:** `ADS1263_INTERFACE_STATUS = 0x04` (bit 2)

**Impact:** Without this fix, status byte is never enabled, causing data read to return wrong bytes and corrupt all voltage readings.

**Verification:** ✅ CONFIRMED
- Datasheet Figure 9-60 shows: `[7:4]=RESERVED, [3]=TIMEOUT, [2]=STATUS, [1:0]=CRC`
- Reset value 0x05 = 0b00000101 = STATUS=1, CRC=01 ✓

---

## ✅ FIX 2: MODE0 CHOP Bit Position (HIGH)

**Original Bug:** CHOP shifted by 3 bits → mask 0x18, bits [4:3]

**Datasheet Reference:** Table 9-38, p.91
```
Bits 5:4: CHOP[1:0] - Chop Mode Enable
  00: Input chop and IDAC rotation disabled
  01: Input chop enabled
  10: IDAC rotation enabled
  11: Input chop and IDAC rotation enabled
```

**Fixed Values:**
```c
#define ADS1263_MODE0_CHOP_MASK     0x30    // bits [5:4]
#define ADS1263_MODE0_CHOP_OFF      0x00    // 00 << 4
#define ADS1263_MODE0_CHOP_INPUT    0x10    // 01 << 4
#define ADS1263_MODE0_CHOP_IDAC     0x20    // 10 << 4
#define ADS1263_MODE0_CHOP_BOTH     0x30    // 11 << 4
```

**Verification:** ✅ CONFIRMED
- Datasheet Figure 9-61 shows: `[7]=REFREV, [6]=RUNMODE, [5:4]=CHOP, [3:0]=DELAY`

---

## ✅ FIX 3: MODE0 RUNMODE Bit Position (HIGH)

**Original Bug:** RUNMODE shifted by 5 bits → bit 5

**Datasheet Reference:** Table 9-38, p.91
```
Bit 6: RUNMODE - ADC Conversion Run Mode
  0: Continuous conversion (default)
  1: Pulse conversion (one shot)
```

**Fixed Values:**
```c
#define ADS1263_MODE0_RUNMODE_MASK  0x40    // bit [6]
#define ADS1263_MODE0_RUNMODE_CONT  0x00
#define ADS1263_MODE0_RUNMODE_PULSE 0x40
```

**Verification:** ✅ CONFIRMED

---

## ✅ FIX 4: MODE0 DELAY Mask (MEDIUM)

**Original Bug:** `ADS1263_MODE0_DELAY_MASK = 0x07` (3 bits), missing delay values >555µs

**Datasheet Reference:** Table 9-38, p.91
```
Bits 3:0: DELAY[3:0] - Conversion Delay (4 bits)
  0000-1011: Valid delay values up to 8.8ms
```

**Fixed Values:**
```c
#define ADS1263_MODE0_DELAY_MASK    0x0F    // bits [3:0]
#define ADS1263_MODE0_DELAY_1p1MS   0x08    // 1.1 ms (was missing)
#define ADS1263_MODE0_DELAY_2p2MS   0x09    // 2.2 ms (was missing)
#define ADS1263_MODE0_DELAY_4p4MS   0x0A    // 4.4 ms (was missing)
#define ADS1263_MODE0_DELAY_8p8MS   0x0B    // 8.8 ms (was missing)
```

**Verification:** ✅ CONFIRMED

---

## ✅ FIX 5: POWER Register Bit Positions (HIGH)

**Original Bug:** 
- `ADS1263_POWER_RESET = 0x01` (bit 0) - should be bit 4
- `ADS1263_POWER_INTREF = 0x04` (bit 2) - should be bit 0

**Datasheet Reference:** Table 9-36, p.89
```
Bit 4: RESET - Reset Indicator
Bit 1: VBIAS - Level Shift Voltage Enable  
Bit 0: INTREF - Internal Reference Enable
Reset value: 0x11 (RESET=1, INTREF=1)
```

**Fixed Values:**
```c
#define ADS1263_POWER_RESET     0x10    // Bit 4
#define ADS1263_POWER_VBIAS     0x02    // Bit 1
#define ADS1263_POWER_INTREF    0x01    // Bit 0
```

**Verification:** ✅ CONFIRMED
- Reset value 0x11 = 0b00010001 = RESET=1, INTREF=1 ✓

---

## ✅ FIX 6: Register Caching for Read-Modify-Write (HIGH)

**Original Bug:** Functions like setChopMode(), setFilter(), enableVBias() overwrote entire registers

**Example Problem:**
```c
// Original: This clears REFREV, RUNMODE, and DELAY bits!
return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE0, (mode << 3));
```

**Fix:** Added register cache variables and read-modify-write pattern:
```c
// Fixed: Preserves all other bits
_reg_mode0_cache = (_reg_mode0_cache & ~ADS1263_MODE0_CHOP_MASK) | (mode << 4);
enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE0, _reg_mode0_cache);
```

**Verification:** ✅ IMPLEMENTED
- All configuration functions now preserve other bits in shared registers

---

## ✅ FIX 7: ADC2 24-bit Sign Extension (HIGH)

**Original Bug:**
```c
int32_t raw = ((int32_t)buf[1] << 24) | ((int32_t)buf[2] << 16) | ((int32_t)buf[3] << 8);
raw >>= 8;  // Incorrect sign extension - uses arithmetic shift which is implementation-defined
```

**Datasheet Reference:** ADC2 is 24-bit (Table 9-52)

**Fixed Code:**
```c
int32_t raw = ((int32_t)buf[1] << 16) | ((int32_t)buf[2] << 8) | buf[3];
if (raw & 0x00800000) {
    raw |= 0xFF000000;  // Explicit sign extension for negative values
}
```

**Verification:** ✅ CONFIRMED
- Proper two's complement sign extension from 24-bit to 32-bit

---

## ✅ FIX 8: GPIO Pin Count (MEDIUM)

**Original Bug:** `if (pin > 3) return ADS1263_ERROR_RANGE;`

**Datasheet Reference:** Table 6-1, p.4-5 and Table 9-49, p.101
```
GPIO0 = AIN3,  GPIO1 = AIN4,  GPIO2 = AIN5,  GPIO3 = AIN6
GPIO4 = AIN7,  GPIO5 = AIN8,  GPIO6 = AIN9,  GPIO7 = AINCOM
```

**Fixed Code:** `if (pin > 7) return ADS1263_ERROR_RANGE;`

**Verification:** ✅ CONFIRMED
- ADS1263 has 8 GPIO pins (GPIO0-GPIO7)

---

## ✅ FIX 9: GPIO Register Caching (MEDIUM)

**Original Bug:** 
```c
// gpioPinMode clobbers other pins
enqueue(..., ADS1263_REG_GPIODIR, mask);  // Sets only one pin, clears others

// gpioWrite clobbers other pins  
uint8_t data = value ? mask : 0;  // Sets only one pin, clears others
```

**Fixed Code:**
```c
// gpioPinMode preserves other pins
if (mode == OUTPUT) {
    _reg_gpiodir_cache |= mask;
} else {
    _reg_gpiodir_cache &= ~mask;
}
enqueue(..., ADS1263_REG_GPIODIR, _reg_gpiodir_cache);

// gpioWrite preserves other pins
if (value) {
    _reg_gpiodat_cache |= mask;
} else {
    _reg_gpiodat_cache &= ~mask;
}
enqueue(..., ADS1263_REG_GPIODAT, _reg_gpiodat_cache);
```

**Verification:** ✅ IMPLEMENTED

---

## ✅ FIX 10: Static init_step Variable (MEDIUM)

**Original Bug:** `static uint8_t init_step = 0;` inside handleInitialization()

**Problem:** Static variable persists across reset() calls, causing initialization to start at wrong step after reset

**Fix:** Made `_init_step` a class member variable, reset to 0 in reset() function

**Verification:** ✅ IMPLEMENTED

---

## ✅ FIX 11: Temperature Sensor MUX Values (MEDIUM)

**Original Bug:** 
```c
ADS1263_INPUT_TEMP_P = 0x0B  // Correct
ADS1263_INPUT_TEMP_N = 0x0C  // WRONG - 0x0C is AVDD monitor!
```

**Datasheet Reference:** Section 9.3.4 and Table 9-41
```
For temperature sensor measurement:
- Set INPMUX to 0xBB (both P and N = 0x0B)
- 0x0B = Temperature sensor monitor (for both positive and negative)
- 0x0C = Analog power supply monitor (NOT temperature!)
```

**Fixed Values:**
```c
ADS1263_INPUT_TEMP_SENSOR   = 0x0B  // Use for both P and N
ADS1263_INPUT_AVDD_MONITOR  = 0x0C  // Analog supply (VAVDD-VAVSS)/4
ADS1263_INPUT_DVDD_MONITOR  = 0x0D  // Digital supply (VDVDD-VDGND)/4
```

**Fixed Temperature Reading:**
```c
// Correct: Set INPMUX to 0xBB per datasheet Section 9.3.4
enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_INPMUX, 0xBB);
```

**Verification:** ✅ CONFIRMED

---

## ✅ FIX 12: Checksum Calculation (MEDIUM)

**Original Bug:**
```c
return (sum & 0xFF) ^ 0x9B;  // WRONG - XOR instead of ADD
```

**Datasheet Reference:** Section 9.4.7.3.3.1, p.72
```
Checksum = lower 8 bits of (sum of data bytes + 9Bh)
Example: 12h + 34h + 56h + 78h + 9Bh = AFh
```

**Fixed Code:**
```c
uint16_t sum = 0x9B;  // Start with offset value
for (uint8_t i = 0; i < len; i++) {
    sum += data[i];
}
return (uint8_t)(sum & 0xFF);
```

**Verification:** ✅ CONFIRMED

---

## ✅ FIX 13: CRC Initial Value (LOW)

**Original Bug:** `uint8_t crc = 0xFF;` - Non-standard initial value

**Datasheet Reference:** Section 9.4.7.3.4 - CRC-8-ATM (HEC) polynomial

**Fixed Code:** `uint8_t crc = 0x00;` - Standard CRC-8-ATM initial value

**Verification:** ✅ IMPLEMENTED

---

## ✅ FIX 14: CRC/Checksum Validation (MEDIUM)

**Original Bug:** Code reads data with CRC but never validates it

**Fix:** Added validation in executeSPIDataRead() and executeADC2DataRead():
```c
if (_crc_enabled) {
    uint8_t received_crc = buf[5];
    if (!validateDataCRC(buf, 5, received_crc)) {
        dispatchError(ADS1263_ERROR_CRC, "Data CRC mismatch");
        return;
    }
}
```

**Verification:** ✅ IMPLEMENTED

---

## ✅ FIX 15: MODE1 SBMAG Mask Added (LOW)

**Original Bug:** No mask defined for SBMAG bits

**Datasheet Reference:** Table 9-39 shows SBMAG[2:0] at bits 2:0

**Fix:** Added `#define ADS1263_MODE1_SBMAG_MASK 0x07`

**Verification:** ✅ IMPLEMENTED

---

## Summary of All Files Modified

| File | Changes Made |
|------|--------------|
| `ads1263_defs.h` | Fixed STATUS bit (0x04), CHOP bits ([5:4]), RUNMODE bit ([6]), DELAY mask (0x0F), POWER bits, added GPIO 4-7, added SBMAG mask |
| `ads1263_types.h` | Fixed temperature/monitor MUX values (TEMP=0x0B, AVDD=0x0C, DVDD=0x0D, TDAC=0x0E) |
| `ads1263.h` | Added register cache variables, init_step member, CRC functions, settling time function |
| `ads1263.cpp` | Register caching for all config functions, proper bit operations, ADC2 sign extension, CRC validation, corrected checksum calculation, temperature sensor fix |

---

## Verification Checklist

- [x] INTERFACE STATUS bit = 0x04 (bit 2) per Table 9-37
- [x] MODE0 CHOP bits = [5:4] per Table 9-38  
- [x] MODE0 RUNMODE bit = [6] per Table 9-38
- [x] MODE0 DELAY bits = [3:0] with mask 0x0F per Table 9-38
- [x] POWER INTREF bit = [0] per Table 9-36
- [x] POWER VBIAS bit = [1] per Table 9-36
- [x] POWER RESET bit = [4] per Table 9-36
- [x] GPIO count = 8 (GPIO0-GPIO7) per Table 6-1 and Table 9-49
- [x] ADC2 = 24-bit with proper sign extension per Table 9-52
- [x] Temperature sensor = 0x0B for both P and N per Section 9.3.4
- [x] AVDD monitor = 0x0C per Table 9-41
- [x] Checksum = sum + 0x9B per Section 9.4.7.3.3.1
- [x] CRC polynomial = 0x07 per Section 9.4.7.3.4
- [x] All register writes use read-modify-write pattern
- [x] Static init_step changed to member variable
