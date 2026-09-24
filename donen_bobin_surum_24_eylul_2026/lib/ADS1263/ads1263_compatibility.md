# ADS1263 Setting Compatibility Matrix

> [!CAUTION]
> The driver currently has **NO validation** on filter↔rate combos. When you set an incompatible pair, the ADS1263 silently ignores the filter setting. The config report reads back the **cached** value (not the actual hardware state), so the host thinks the filter was applied when it wasn't.

## Filter × Data Rate Compatibility

Source: ADS1263 Datasheet SBAS661C, Section 9.3.8, Table 18

| Rate Index | Data Rate | Sinc1 (0) | Sinc2 (1) | Sinc3 (2) | Sinc4 (3) | FIR (4) |
|:----------:|:---------:|:---------:|:---------:|:---------:|:---------:|:-------:|
| 0          | 2.5 SPS   | ✅        | ✅        | ✅        | ✅        | ✅      |
| 1          | 5 SPS     | ✅        | ✅        | ✅        | ✅        | ✅      |
| 2          | 10 SPS    | ✅        | ✅        | ✅        | ✅        | ✅      |
| 3          | 16.6 SPS  | ✅        | ✅        | ✅        | ✅        | ✅      |
| 4          | 20 SPS    | ✅        | ✅        | ✅        | ✅        | ✅      |
| 5          | 50 SPS    | ✅        | ✅        | ✅        | ✅        | ❌      |
| 6          | 60 SPS    | ✅        | ✅        | ✅        | ✅        | ❌      |
| 7          | 100 SPS   | ✅        | ✅        | ✅        | ✅        | ❌      |
| 8          | 400 SPS   | ✅        | ✅        | ✅        | ✅        | ❌      |
| 9          | 1200 SPS  | ✅        | ✅        | ✅        | ✅        | ❌      |
| 10         | 2400 SPS  | ✅        | ✅        | ✅        | ✅        | ❌      |
| 11         | 4800 SPS  | ✅        | ✅        | ✅        | ✅        | ❌      |
| 12         | 7200 SPS  | ✅        | ✅        | ✅        | ✅        | ❌      |
| 13         | 14400 SPS | ⚡ forced | ❌        | ❌        | ❌        | ❌      |
| 14         | 19200 SPS | ⚡ forced | ❌        | ❌        | ❌        | ❌      |
| 15         | 38400 SPS | ⚡ forced | ❌        | ❌        | ❌        | ❌      |

> [!IMPORTANT]
> **⚡ forced** = At rates 13–15 (14400/19200/38400 SPS), the second-stage digital filter is **hardware-bypassed**. The FILTER bits in MODE1 register are **completely ignored**. The ADC uses its first-stage Sinc5 filter only. Writing any filter value has no effect.

### Summary Rules
- **FIR (4)**: Only valid at rates 0–4 (≤20 SPS)
- **Sinc2/3/4 (1–3)**: Valid at rates 0–12 (≤7200 SPS)
- **Sinc1 (0)**: Valid at rates 0–12 (≤7200 SPS). At rates 13–15, the hardware forces Sinc5 regardless.

---

## Chop Mode × Conversion Mode

Source: Datasheet Section 9.3.6

| Chop Mode    | Continuous (0) | Pulse (1) |
|:-------------|:--------------:|:---------:|
| Off (0)      | ✅             | ✅        |
| Input (1)    | ✅             | ❌        |
| IDAC (2)     | ✅             | ❌        |
| Both (3)     | ✅             | ❌        |

> [!NOTE]
> This constraint **IS** already validated in the driver: [ads1263.cpp:setConversionMode()](file:///c:/Users/Xil/Desktop/MGF1-fixed/MGF1-fixed/MGFv0.4/lib/ADS1263/ads1263.cpp#L287-L299) returns `ADS1263_ERROR_CONFIG` when attempting Pulse mode with Chop enabled.

---

## PGA Gain × PGA Bypass

Source: Datasheet Table 9-40

| PGA Bypass | Gain Setting | Actual Gain |
|:-----------|:-------------|:------------|
| Off (0)    | 0–5          | 1/2/4/8/16/32 (as set) |
| On (1)     | _any_        | **Always 1** (gain register ignored) |

> [!WARNING]
> When PGA bypass = 1, the gain setting in MODE2 is ignored. The PGA is physically disconnected from the signal path. The driver's voltage conversion uses `_pga_bypass ? 1.0f : GAIN_TABLE[_gain]`, so calculations remain correct. However the config report will still show the cached gain value — misleading if bypass is on.

---

## Conversion Delay Restrictions

Source: Datasheet Table 9-38

| Delay Index | Delay Value | Valid with All Modes? |
|:-----------:|:------------|:---------------------:|
| 0           | No delay    | ✅ |
| 1           | 8.7 µs      | ✅ |
| 2           | 17 µs       | ✅ |
| 3           | 35 µs       | ✅ |
| 4           | 69 µs       | ✅ |
| 5           | 139 µs      | ✅ |
| 6           | 278 µs      | ✅ |
| 7           | 555 µs      | ✅ |
| 8           | 1.1 ms      | ✅ |
| 9           | 2.2 ms      | ✅ |
| 10          | 4.4 ms      | ✅ |
| 11          | 8.8 ms      | ✅ |

No restrictions — conversion delay is independent of other settings. But delays longer than the sample period at fast rates will obviously reduce effective throughput.

---

## Your Default Configuration

```
Rate   = 12 (7200 SPS)
Filter = 0  (Sinc1)
```

This is valid ✅. But if the host tries to set Filter=4 (FIR) while at 7200 SPS, the ADS1263 will silently ignore it.

---

## The Bug

In [rotor.cpp](file:///c:/Users/Xil/Desktop/MGF1-fixed/MGF1-fixed/MGFv0.4/src/rotor.cpp) `CMD_SET_FILTER` (line ~266) and `CMD_SET_RATE` (line ~251):

1. Neither command validates whether the new filter is compatible with the current rate (or vice versa)
2. The ADS1263 driver's [setFilter()](file:///c:/Users/Xil/Desktop/MGF1-fixed/MGF1-fixed/MGFv0.4/lib/ADS1263/ads1263.cpp#L242-L247) and [setDataRate()](file:///c:/Users/Xil/Desktop/MGF1-fixed/MGF1-fixed/MGFv0.4/lib/ADS1263/ads1263.cpp#L235-L240) have no cross-validation either
3. The config report reads from cache (`_filter`, `_rate`), not from hardware, so the host sees the wrong state
4. The ADS1263 hardware silently ignores incompatible filter writes — no error flag, no interrupt, no indication

### Fix needed
Validate filter↔rate compatibility at command time and return `ACK_INVALID_PARAM` if the combination is not allowed. When changing rate, auto-fallback the filter if needed.
