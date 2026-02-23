# ONNX Runtime + Real-ESRGAN payload

This folder is used by `install_manifest.json` for fallback install to:
`<PEKAT_ROOT>\\server`.

Recommended production strategy is to deploy dependencies to:
`C:\\ProgramData\\PEKAT\\pydeps` and load via `sys.path` in Code module.

To build offline payload assets, run:
`helpers\\build_offline_payload.ps1`

The script downloads cp310/win_amd64 wheels and Qualcomm model files,
then populates:
- `payload\\pydeps\\...`
- `payload\\models\\real_esrgan_general_x4v3.onnx`
- `payload\\models\\real_esrgan_general_x4v3.data`
