"""
Analysis Engine for MGF Radar V2.
Provides FFT/Order analysis, envelope analysis (Hilbert), bearing defect
frequency calculator, TIR, and automatic peak detection with order labels.
"""

import numpy as np
from dataclasses import dataclass, field


@dataclass
class FFTPeak:
    """A detected peak in the FFT spectrum."""
    order: float
    magnitude: float
    label: str = ""   # e.g. "1X", "2X", "BPFO"


@dataclass
class BearingDefectFreqs:
    """Standard bearing defect frequencies as multiples of shaft speed."""
    bpfo: float = 0.0   # Ball Pass Frequency Outer
    bpfi: float = 0.0   # Ball Pass Frequency Inner
    bsf: float = 0.0    # Ball Spin Frequency
    ftf: float = 0.0    # Fundamental Train Frequency


class Analyzer:
    """Signal analysis toolkit for rotating machinery diagnostics."""

    def __init__(self):
        # Persistent windows cache (avoid re-allocation)
        # cache key: (window_type, length)
        self._window_cache: dict[tuple[str, int], np.ndarray] = {}

    def _get_window(self, n: int, window_type: str = "Hanning") -> np.ndarray:
        """Return a cached window of length n."""
        key = (window_type, n)
        if key not in self._window_cache:
            if window_type == "Hanning":
                self._window_cache[key] = np.hanning(n).astype(np.float32)
            elif window_type == "Hamming":
                self._window_cache[key] = np.hamming(n).astype(np.float32)
            elif window_type == "Blackman":
                self._window_cache[key] = np.blackman(n).astype(np.float32)
            else: # "Rectangular" / default
                self._window_cache[key] = np.ones(n, dtype=np.float32)
        return self._window_cache[key]

    # ------------------------------------------------------------------
    # FFT / Order Analysis
    # ------------------------------------------------------------------

    def perform_fft(self, adc_data: np.ndarray, sample_rate: float,
                    motor_speed_hz: float, window_type: str = "Hanning",
                    fft_size: int = -1, domain: str = "Order",
                    zero_pad_factor: int = 1,
                    num_averages: int = 1) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute FFT (Frequency or Order domain).

        Parameters
        ----------
        zero_pad_factor : int
            Multiply FFT length by this factor for interpolated frequency
            resolution. 1 = no padding (default). 2 or 4 recommended.
        num_averages : int
            If > 1, use Welch's method: split data into overlapping segments,
            FFT each, and average. Reduces variance at the cost of frequency
            resolution.

        Returns (x_vals, magnitudes) where x_vals represent frequency or orders.
        Magnitudes are RMS-scaled.
        """
        if len(adc_data) < 1024 or motor_speed_hz <= 0.01:
            return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

        if fft_size > 0 and len(adc_data) > fft_size:
            data = adc_data[-fft_size:].astype(np.float32)
        else:
            data = adc_data.astype(np.float32)

        # Welch's method: split into overlapping segments and average
        if num_averages > 1 and len(data) >= 2048:
            seg_len = len(data) // num_averages
            seg_len = max(seg_len, 1024)
            overlap = seg_len // 2
            step = seg_len - overlap

            mag_accum = None
            count = 0
            for start in range(0, len(data) - seg_len + 1, step):
                segment = data[start:start + seg_len].copy()
                segment -= np.mean(segment)
                window = self._get_window(seg_len, window_type)
                segment *= window

                n_fft = seg_len * max(1, zero_pad_factor)
                fft_result = np.abs(np.fft.rfft(segment, n=n_fft))
                window_sum = np.sum(window)
                if window_sum > 0:
                    seg_mag = (fft_result / window_sum) * 2.0
                else:
                    seg_mag = (fft_result / seg_len) * 2.0

                if mag_accum is None:
                    mag_accum = seg_mag
                else:
                    mag_accum += seg_mag
                count += 1
                if count >= num_averages * 2:  # Cap iterations
                    break

            if count > 0:
                mag = mag_accum / count
            else:
                mag = mag_accum

            freqs = np.fft.rfftfreq(seg_len * max(1, zero_pad_factor), d=1.0 / sample_rate)
        else:
            n = len(data)

            # Remove DC offset
            data -= np.mean(data)

            # Apply window
            window = self._get_window(n, window_type)
            data *= window

            # Compute FFT (with optional zero-padding)
            n_fft = n * max(1, zero_pad_factor)
            fft_result = np.abs(np.fft.rfft(data, n=n_fft))
            freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)

            # Normalize using coherent gain of the window
            window_sum = np.sum(window)
            if window_sum > 0:
                mag = (fft_result / window_sum) * 2.0
            else:
                mag = (fft_result / n) * 2.0

        # Convert to requested domain
        if domain == "Frequency":
            x_vals = freqs
        else:
            x_vals = freqs / motor_speed_hz

        # Floor at epsilon for log-safe plotting
        np.clip(mag, 1e-9, None, out=mag)

        return x_vals.astype(np.float32), mag.astype(np.float32)

    # ------------------------------------------------------------------
    # Host-side Digital Filter
    # ------------------------------------------------------------------

    @staticmethod
    def apply_digital_filter(data: np.ndarray, sample_rate: float,
                             cutoff_hz: float, filter_type: str = "lowpass",
                             order: int = 4) -> np.ndarray:
        """
        Apply a Butterworth digital filter to the signal.

        Parameters
        ----------
        data : input signal
        sample_rate : sampling rate in Hz
        cutoff_hz : cutoff frequency in Hz (or tuple for bandpass)
        filter_type : 'lowpass', 'highpass'
        order : filter order (default 4)

        Returns filtered signal.
        """
        from scipy.signal import butter, sosfilt
        nyq = sample_rate / 2.0
        if cutoff_hz >= nyq:
            cutoff_hz = nyq * 0.95
        wn = cutoff_hz / nyq
        sos = butter(order, wn, btype=filter_type, output='sos')
        return sosfilt(sos, data).astype(np.float32)

    @staticmethod
    def remove_dc(data: np.ndarray) -> np.ndarray:
        """Remove DC offset from signal."""
        return (data - np.mean(data)).astype(np.float32)

    # ------------------------------------------------------------------
    # Peak Detection
    # ------------------------------------------------------------------

    def detect_peaks(self, orders: np.ndarray, mag: np.ndarray,
                     threshold_db: float = -40.0,
                     max_peaks: int = 10,
                     min_order: float = 0.5,
                     max_order: float = 30.0,
                     bearing: BearingDefectFreqs | None = None,
                     motor_speed_hz: float = 1.0
                     ) -> list[FFTPeak]:
        """
        Detect spectral peaks and label them as harmonic orders or bearing defects.

        Parameters
        ----------
        orders : array of order values
        mag : array of magnitudes (linear)
        threshold_db : minimum dB above noise floor to consider a peak
        max_peaks : maximum number of peaks to return
        min_order, max_order : search range
        bearing : optional bearing defect frequencies to label
        motor_speed_hz : motor speed to scale frequency values to order for labeling

        Returns
        -------
        List of FFTPeak sorted by magnitude (descending).
        """
        if len(orders) < 16 or len(mag) < 16:
            return []

        # Limit to search range
        mask = (orders >= min_order) & (orders <= max_order)
        if not np.any(mask):
            return []

        idx = np.where(mask)[0]
        m = mag[idx]
        o = orders[idx]

        # Noise floor estimate (median of magnitudes)
        noise_floor = np.median(m)
        threshold_linear = noise_floor * (10.0 ** (threshold_db / 20.0))
        if threshold_linear < 1e-9:
            threshold_linear = 1e-9

        # Simple local-max peak finder
        peaks: list[FFTPeak] = []
        for i in range(1, len(m) - 1):
            if m[i] > m[i - 1] and m[i] > m[i + 1] and m[i] > threshold_linear:
                peaks.append(FFTPeak(order=float(o[i]), magnitude=float(m[i])))

        # Sort by magnitude descending
        peaks.sort(key=lambda p: p.magnitude, reverse=True)
        peaks = peaks[:max_peaks]

        # Label peaks
        for p in peaks:
            p.label = self._label_peak(p.order / motor_speed_hz, bearing)

        return peaks

    def _label_peak(self, order: float,
                    bearing: BearingDefectFreqs | None) -> str:
        """Assign a human-readable label to a peak based on its order."""

        # Check integer harmonics (1X, 2X, 3X ...)
        for n in range(1, 13):
            if abs(order - n) < 0.08:
                return f"{n}X"
            # Sub-harmonics
            if abs(order - n * 0.5) < 0.06 and n <= 4:
                return f"{n}/2X"

        # Check bearing defect frequencies
        if bearing:
            tol = 0.12
            for freq_val, label in [
                (bearing.bpfo, "BPFO"),
                (bearing.bpfi, "BPFI"),
                (bearing.bsf, "BSF"),
                (bearing.ftf, "FTF"),
            ]:
                if freq_val > 0.1:
                    # Check fundamental and first two harmonics
                    for mult in range(1, 4):
                        if abs(order - freq_val * mult) < tol:
                            prefix = f"{mult}×" if mult > 1 else ""
                            return f"{prefix}{label}"

        return ""

    # ------------------------------------------------------------------
    # Bearing Defect Frequency Calculator
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_bearing_frequencies(
            num_balls: int,
            ball_diameter: float,
            pitch_diameter: float,
            contact_angle_deg: float = 0.0
    ) -> BearingDefectFreqs:
        """
        Calculate bearing defect frequencies as orders of shaft speed.

        Parameters
        ----------
        num_balls : number of rolling elements
        ball_diameter : diameter of rolling element (any unit)
        pitch_diameter : pitch circle diameter (same unit as ball_diameter)
        contact_angle_deg : contact angle in degrees (0 for radial bearings)

        Returns
        -------
        BearingDefectFreqs with all values in orders (multiples of shaft speed).
        """
        if pitch_diameter <= 0 or num_balls <= 0:
            return BearingDefectFreqs()

        cos_a = np.cos(np.radians(contact_angle_deg))
        ratio = ball_diameter / pitch_diameter

        ftf = 0.5 * (1.0 - ratio * cos_a)
        bpfo = (num_balls / 2.0) * (1.0 - ratio * cos_a)
        bpfi = (num_balls / 2.0) * (1.0 + ratio * cos_a)
        bsf = (pitch_diameter / (2.0 * ball_diameter)) * (
                1.0 - (ratio * cos_a) ** 2)

        return BearingDefectFreqs(
            bpfo=round(bpfo, 4),
            bpfi=round(bpfi, 4),
            bsf=round(bsf, 4),
            ftf=round(ftf, 4)
        )

    # ------------------------------------------------------------------
    # Envelope Analysis (Hilbert Transform)
    # ------------------------------------------------------------------

    @staticmethod
    def envelope_analysis(adc_data: np.ndarray,
                          sample_rate: float,
                          motor_speed_hz: float,
                          bandpass_low_order: float = 5.0,
                          bandpass_high_order: float = 50.0
                          ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute envelope spectrum via Hilbert transform for bearing diagnostics.

        Steps:
        1. Bandpass filter the raw signal (in frequency domain)
        2. Compute analytic signal via FFT-based Hilbert
        3. Extract envelope (magnitude of analytic signal)
        4. FFT of envelope → envelope spectrum

        Returns (orders, envelope_magnitude).
        """
        n = len(adc_data)
        if n < 1024 or motor_speed_hz <= 0.01:
            return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

        data = adc_data.astype(np.float64)
        data -= np.mean(data)

        # FFT of raw signal
        F = np.fft.fft(data)
        freqs = np.fft.fftfreq(n, d=1.0 / sample_rate)

        # Bandpass filter
        low_hz = bandpass_low_order * motor_speed_hz
        high_hz = bandpass_high_order * motor_speed_hz
        mask = (np.abs(freqs) < low_hz) | (np.abs(freqs) > high_hz)
        F[mask] = 0.0

        # Hilbert transform → analytic signal
        h = np.zeros(n)
        if n % 2 == 0:
            h[0] = h[n // 2] = 1.0
            h[1:n // 2] = 2.0
        else:
            h[0] = 1.0
            h[1:(n + 1) // 2] = 2.0

        analytic = np.fft.ifft(F * h)
        envelope = np.abs(analytic)

        # Remove DC from envelope
        envelope -= np.mean(envelope)

        # FFT of envelope
        env_fft = np.abs(np.fft.rfft(envelope))
        env_freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

        # Convert to orders
        orders = env_freqs / motor_speed_hz
        mag = (env_fft / n) * 2.0
        np.clip(mag, 1e-9, None, out=mag)

        return orders.astype(np.float32), mag.astype(np.float32)

    # ------------------------------------------------------------------
    # TIR (Total Indicator Reading)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_tir(polar_bins: np.ndarray
                      ) -> tuple[float, float, float]:
        """
        Calculate Total Indicator Reading from a 360-degree polar scan.

        Returns (max_val, min_val, tir).
        """
        mask = polar_bins != 0.0
        valid = polar_bins[mask]

        if len(valid) < 10:
            return 0.0, 0.0, 0.0

        max_val = float(np.max(valid))
        min_val = float(np.min(valid))
        tir = max_val - min_val

        return max_val, min_val, tir

    # ------------------------------------------------------------------
    # Run-out (peak-to-peak per revolution)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_runout(polar_bins: np.ndarray
                         ) -> tuple[float, float, float]:
        """
        Calculate run-out from polar data.

        Returns (high_spot_deg, low_spot_deg, runout_pk_pk).
        """
        mask = polar_bins != 0.0
        valid_idx = np.where(mask)[0]

        if len(valid_idx) < 10:
            return 0.0, 0.0, 0.0

        valid = polar_bins[valid_idx]
        high_idx = valid_idx[np.argmax(valid)]
        low_idx = valid_idx[np.argmin(valid)]

        return float(high_idx), float(low_idx), float(np.max(valid) - np.min(valid))


def run_background_fft(adc_data, sample_rate, motor_speed_hz, window_type="Hanning",
                       fft_size=-1, domain="Order", zero_pad_factor=1, num_averages=1):
    """Module-level wrapper for Analyzer.perform_fft to run on multiprocessing pool."""
    analyzer = Analyzer()
    return analyzer.perform_fft(
        adc_data, sample_rate, motor_speed_hz,
        window_type=window_type, fft_size=fft_size, domain=domain,
        zero_pad_factor=zero_pad_factor, num_averages=num_averages
    )

