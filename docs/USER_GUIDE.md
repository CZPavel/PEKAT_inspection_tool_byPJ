# PEKAT Inspection Tool - User Guide (V03)

This guide describes GUI controls and runtime indicators.

## Main Tab: Konfigurace

### 1) Mode (SDK/REST)
- Default: `REST`
- Use `SDK` only when SDK runtime is available and intended

### 2) Host / Port
- Target project host and port
- Default: `127.0.0.1` and `8000`

### 3) Project path
- Required only for PM TCP project control

### 4) Input source
- `Slozka` for folder mode
- `Zahrnout podslozky` for recursive scan
- `Vybrat soubory` for fixed file list mode

### 5) Run mode
- `Loop`: Nacita snimky k vyhodnoceni stale dokola
- `Once`: Odesle postupne vsechny snimky k vyhodnoceni jen jednou
- `Send ALL Once and Watch`: Odesle vsechny snimky ve slozce jednou, pak ceka na dalsi nove
- `Just Watch`: Ignoruje stavajici snimky ve slozce a ceka jen na nove soubory

Poznamka:
- Vsechny rezimy respektuji volbu `Zahrnout podslozky`.

### 6) Delay
- `Prodleva (ms)` is delay between sends

### 7) Data payload options
- `Include filename`
- `Include timestamp`
- `Include string`

Result is sent as a single `data` string in REST/SDK analyze call.

### 8) API key setup
- Open dialog with `API key setup`
- Keep empty if secure analyze is not enabled in project

### 9) Project control (PM TCP)
- `PM TCP enabled`
- PM host/port (typically `7002`)
- Policy:
  - `Off (status only)`
  - `Auto-start on Connect`
  - `Auto-start + Auto-stop on Disconnect`
  - `Automatic restart`

Notes:
- Works only when PM TCP server is enabled in Projects Manager settings.
- `start/stop` may return no immediate response (timeout); app tracks state through `status`.

### 10) Control buttons
- `Connect`
- `Disconnect`
- `Start sending`
- `Stop sending`

## Runtime Indicators

- `Connection`: current connection state
- `Sending`: sender state
- `Production Mode`: ON/OFF/Unknown from last context
- `Data preview`: last sent `data`
- `Odeslano`: total sent images
- `Posledni vyhodnoceni (ms)`: time of last evaluated image
- `Prumerny cas (ms)`: average evaluation time
- `NOK` and `OK`: large counters in bottom panel

## Tabs

- `Manipulace se soubory`: post-evaluation delete/move rules
- `Log`: runtime log stream
- `JSON`: full JSON of last processed image context (or last error payload)

## Tab: Manipulace se soubory

### 1) Enable
- `Povolit manipulaci se soubory` turns post-processing on/off
- In `Loop` run mode, this checkbox is disabled and forced OFF
- Message is shown: `V rezimu Loop neni funkcionalita dostupna.`

### 2) Manipulation mode
- `Po vyhodnoceni mazat soubory`
- `Presouvat podle vyhodnoceni`
- `Presun kdyz OK - Smaz kdyz NOK`
- `Smaz kdyz OK - Presun kdyz NOK`

### 3) Section OK / Section NOK
Each section contains:
- target folder path
- folder picker button
- `Vytvorit novou slozku pro kazdy den (YYYY_MM_DD)`
- `Vytvorit novou slozku pro kazdou hodinu (MM_DD_HH)`
- `Include RESULT` (`OK_` / `NOK_` prefix)
- `Include Timestamp` (`_YYYY_MM_DD_HH_MM_SS` suffix)
- `Include String` + custom text field

Rules:
- If both daily and hourly are enabled, hourly folder is created under daily folder.
- If only hourly is enabled, hourly folder is created directly under target root.
- Unknown or error evaluation is treated as `NOK` for routing.
- Name collisions in target folder use auto-rename (`_1`, `_2`, ...).

## Reset

`Reset counter and list` resets all runtime counters:
- sent count
- last/average evaluation time
- OK/NOK counters
- sent list
- JSON snapshot (to default state)

## Recommended Workflow

1. Configure host/port and input
2. Optional: configure PM TCP + policy
3. Click `Connect`
4. Click `Start sending`
5. Monitor `Log`, `JSON`, and counters

## Troubleshooting

- If reconnect loops appear, verify project is running on expected host/port.
- For PM control issues, verify PM TCP is enabled and project path is valid.
- `data` is internal project argument; it is used inside PEKAT flow and is not usually returned in REST response.
