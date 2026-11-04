/**
 * @file ads1263_defs.h
 * @brief ADS1263 Register and Bit Definitions
 * @version 3.2.1 - FIXED
 * @note FIXES: Removed IDAC macro definitions that conflicted with ads1263_types.h enums.
 */

#ifndef ADS1263_DEFS_H
#define ADS1263_DEFS_H

#include <stdint.h>

/* ========================================================================== */
/* REGISTER MAP                                    */
/* ========================================================================== */
/* Datasheet Table 9-34, p.88 */

#define ADS1263_REG_ID          0x00    ///< Device ID (Read-only)
#define ADS1263_REG_POWER       0x01    ///< Power control
#define ADS1263_REG_INTERFACE   0x02    ///< Interface format
#define ADS1263_REG_MODE0       0x03    ///< ADC1 Mode 0
#define ADS1263_REG_MODE1       0x04    ///< ADC1 Mode 1
#define ADS1263_REG_MODE2       0x05    ///< ADC1 Mode 2
#define ADS1263_REG_INPMUX      0x06    ///< ADC1 Input multiplexer
#define ADS1263_REG_OFCAL0      0x07    ///< ADC1 Offset calibration LSB
#define ADS1263_REG_OFCAL1      0x08    ///< ADC1 Offset calibration MID
#define ADS1263_REG_OFCAL2      0x09    ///< ADC1 Offset calibration MSB
#define ADS1263_REG_FSCAL0      0x0A    ///< ADC1 Full-scale calibration LSB
#define ADS1263_REG_FSCAL1      0x0B    ///< ADC1 Full-scale calibration MID
#define ADS1263_REG_FSCAL2      0x0C    ///< ADC1 Full-scale calibration MSB
#define ADS1263_REG_IDACMUX     0x0D    ///< IDAC multiplexer
#define ADS1263_REG_IDACMAG     0x0E    ///< IDAC magnitude
#define ADS1263_REG_REFMUX      0x0F    ///< Reference multiplexer
#define ADS1263_REG_TDACP       0x10    ///< TDAC positive output
#define ADS1263_REG_TDACN       0x11    ///< TDAC negative output
#define ADS1263_REG_GPIOCON     0x12    ///< GPIO connection
#define ADS1263_REG_GPIODIR     0x13    ///< GPIO direction
#define ADS1263_REG_GPIODAT     0x14    ///< GPIO data
#define ADS1263_REG_ADC2CFG     0x15    ///< ADC2 configuration
#define ADS1263_REG_ADC2MUX     0x16    ///< ADC2 input multiplexer
#define ADS1263_REG_ADC2OFC0    0x17    ///< ADC2 Offset calibration LSB
#define ADS1263_REG_ADC2OFC1    0x18    ///< ADC2 Offset calibration MSB
#define ADS1263_REG_ADC2FSC0    0x19    ///< ADC2 Full-scale calibration LSB
#define ADS1263_REG_ADC2FSC1    0x1A    ///< ADC2 Full-scale calibration MSB

/* ========================================================================== */
/* COMMANDS                                        */
/* ========================================================================== */
/* Datasheet Table 9-33, p.85 */

#define ADS1263_CMD_NOP         0x00    ///< No operation
#define ADS1263_CMD_RESET       0x06    ///< Reset device
#define ADS1263_CMD_START1      0x08    ///< Start ADC1 conversions
#define ADS1263_CMD_STOP1       0x0A    ///< Stop ADC1 conversions
#define ADS1263_CMD_START2      0x0C    ///< Start ADC2 conversions
#define ADS1263_CMD_STOP2       0x0E    ///< Stop ADC2 conversions
#define ADS1263_CMD_RDATA1      0x12    ///< Read ADC1 data
#define ADS1263_CMD_RDATA2      0x14    ///< Read ADC2 data
#define ADS1263_CMD_SYOCAL1     0x16    ///< ADC1 system offset calibration
#define ADS1263_CMD_SYGCAL1     0x17    ///< ADC1 system gain calibration
#define ADS1263_CMD_SFOCAL1     0x19    ///< ADC1 self offset calibration
#define ADS1263_CMD_SYOCAL2     0x1B    ///< ADC2 system offset calibration
#define ADS1263_CMD_SYGCAL2     0x1C    ///< ADC2 system gain calibration
#define ADS1263_CMD_SFOCAL2     0x1E    ///< ADC2 self offset calibration
#define ADS1263_CMD_RREG        0x20    ///< Read register (OR with address)
#define ADS1263_CMD_WREG        0x40    ///< Write register (OR with address)

/* ========================================================================== */
/* ID REGISTER (0x00) - READ ONLY                        */
/* ========================================================================== */
/* Datasheet Table 9-35, p.89 */

#define ADS1263_ID_DEV_MASK     0xE0    ///< Device ID mask [7:5]
#define ADS1263_ID_ADS1262      0x00    ///< Device ID for ADS1262 (DEV_ID = 000)
#define ADS1263_ID_ADS1263      0x20    ///< Device ID for ADS1263 (DEV_ID = 001)
#define ADS1263_ID_REV_MASK     0x1F    ///< Revision ID mask [4:0]

/* ========================================================================== */
/* POWER REGISTER (0x01) [reset = 11h]                   */
/* ========================================================================== */
/* Datasheet Table 9-36, p.89 */

#define ADS1263_POWER_RESET     0x10    ///< Bit 4: Reset indicator (1=reset occurred)
#define ADS1263_POWER_VBIAS     0x02    ///< Bit 1: VBIAS enable (1=enabled)
#define ADS1263_POWER_INTREF    0x01    ///< Bit 0: Internal reference (1=always on)
#define ADS1263_POWER_DEFAULT   0x11    ///< Default value after reset

/* ========================================================================== */
/* INTERFACE REGISTER (0x02) [reset = 05h]                */
/* ========================================================================== */
/* Datasheet Table 9-37, p.90 */

#define ADS1263_INTERFACE_TIMEOUT   0x08    ///< Bit 3: Timeout enable (1=enabled)
#define ADS1263_INTERFACE_STATUS    0x04    ///< Bit 2: Status byte enable (1=enabled)
#define ADS1263_INTERFACE_CRC_MASK  0x03    ///< CRC mode bits [1:0]
#define ADS1263_INTERFACE_CRC_OFF   0x00    ///< CRC disabled
#define ADS1263_INTERFACE_CRC_CSUM  0x01    ///< Checksum mode
#define ADS1263_INTERFACE_CRC_CRC   0x02    ///< CRC mode
#define ADS1263_INTERFACE_DEFAULT   0x05    ///< Default value (STATUS=1, CRC=01)

/* ========================================================================== */
/* MODE0 REGISTER (0x03) [reset = 00h]                   */
/* ========================================================================== */
/* Datasheet Table 9-38, p.91 */

#define ADS1263_MODE0_REFREV        0x80    ///< Bit 7: Reference reverse (1=reversed)

#define ADS1263_MODE0_RUNMODE_MASK  0x40    ///< Run mode bit [6]
#define ADS1263_MODE0_RUNMODE_CONT  0x00    ///< Continuous conversion
#define ADS1263_MODE0_RUNMODE_PULSE 0x40    ///< Pulse conversion (one-shot)

#define ADS1263_MODE0_CHOP_MASK     0x30    ///< Chop mode bits [5:4]
#define ADS1263_MODE0_CHOP_OFF      0x00    ///< Chop disabled
#define ADS1263_MODE0_CHOP_INPUT    0x10    ///< Input chop enabled
#define ADS1263_MODE0_CHOP_IDAC     0x20    ///< IDAC rotation enabled
#define ADS1263_MODE0_CHOP_BOTH     0x30    ///< Input chop + IDAC rotation

#define ADS1263_MODE0_DELAY_MASK    0x0F    ///< Conversion delay bits [3:0]
#define ADS1263_MODE0_DELAY_NONE    0x00    ///< No delay
#define ADS1263_MODE0_DELAY_8p7US   0x01    ///< 8.7 µs
#define ADS1263_MODE0_DELAY_17US    0x02    ///< 17 µs
#define ADS1263_MODE0_DELAY_35US    0x03    ///< 35 µs
#define ADS1263_MODE0_DELAY_69US    0x04    ///< 69 µs
#define ADS1263_MODE0_DELAY_139US   0x05    ///< 139 µs
#define ADS1263_MODE0_DELAY_278US   0x06    ///< 278 µs
#define ADS1263_MODE0_DELAY_555US   0x07    ///< 555 µs
#define ADS1263_MODE0_DELAY_1p1MS   0x08    ///< 1.1 ms
#define ADS1263_MODE0_DELAY_2p2MS   0x09    ///< 2.2 ms
#define ADS1263_MODE0_DELAY_4p4MS   0x0A    ///< 4.4 ms
#define ADS1263_MODE0_DELAY_8p8MS   0x0B    ///< 8.8 ms

/* ========================================================================== */
/* MODE1 REGISTER (0x04) [reset = 80h]                   */
/* ========================================================================== */
/* Datasheet Table 9-39, p.92 */

#define ADS1263_MODE1_FILTER_MASK   0xE0    ///< Filter bits [7:5]
#define ADS1263_MODE1_FILTER_SINC1  0x00    ///< Sinc1 filter
#define ADS1263_MODE1_FILTER_SINC2  0x20    ///< Sinc2 filter
#define ADS1263_MODE1_FILTER_SINC3  0x40    ///< Sinc3 filter
#define ADS1263_MODE1_FILTER_SINC4  0x60    ///< Sinc4 filter
#define ADS1263_MODE1_FILTER_FIR    0x80    ///< FIR filter (default)

#define ADS1263_MODE1_SBADC         0x10    ///< Bit 4: Sensor bias ADC connection
#define ADS1263_MODE1_SBPOL         0x08    ///< Bit 3: Sensor bias polarity

#define ADS1263_MODE1_SBMAG_MASK    0x07    ///< Sensor bias magnitude bits [2:0]
#define ADS1263_MODE1_SBMAG_NONE    0x00    ///< No sensor bias
#define ADS1263_MODE1_SBMAG_0p5UA   0x01    ///< 0.5 µA
#define ADS1263_MODE1_SBMAG_2UA     0x02    ///< 2 µA
#define ADS1263_MODE1_SBMAG_10UA    0x03    ///< 10 µA
#define ADS1263_MODE1_SBMAG_50UA    0x04    ///< 50 µA
#define ADS1263_MODE1_SBMAG_200UA   0x05    ///< 200 µA
#define ADS1263_MODE1_SBMAG_10MOHM  0x06    ///< 10 MΩ resistor

#define ADS1263_MODE1_DEFAULT       0x80    ///< Default value (FIR filter)

/* ========================================================================== */
/* MODE2 REGISTER (0x05) [reset = 04h]                   */
/* ========================================================================== */
/* Datasheet Table 9-40, p.93 */

#define ADS1263_MODE2_BYPASS        0x80    ///< Bit 7: PGA bypass (1=bypassed)

#define ADS1263_MODE2_GAIN_MASK     0x70    ///< Gain bits [6:4]
#define ADS1263_MODE2_GAIN_1        0x00    ///< Gain = 1
#define ADS1263_MODE2_GAIN_2        0x10    ///< Gain = 2
#define ADS1263_MODE2_GAIN_4        0x20    ///< Gain = 4
#define ADS1263_MODE2_GAIN_8        0x30    ///< Gain = 8
#define ADS1263_MODE2_GAIN_16       0x40    ///< Gain = 16
#define ADS1263_MODE2_GAIN_32       0x50    ///< Gain = 32

#define ADS1263_MODE2_DR_MASK       0x0F    ///< Data rate bits [3:0]
#define ADS1263_MODE2_DR_2_5        0x00    ///< 2.5 SPS
#define ADS1263_MODE2_DR_5          0x01    ///< 5 SPS
#define ADS1263_MODE2_DR_10         0x02    ///< 10 SPS
#define ADS1263_MODE2_DR_16_6       0x03    ///< 16.6 SPS
#define ADS1263_MODE2_DR_20         0x04    ///< 20 SPS (default)
#define ADS1263_MODE2_DR_50         0x05    ///< 50 SPS
#define ADS1263_MODE2_DR_60         0x06    ///< 60 SPS
#define ADS1263_MODE2_DR_100        0x07    ///< 100 SPS
#define ADS1263_MODE2_DR_400        0x08    ///< 400 SPS
#define ADS1263_MODE2_DR_1200       0x09    ///< 1200 SPS
#define ADS1263_MODE2_DR_2400       0x0A    ///< 2400 SPS
#define ADS1263_MODE2_DR_4800       0x0B    ///< 4800 SPS
#define ADS1263_MODE2_DR_7200       0x0C    ///< 7200 SPS
#define ADS1263_MODE2_DR_14400      0x0D    ///< 14400 SPS (Sinc1 only)
#define ADS1263_MODE2_DR_19200      0x0E    ///< 19200 SPS (Sinc1 only)
#define ADS1263_MODE2_DR_38400      0x0F    ///< 38400 SPS (Sinc1 only)

#define ADS1263_MODE2_DEFAULT       0x04    ///< Default value (Gain=1, DR=20 SPS)

/* ========================================================================== */
/* INPUT MUX REGISTER (0x06) [reset = 01h]                 */
/* ========================================================================== */
/* Datasheet Table 9-41, p.93-94 */

#define ADS1263_MUX_MUXP_MASK       0xF0    ///< Positive input bits [7:4]
#define ADS1263_MUX_MUXN_MASK       0x0F    ///< Negative input bits [3:0]

#define ADS1263_MUX_AIN0            0x00    ///< AIN0
#define ADS1263_MUX_AIN1            0x01    ///< AIN1
#define ADS1263_MUX_AIN2            0x02    ///< AIN2
#define ADS1263_MUX_AIN3            0x03    ///< AIN3
#define ADS1263_MUX_AIN4            0x04    ///< AIN4
#define ADS1263_MUX_AIN5            0x05    ///< AIN5
#define ADS1263_MUX_AIN6            0x06    ///< AIN6
#define ADS1263_MUX_AIN7            0x07    ///< AIN7
#define ADS1263_MUX_AIN8            0x08    ///< AIN8
#define ADS1263_MUX_AIN9            0x09    ///< AIN9
#define ADS1263_MUX_AINCOM          0x0A    ///< AINCOM
#define ADS1263_MUX_TEMP_P          0x0B    ///< Temperature sensor monitor positive
#define ADS1263_MUX_AVDD_P          0x0C    ///< Analog power supply monitor positive
#define ADS1263_MUX_DVDD_P          0x0D    ///< Digital power supply monitor positive
#define ADS1263_MUX_TDAC_P          0x0E    ///< TDAC test signal positive
#define ADS1263_MUX_FLOAT           0x0F    ///< Float (open connection)

/* ========================================================================== */
/* IDAC REGISTERS (0x0D, 0x0E)                            */
/* ========================================================================== */
/* Datasheet Table 9-44, 9-45, p.96-97 */

// IDACMUX (0x0D) - MUX2[7:4] | MUX1[3:0]
#define ADS1263_IDACMUX_MUX2_MASK   0xF0
#define ADS1263_IDACMUX_MUX1_MASK   0x0F
#define ADS1263_IDACMUX_DEFAULT     0xBB    ///< Both disconnected (AINCOM)

// IDACMAG (0x0E) - MAG2[7:4] | MAG1[3:0]
#define ADS1263_IDACMAG_MAG2_MASK   0xF0
#define ADS1263_IDACMAG_MAG1_MASK   0x0F

/*
 * NOTE: The IDAC value definitions have been removed from here
 * because they are defined as an enum in ads1263_types.h.
 * Using #define here caused a name collision compiler error.
 */

/* ========================================================================== */
/* REFMUX REGISTER (0x0F) [reset = 00h]                   */
/* ========================================================================== */
/* Datasheet Table 9-46, p.98 */

#define ADS1263_REFMUX_RMUXP_MASK   0x38    ///< REFP mux bits [5:3]
#define ADS1263_REFMUX_RMUXN_MASK   0x07    ///< REFN mux bits [2:0]

#define ADS1263_REFMUX_RMUXP_INT    0x00    ///< Internal 2.5V reference
#define ADS1263_REFMUX_RMUXP_AIN0   0x08    ///< External AIN0
#define ADS1263_REFMUX_RMUXP_AIN2   0x10    ///< External AIN2
#define ADS1263_REFMUX_RMUXP_AIN4   0x18    ///< External AIN4
#define ADS1263_REFMUX_RMUXP_AVDD   0x20    ///< Internal AVDD

#define ADS1263_REFMUX_RMUXN_INT    0x00    ///< Internal 2.5V reference
#define ADS1263_REFMUX_RMUXN_AIN1   0x01    ///< External AIN1
#define ADS1263_REFMUX_RMUXN_AIN3   0x02    ///< External AIN3
#define ADS1263_REFMUX_RMUXN_AIN5   0x03    ///< External AIN5
#define ADS1263_REFMUX_RMUXN_AVSS   0x04    ///< Internal AVSS

/* ========================================================================== */
/* GPIO REGISTERS (0x12, 0x13, 0x14)                      */
/* ========================================================================== */
/* Datasheet Table 9-49, 9-50, 9-51, p.100-101 */
/* Note: ADS1263 has 8 GPIO pins (GPIO0-7) on AIN3-AIN9 and AINCOM */

#define ADS1263_GPIO_0              0x01    ///< GPIO 0 (AIN3)
#define ADS1263_GPIO_1              0x02    ///< GPIO 1 (AIN4)
#define ADS1263_GPIO_2              0x04    ///< GPIO 2 (AIN5)
#define ADS1263_GPIO_3              0x08    ///< GPIO 3 (AIN6)
#define ADS1263_GPIO_4              0x10    ///< GPIO 4 (AIN7)
#define ADS1263_GPIO_5              0x20    ///< GPIO 5 (AIN8)
#define ADS1263_GPIO_6              0x40    ///< GPIO 6 (AIN9)
#define ADS1263_GPIO_7              0x80    ///< GPIO 7 (AINCOM)

#define ADS1263_GPIO_ALL            0xFF    ///< All GPIO pins

// GPIOCON (0x12) - 1=GPIO function, 0=Analog input
// GPIODIR (0x13) - 1=Output, 0=Input
// GPIODAT (0x14) - Data value (read/write)

/* ========================================================================== */
/* ADC2CFG REGISTER (0x15) [reset = 00h]                  */
/* ========================================================================== */
/* Datasheet Table 9-52, p.104 */

#define ADS1263_ADC2CFG_DR2_MASK    0xC0    ///< ADC2 data rate [7:6]
#define ADS1263_ADC2CFG_DR2_10      0x00    ///< 10 SPS
#define ADS1263_ADC2CFG_DR2_100     0x40    ///< 100 SPS
#define ADS1263_ADC2CFG_DR2_400     0x80    ///< 400 SPS
#define ADS1263_ADC2CFG_DR2_800     0xC0    ///< 800 SPS

#define ADS1263_ADC2CFG_REF2_MASK   0x38    ///< ADC2 reference [5:3]
#define ADS1263_ADC2CFG_REF2_INT    0x00    ///< Internal 2.5V
#define ADS1263_ADC2CFG_REF2_AIN01  0x08    ///< External AIN0/AIN1
#define ADS1263_ADC2CFG_REF2_AIN23  0x10    ///< External AIN2/AIN3
#define ADS1263_ADC2CFG_REF2_AIN45  0x18    ///< External AIN4/AIN5
#define ADS1263_ADC2CFG_REF2_AVDD   0x20    ///< Internal VAVDD/VAVSS

#define ADS1263_ADC2CFG_GAIN2_MASK  0x07    ///< ADC2 gain [2:0]
#define ADS1263_ADC2CFG_GAIN2_1     0x00    ///< Gain = 1
#define ADS1263_ADC2CFG_GAIN2_2     0x01    ///< Gain = 2
#define ADS1263_ADC2CFG_GAIN2_4     0x02    ///< Gain = 4
#define ADS1263_ADC2CFG_GAIN2_8     0x03    ///< Gain = 8
#define ADS1263_ADC2CFG_GAIN2_16    0x04    ///< Gain = 16
#define ADS1263_ADC2CFG_GAIN2_32    0x05    ///< Gain = 32
#define ADS1263_ADC2CFG_GAIN2_64    0x06    ///< Gain = 64
#define ADS1263_ADC2CFG_GAIN2_128   0x07    ///< Gain = 128

/* ========================================================================== */
/* STATUS BYTE BIT DEFINITIONS                            */
/* ========================================================================== */
/* Datasheet Table 9-31, p.67 */

#define ADS1263_STATUS_ADC2_NEW     0x80    ///< Bit 7: ADC2 new data available
#define ADS1263_STATUS_ADC1_NEW     0x40    ///< Bit 6: ADC1 new data available
#define ADS1263_STATUS_EXTCLK       0x20    ///< Bit 5: External clock detected
#define ADS1263_STATUS_REF_ALM      0x10    ///< Bit 4: Reference alarm
#define ADS1263_STATUS_PGAL_ALM     0x08    ///< Bit 3: PGA output low alarm
#define ADS1263_STATUS_PGAH_ALM     0x04    ///< Bit 2: PGA output high alarm
#define ADS1263_STATUS_PGAD_ALM     0x02    ///< Bit 1: PGA differential alarm
#define ADS1263_STATUS_RESET        0x01    ///< Bit 0: Reset occurred

#define ADS1263_STATUS_ALARM_MASK   0x1E    ///< All alarm bits mask

/* ========================================================================== */
/* CHECKSUM/CRC COMPUTATION                               */
/* ========================================================================== */
/* Datasheet p.72 */

#define ADS1263_CRC_POLYNOMIAL      0x07    ///< CRC-8 polynomial (x^8 + x^2 + x + 1)
#define ADS1263_CRC_INIT            0x00    ///< CRC initial value

/* ========================================================================== */
/* TEMPERATURE SENSOR CONSTANTS                           */
/* ========================================================================== */
/* Datasheet p.43 */

#define ADS1263_TEMP_OFFSET_UV      122400.0f   ///< Temperature offset at 25°C (µV)
#define ADS1263_TEMP_SLOPE_UV_C     420.0f      ///< Temperature slope (µV/°C)
#define ADS1263_TEMP_OFFSET_C       25.0f       ///< Reference temperature (°C)

/* ========================================================================== */
/* INTERNAL REFERENCE                                     */
/* ========================================================================== */
/* Datasheet p.7 */

#define ADS1263_VREF_INTERNAL       2.5f        ///< Internal reference voltage (V)

/* ========================================================================== */
/* REGISTER DEFAULT VALUES                                */
/* ========================================================================== */
/* From Table 9-34 */

#define ADS1263_REG_POWER_DEFAULT       0x11
#define ADS1263_REG_INTERFACE_DEFAULT   0x05
#define ADS1263_REG_MODE0_DEFAULT       0x00
#define ADS1263_REG_MODE1_DEFAULT       0x80
#define ADS1263_REG_MODE2_DEFAULT       0x04
#define ADS1263_REG_INPMUX_DEFAULT      0x01
#define ADS1263_REG_REFMUX_DEFAULT      0x00
#define ADS1263_REG_IDACMUX_DEFAULT     0xBB
#define ADS1263_REG_IDACMAG_DEFAULT     0x00
#define ADS1263_REG_FSCAL2_DEFAULT      0x40
#define ADS1263_REG_ADC2CFG_DEFAULT     0x00
#define ADS1263_REG_ADC2MUX_DEFAULT     0x01
#define ADS1263_REG_ADC2FSC1_DEFAULT    0x40

#endif // ADS1263_DEFS_H