from __future__ import annotations

import inspect
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np

from .ring_buffer import AudioRingBuffer


def _require_sounddevice():
    try:
        import sounddevice as sd  # type: ignore
    except Exception as exc:  # pragma: no cover - env dependent
        raise RuntimeError(
            "Missing dependency 'sounddevice'. Install dependencies first."
        ) from exc
    return sd


def _require_pyaudiowpatch():
    try:
        import pyaudiowpatch as pyaudio  # type: ignore
    except Exception as exc:  # pragma: no cover - env dependent
        raise RuntimeError(
            "Missing dependency 'pyaudiowpatch'. Install dependencies first."
        ) from exc
    return pyaudio


def _resolve_primary_output_index(sd) -> int:
    devices = sd.query_devices()
    try:
        hostapis = sd.query_hostapis()
    except Exception:
        hostapis = []

    for hostapi in hostapis:
        name = str(hostapi.get("name", "")).lower()
        if "wasapi" not in name:
            continue
        idx = int(hostapi.get("default_output_device", -1))
        if 0 <= idx < len(devices):
            dev = devices[idx]
            if int(dev.get("max_output_channels", 0)) > 0:
                return idx

    try:
        default_out = sd.default.device[1]
    except Exception:
        default_out = None
    if default_out is not None:
        idx = int(default_out)
        if 0 <= idx < len(devices):
            dev = devices[idx]
            if int(dev.get("max_output_channels", 0)) > 0:
                return idx

    for idx, dev in enumerate(devices):
        if int(dev.get("max_output_channels", 0)) > 0:
            return idx
    raise RuntimeError("No output audio device found.")


def _resolve_device_index(
    sd,
    device_id: str | int,
    *,
    require_input: bool,
    require_output: bool,
) -> int:
    if str(device_id).lower() == "default":
        if require_output and not require_input:
            return _resolve_primary_output_index(sd)
        default = sd.default.device[0 if require_input else 1]
        if default is not None and int(default) >= 0:
            return int(default)

    try:
        return int(device_id)
    except Exception:
        pass

    needle = str(device_id).lower().strip()
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if require_input and int(dev.get("max_input_channels", 0)) <= 0:
            continue
        if require_output and int(dev.get("max_output_channels", 0)) <= 0:
            continue
        if needle in str(dev.get("name", "")).lower():
            return idx
    role = "input" if require_input else "output"
    raise RuntimeError(f"Cannot resolve {role} device '{device_id}'.")


def list_microphone_devices() -> List[Dict[str, str]]:
    sd = _require_sounddevice()
    rows: List[Dict[str, str]] = [{"id": "default", "label": "Default system microphone"}]
    for idx, dev in enumerate(sd.query_devices()):
        max_input = int(dev.get("max_input_channels", 0))
        if max_input <= 0:
            continue
        name = str(dev.get("name", "unknown"))
        rows.append({"id": str(idx), "label": f"{idx}: {name} (in={max_input})"})
    return rows


def _resolve_primary_loopback_id(sd=None) -> str:
    sd_ctx = sd or _require_sounddevice()
    try:
        pyaudio = _require_pyaudiowpatch()
        pa = pyaudio.PyAudio()
        try:
            out_idx = _resolve_primary_output_index(sd_ctx)
            if hasattr(pa, "get_wasapi_loopback_analogue_by_index"):
                loop = dict(pa.get_wasapi_loopback_analogue_by_index(int(out_idx)))
                idx = int(loop.get("index", -1))
                if idx >= 0:
                    return str(idx)
            loop = dict(pa.get_default_wasapi_loopback())
            idx = int(loop.get("index", -1))
            if idx >= 0:
                return str(idx)
        finally:
            pa.terminate()
    except Exception:
        pass
    return str(_resolve_primary_output_index(sd_ctx))


def list_loopback_devices() -> List[Dict[str, str]]:
    try:
        pyaudio = _require_pyaudiowpatch()
        pa = pyaudio.PyAudio()
        try:
            primary = _resolve_primary_loopback_id()
            rows: List[Dict[str, str]] = []
            for dev in pa.get_loopback_device_info_generator():
                idx = str(int(dev.get("index", -1)))
                name = str(dev.get("name", "unknown"))
                max_in = int(dev.get("maxInputChannels", 0))
                sr = int(round(float(dev.get("defaultSampleRate", 0.0))))
                label = f"{idx}: {name} (loopback in={max_in}, sr={sr})"
                if idx == primary:
                    label = f"[PRIMARY] {label}"
                rows.append({"id": idx, "label": label})
            rows.sort(key=lambda row: (0 if row["id"] == primary else 1, int(row["id"])))
            if not rows:
                rows.append({"id": "default", "label": "Default loopback output"})
            return rows
        finally:
            pa.terminate()
    except Exception:
        sd = _require_sounddevice()
        primary = _resolve_primary_loopback_id(sd)
        rows = [{"id": "default", "label": "Default loopback output"}]
        for idx, dev in enumerate(sd.query_devices()):
            max_out = int(dev.get("max_output_channels", 0))
            if max_out <= 0:
                continue
            label = f"{idx}: {dev.get('name', 'unknown')} (out={max_out})"
            if str(idx) == primary:
                label = f"[PRIMARY] {label}"
            rows.append({"id": str(idx), "label": label})
        return rows


def _find_loopback_like_input(sd, preferred_output_idx: int | None = None) -> int | None:
    devices = sd.query_devices()
    preferred_name = ""
    if preferred_output_idx is not None and 0 <= preferred_output_idx < len(devices):
        preferred_name = str(devices[preferred_output_idx].get("name", "")).lower()

    keywords = ("loopback", "stereo mix", "what u hear", "mix", "smesovac")
    best_idx: int | None = None
    best_score = -10**9
    for idx, dev in enumerate(devices):
        if int(dev.get("max_input_channels", 0)) <= 0:
            continue
        name = str(dev.get("name", "")).lower()
        score = 0
        if any(k in name for k in keywords):
            score += 100
        if preferred_name and (preferred_name in name or name in preferred_name):
            score += 20
        if int(dev.get("max_input_channels", 0)) >= 2:
            score += 5
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx is not None and best_score >= 20:
        return best_idx
    return None


class AudioSourceBase(ABC):
    sample_rate: int
    channels: int

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_latest(self, num_samples: int) -> np.ndarray:
        raise NotImplementedError


class _SounddeviceSourceBase(AudioSourceBase):
    def __init__(self, *, sample_rate: int, channels: int, buffer_seconds: float = 8.0) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(max(1, channels))
        self.buffer_seconds = float(buffer_seconds)
        self._ring = AudioRingBuffer(
            capacity_samples=max(self.sample_rate, int(self.sample_rate * self.buffer_seconds)),
            channels=self.channels,
        )
        self._stream = None
        self._started = False

    def _callback(self, indata, _frames, _time_info, _status) -> None:
        self._ring.write(np.asarray(indata, dtype=np.float32))

    def get_latest(self, num_samples: int) -> np.ndarray:
        return self._ring.read_latest(num_samples)

    def stop(self) -> None:
        if self._stream is not None:
            try:
                if hasattr(self._stream, "is_active") and self._stream.is_active():
                    self._stream.stop_stream()
                elif hasattr(self._stream, "stop"):
                    self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None
        self._started = False


class MicrophoneSource(_SounddeviceSourceBase):
    def __init__(self, *, device_id: str = "default", sample_rate: int = 96000, channels: int = 1) -> None:
        super().__init__(sample_rate=sample_rate, channels=channels)
        self.device_id = device_id

    def start(self) -> None:
        if self._started:
            return
        sd = _require_sounddevice()
        device_idx = _resolve_device_index(sd, self.device_id, require_input=True, require_output=False)
        dev = sd.query_devices(device_idx)
        max_in = int(dev.get("max_input_channels", 1))
        stream_channels = int(max(1, min(self.channels, max_in)))
        default_sr = int(round(float(dev.get("default_samplerate", self.sample_rate))))
        sr_candidates = [self.sample_rate, default_sr, 48000, 44100]

        errors: List[str] = []
        for sr in dict.fromkeys(sr_candidates):
            try:
                self._stream = sd.InputStream(
                    samplerate=int(sr),
                    channels=stream_channels,
                    dtype="float32",
                    device=device_idx,
                    callback=self._callback,
                    blocksize=0,
                )
                self._stream.start()
                self.sample_rate = int(sr)
                self.channels = int(stream_channels)
                self._started = True
                return
            except Exception as exc:
                errors.append(f"sr={sr}: {exc}")
        raise RuntimeError("Cannot start microphone stream.\n" + "\n".join(errors))


class LoopbackSource(_SounddeviceSourceBase):
    def __init__(
        self,
        *,
        device_id: str = "default",
        sample_rate: int = 96000,
        channels: int = 2,
        backend_policy: str = "auto",
    ) -> None:
        super().__init__(sample_rate=sample_rate, channels=channels)
        self.device_id = device_id
        self.backend_policy = backend_policy
        self._pyaudio = None
        self._pa_ctx = None

    def _resolve_loopback_device_info(self, pa, device_id: str) -> Dict[str, Any]:
        if str(device_id).lower() == "default":
            out_idx = _resolve_primary_output_index(_require_sounddevice())
            if hasattr(pa, "get_wasapi_loopback_analogue_by_index"):
                try:
                    return dict(pa.get_wasapi_loopback_analogue_by_index(int(out_idx)))
                except Exception:
                    pass
            return dict(pa.get_default_wasapi_loopback())

        try:
            idx = int(device_id)
            dev = dict(pa.get_device_info_by_index(idx))
            if bool(dev.get("isLoopbackDevice", False)):
                return dev
            if hasattr(pa, "get_wasapi_loopback_analogue_by_index"):
                return dict(pa.get_wasapi_loopback_analogue_by_index(idx))
        except Exception:
            pass

        needle = str(device_id).lower().strip()
        for dev in pa.get_loopback_device_info_generator():
            dev_dict = dict(dev)
            if needle in str(dev_dict.get("name", "")).lower():
                return dev_dict
        raise RuntimeError(f"Cannot resolve WASAPI loopback device '{device_id}'.")

    def _callback_pyaudio(self, in_data, _frame_count, _time_info, _status):
        arr = np.frombuffer(in_data, dtype=np.float32)
        if self.channels > 1:
            arr = arr.reshape(-1, self.channels)
        else:
            arr = arr.reshape(-1, 1)
        self._ring.write(arr)
        return (None, self._pyaudio.paContinue)

    def _start_with_pyaudio(self) -> None:
        self._pyaudio = _require_pyaudiowpatch()
        self._pa_ctx = self._pyaudio.PyAudio()
        errors: List[str] = []
        try:
            dev = self._resolve_loopback_device_info(self._pa_ctx, self.device_id)
            max_in = int(dev.get("maxInputChannels", 0))
            if max_in <= 0:
                raise RuntimeError("Selected loopback endpoint has zero input channels.")

            default_sr = int(round(float(dev.get("defaultSampleRate", self.sample_rate))))
            stream_channels = int(max(1, min(self.channels, max_in)))
            sr_candidates = [self.sample_rate, default_sr, 48000, 44100]
            for sr in dict.fromkeys(sr_candidates):
                try:
                    self._stream = self._pa_ctx.open(
                        format=self._pyaudio.paFloat32,
                        channels=stream_channels,
                        rate=int(sr),
                        input=True,
                        frames_per_buffer=1024,
                        input_device_index=int(dev["index"]),
                        stream_callback=self._callback_pyaudio,
                        start=True,
                    )
                    self.sample_rate = int(sr)
                    self.channels = int(stream_channels)
                    self._started = True
                    return
                except Exception as exc:
                    errors.append(f"wasapi_loopback idx={dev.get('index')} sr={sr}: {exc}")
            raise RuntimeError("Cannot start WASAPI loopback stream.\n" + "\n".join(errors))
        except Exception:
            self.stop()
            raise

    def _start_with_sounddevice(self) -> None:
        sd = _require_sounddevice()
        output_idx = _resolve_device_index(sd, self.device_id, require_input=False, require_output=True)
        output_dev = sd.query_devices(output_idx)
        output_sr = int(round(float(output_dev.get("default_samplerate", self.sample_rate))))
        stream_sr = self.sample_rate if self.sample_rate > 0 else output_sr
        requested_channels = int(max(1, min(self.channels, int(output_dev.get("max_output_channels", 2)))))

        def callback(indata, _frames, _time_info, _status):
            self._ring.write(np.asarray(indata, dtype=np.float32))

        wasapi_settings = None
        supports_loopback = False
        if hasattr(sd, "WasapiSettings"):
            try:
                sig = inspect.signature(sd.WasapiSettings)
                supports_loopback = "loopback" in sig.parameters
            except Exception:
                supports_loopback = False

        if supports_loopback:
            wasapi_settings = sd.WasapiSettings(loopback=True)
            self._stream = sd.InputStream(
                samplerate=stream_sr,
                channels=requested_channels,
                dtype="float32",
                device=output_idx,
                callback=callback,
                blocksize=0,
                extra_settings=wasapi_settings,
            )
            self._stream.start()
            self.sample_rate = int(stream_sr)
            self.channels = int(requested_channels)
            self._started = True
            return

        alt_input_idx = _find_loopback_like_input(sd, preferred_output_idx=output_idx)
        if alt_input_idx is None:
            raise RuntimeError(
                "No loopback fallback input was found (Stereo Mix / loopback-like device)."
            )
        input_dev = sd.query_devices(alt_input_idx)
        in_channels = int(input_dev.get("max_input_channels", 1))
        stream_channels = int(max(1, min(requested_channels, in_channels)))
        self._stream = sd.InputStream(
            samplerate=stream_sr,
            channels=stream_channels,
            dtype="float32",
            device=alt_input_idx,
            callback=callback,
            blocksize=0,
        )
        self._stream.start()
        self.sample_rate = int(stream_sr)
        self.channels = int(stream_channels)
        self._started = True

    def start(self) -> None:
        if self._started:
            return
        policy = (self.backend_policy or "auto").strip().lower()
        errors: List[str] = []

        if policy in {"auto", "prefer_pyaudiowpatch"}:
            try:
                self._start_with_pyaudio()
                return
            except Exception as exc:
                errors.append(f"pyaudiowpatch path failed: {exc}")
                if policy == "prefer_pyaudiowpatch":
                    # Still allow fallback to sounddevice for resilience.
                    pass

        try:
            self._start_with_sounddevice()
            return
        except Exception as exc:
            errors.append(f"sounddevice path failed: {exc}")
            self.stop()
            raise RuntimeError("Cannot start loopback source.\n" + "\n".join(errors))

    def stop(self) -> None:
        super().stop()
        if self._pa_ctx is not None:
            try:
                self._pa_ctx.terminate()
            except Exception:
                pass
        self._pa_ctx = None
        self._pyaudio = None


class SineSource(AudioSourceBase):
    def __init__(
        self,
        *,
        sample_rate: int = 96000,
        channels: int = 1,
        frequency_hz: float = 440.0,
        buffer_seconds: float = 8.0,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(max(1, channels))
        self.frequency_hz = float(frequency_hz)
        self.buffer_seconds = float(buffer_seconds)
        self._ring = AudioRingBuffer(
            capacity_samples=max(self.sample_rate, int(self.sample_rate * self.buffer_seconds)),
            channels=self.channels,
        )
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._phase = 0.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        block = 2048
        dt = 1.0 / float(self.sample_rate)
        while not self._stop_event.is_set():
            t = np.arange(block, dtype=np.float32) * dt
            chunk = np.sin(2.0 * np.pi * self.frequency_hz * t + self._phase).astype(np.float32)
            self._phase = float(
                (self._phase + 2.0 * np.pi * self.frequency_hz * block * dt) % (2.0 * np.pi)
            )
            if self.channels > 1:
                chunk = np.repeat(chunk[:, None], self.channels, axis=1)
            self._ring.write(chunk)
            time.sleep(block / float(self.sample_rate) * 0.9)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None

    def get_latest(self, num_samples: int) -> np.ndarray:
        return self._ring.read_latest(num_samples)

