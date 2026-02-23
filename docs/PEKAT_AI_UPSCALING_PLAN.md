# AI Upscaling in PEKAT VISION 3.19.3 (CPU, ONNX Runtime)

This runbook is for offline-capable deployment of AI upscaling in PEKAT Code module
using ONNX Runtime + Real-ESRGAN-General-x4v3 on Windows CPU.

## Target environment
- PEKAT server: `C:\Program Files\PEKAT VISION 3.19.3\server\pekat_vision_server.exe`
- PEKAT Python ABI: `cp310` (Python 3.10.x, x64)
- Runtime: CPU only (`CPUExecutionProvider`)

## Compatibility and pinning
- Use `onnxruntime==1.23.2` for `cp310-cp310-win_amd64`.
- Newer `onnxruntime` releases do not always provide `cp310` wheels.

## Recommended deployment strategy (A)
Deploy dependencies outside Program Files:
- Python deps: `C:\ProgramData\PEKAT\pydeps`
- Model files: `C:\PekatProjects\<Project>\models\`

In Code module, prepend `C:\ProgramData\PEKAT\pydeps` to `sys.path`.

## Fallback strategy (B)
Use GUI wizard in `Pekat Tuning`:
- `Install ONNX Runtime + Real-ESRGAN`
- This copies bundle to `<PEKAT_ROOT>\server`
- Requires admin rights and may be overwritten by PEKAT updates.

## Pre-check checklist
1. Verify OS architecture is x64.
2. Verify PEKAT Python ABI is 3.10 x64 (`cp310`).
3. Verify write rights for target path (`Program Files` often requires elevation).
4. Stop `pekat_vision_server.exe` before copy.
5. If `DLL load failed`, install/update Microsoft Visual C++ Redistributable.
6. Plan performance: use ROI/tile upscaling, avoid full-frame every cycle.

## Build offline payload (online prep machine)
From repository:
- `resources/pekat_libs/onnxruntime_realesrgan/helpers/build_offline_payload.ps1`

The script downloads:
- `onnxruntime==1.23.2` + dependencies for `cp310/win_amd64`
- Qualcomm model archive `real_esrgan_general_x4v3-onnx-float.zip`

And fills:
- `resources/pekat_libs/onnxruntime_realesrgan/payload/pydeps/...`
- `resources/pekat_libs/onnxruntime_realesrgan/payload/models/real_esrgan_general_x4v3.onnx`
- `resources/pekat_libs/onnxruntime_realesrgan/payload/models/real_esrgan_general_x4v3.data`

## Manual commands (variant A)
```powershell
py -3.10 -m pip install --target C:\ProgramData\PEKAT\pydeps onnxruntime==1.23.2
```

Offline from wheel cache:
```powershell
py -3.10 -m pip install --no-index --find-links C:\temp\ort_wheels --target C:\ProgramData\PEKAT\pydeps onnxruntime==1.23.2
```

## Required files
- `onnxruntime/capi/onnxruntime_pybind11_state.pyd`
- `onnxruntime/capi/onnxruntime.dll`
- `onnxruntime/capi/onnxruntime_providers_shared.dll`
- `real_esrgan_general_x4v3.onnx`
- `real_esrgan_general_x4v3.data`

## Code module smoke script
Use:
- `resources/pekat_libs/onnxruntime_realesrgan/helpers/code_module_onnx_realesrgan_cpu_smoke.py`

Adjust paths:
- `PYDEPS_PATH`
- `MODEL_PATH`

The script keeps `InferenceSession` cached and updates `context["image"]`.

## Production Code Module Script (tiled, arbitrary size)
The same helper script now supports tiled inference for arbitrary input sizes:
- fixed model geometry `128 -> 512` per tile
- overlap blending to reduce seam artifacts
- safe fallback without exception throw in PEKAT flow

Supported `module_item` keys:
- `enabled` (`bool`, default `True`)
- `output_mode` (`x4 | same_size`, default `x4`)
- `tile_size` (`int`, default `128`, fixed to model input)
- `tile_overlap` (`int`, default `16`)
- `pydeps_path` (`str`, optional)
- `model_path` (`str`, optional)
- `log_level` (`silent | info`, default `info`)

Defaults and fallback resolution:
- `pydeps_path`: `C:\ProgramData\PEKAT\pydeps`, fallback `C:\Program Files\PEKAT VISION 3.19.3\server`
- `model_path`: `C:\ProgramData\PEKAT\models\real_esrgan_general_x4v3.onnx`,
  fallback `C:\Program Files\PEKAT VISION 3.19.3\server\models\real_esrgan_general_x4v3.onnx`

## Production notes
- Add module toggle (`enabled`) in `module_item` and default it to off.
- Prefer ROI upscaling only (e.g. text/label regions).
- If needed, tile image to 128x128 chunks and stitch output.
- Keep safe fallback: on inference error, return original image.

## References
- ONNX Runtime install docs: https://onnxruntime.ai/docs/install/
- Qualcomm model page: https://aihub.qualcomm.com/models/real_esrgan_general_x4v3
- Hugging Face model card: https://huggingface.co/qualcomm/Real-ESRGAN-General-x4v3
- Qualcomm artifact URL:
  https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/real_esrgan_general_x4v3/releases/v0.46.0/real_esrgan_general_x4v3-onnx-float.zip
- Microsoft VC++ runtime:
  https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
