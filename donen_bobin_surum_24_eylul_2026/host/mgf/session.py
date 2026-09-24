"""
Session Save and Load Manager for MGF Radar V2.
Saves ADC and Encoder buffers along with metadata and annotations as a compressed .mgf file.
"""
import json
import time
import numpy as np

def save_session(filepath: str, adc_data: np.ndarray, enc_data: np.ndarray, 
                 rate_sps: float, motor_speed_hz: float, annotations: str = "", 
                 data_mode: int = 1, step_data: np.ndarray = None, enc_pulses_data: np.ndarray = None):
    """
    Save session data to a compressed .mgf file.
    """
    import os

    if not filepath.endswith('.mgf'):
        filepath += '.mgf'

    # np.savez_compressed auto-appends '.npz' when given a string path.
    # Strip '.mgf' so it saves as '<base>.npz', then rename to '<base>.mgf'.
    base = filepath[:-4]  # remove '.mgf'
    
    metadata = {
        "timestamp": time.time(),
        "rate_sps": rate_sps,
        "motor_speed_hz": motor_speed_hz,
        "annotations": annotations,
        "data_mode": data_mode
    }
    
    kwargs = {}
    if step_data is not None:
        kwargs['step'] = step_data
    if enc_pulses_data is not None:
        kwargs['enc_pulses'] = enc_pulses_data
        
    np.savez_compressed(
        base,
        adc=adc_data,
        enc=enc_data,
        metadata=json.dumps(metadata),
        **kwargs
    )

    # Rename '<base>.npz' -> '<base>.mgf'
    npz_path = base + '.npz'
    if os.path.exists(npz_path):
        os.replace(npz_path, filepath)

def load_session(filepath: str):
    """
    Load session data from a .mgf file.
    Returns: (adc, enc, rate_sps, motor_speed, annotations, data_mode, step, enc_pulses)
    """
    with open(filepath, 'rb') as f:
        with np.load(f, allow_pickle=True) as data:
            adc = data['adc']
            enc = data['enc']
            metadata_str = str(data['metadata'])
            
            # If loaded as numpy object array or bytes, decode it
            try:
                metadata = json.loads(metadata_str)
            except Exception:
                # Handle possible conversion issues with numpy string array wrapping
                if hasattr(data['metadata'], 'item'):
                    metadata_str = data['metadata'].item()
                else:
                    metadata_str = data['metadata'][()]
                if isinstance(metadata_str, bytes):
                    metadata_str = metadata_str.decode('utf-8')
                metadata = json.loads(metadata_str)
                
            rate_sps = metadata.get("rate_sps", 2400.0)
            motor_speed_hz = metadata.get("motor_speed_hz", 1.0)
            annotations = metadata.get("annotations", "")
            data_mode = metadata.get("data_mode", 1)
            
            step = data['step'] if 'step' in data.files else None
            enc_pulses = data['enc_pulses'] if 'enc_pulses' in data.files else None
            
            return adc, enc, rate_sps, motor_speed_hz, annotations, data_mode, step, enc_pulses
