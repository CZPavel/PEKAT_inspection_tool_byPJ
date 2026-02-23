param(
    [string]$OutputRoot = "C:\VS_CODE_PROJECTS\PEKAT_Inspection_tool_by_PJ_V03\resources\pekat_libs\onnxruntime_realesrgan\payload",
    [string]$WheelCache = "C:\temp\ort_wheels",
    [string]$PythonCmd = "py",
    [string]$PythonSelector = "-3"
)

$ErrorActionPreference = "Stop"

$pydeps = Join-Path $OutputRoot "pydeps"
$models = Join-Path $OutputRoot "models"

New-Item -ItemType Directory -Force $WheelCache | Out-Null
if (Test-Path $pydeps) {
    Remove-Item -Recurse -Force $pydeps
}
if (Test-Path $models) {
    Remove-Item -Recurse -Force $models
}
New-Item -ItemType Directory -Force $pydeps | Out-Null
New-Item -ItemType Directory -Force $models | Out-Null

$packages = @(
    "onnxruntime==1.23.2",
    "flatbuffers==25.9.23",
    "protobuf==6.33.0",
    "coloredlogs==15.0.1",
    "humanfriendly==10.0"
)

& $PythonCmd $PythonSelector -m pip download --no-deps --only-binary=:all: --platform win_amd64 --python-version 310 --implementation cp --abi cp310 -d $WheelCache @packages
if ($LASTEXITCODE -ne 0) {
    throw "pip download failed"
}

& $PythonCmd $PythonSelector -c "import glob, os, zipfile; pydeps=r'$pydeps'; allowed=('onnxruntime-','flatbuffers-','protobuf-','coloredlogs-','humanfriendly-'); wheels=[w for w in glob.glob(r'$WheelCache\\*.whl') if os.path.basename(w).startswith(allowed)]; [zipfile.ZipFile(w).extractall(pydeps) for w in wheels]"
if ($LASTEXITCODE -ne 0) {
    throw "wheel extraction failed"
}

$modelZipUrl = "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/real_esrgan_general_x4v3/releases/v0.46.0/real_esrgan_general_x4v3-onnx-float.zip"
$modelZipPath = Join-Path $WheelCache "real_esrgan_general_x4v3-onnx-float.zip"
Invoke-WebRequest -Uri $modelZipUrl -OutFile $modelZipPath
Expand-Archive -Path $modelZipPath -DestinationPath $WheelCache -Force

$extractRoot = Join-Path $WheelCache "real_esrgan_general_x4v3-onnx-float"
Copy-Item (Join-Path $extractRoot "real_esrgan_general_x4v3.onnx") (Join-Path $models "real_esrgan_general_x4v3.onnx") -Force
Copy-Item (Join-Path $extractRoot "real_esrgan_general_x4v3.data") (Join-Path $models "real_esrgan_general_x4v3.data") -Force
Copy-Item (Join-Path $extractRoot "metadata.yaml") (Join-Path $models "metadata.yaml") -Force
Copy-Item (Join-Path $extractRoot "tool-versions.yaml") (Join-Path $models "tool-versions.yaml") -Force

$required = @(
    "pydeps\onnxruntime\capi\onnxruntime_pybind11_state.pyd",
    "pydeps\onnxruntime\capi\onnxruntime.dll",
    "pydeps\onnxruntime\capi\onnxruntime_providers_shared.dll",
    "models\real_esrgan_general_x4v3.onnx",
    "models\real_esrgan_general_x4v3.data"
)

$missing = @()
foreach ($item in $required) {
    $check = Join-Path $OutputRoot $item
    if (-not (Test-Path $check)) {
        $missing += $item
    }
}

if ($missing.Count -gt 0) {
    throw "Missing required payload files: $($missing -join ', ')"
}

Write-Output "Payload build complete: $OutputRoot"
