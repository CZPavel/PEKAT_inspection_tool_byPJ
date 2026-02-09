# PEKAT Inspection Tool – Technical Overview

Tento dokument popisuje technickou architekturu aplikace, tok dat a volání do PEKAT VISION.

## Pøehled architektury

Aplikace je rozdìlena na ètyøi vrstvy:

1. GUI/CLI vrstva – ovládání, validace vstupù, uložení nastavení
2. Connection Manager – øízení pøipojení, ping, PM TCP akce, stav pøipojení
3. Runner – skenování souborù, fronta, odesílání snímkù
4. Klienti – REST/SDK/TCP

## Moduly a odpovìdnosti

### `pektool/core/connection.py`
- Stav pøipojení: `disconnected | connecting | connected | reconnecting | error | disconnecting`
- Vytváøí klienta (REST/SDK), provádí `ping`
- PM TCP ovládání (start/stop/status) dle policy
- Automatic restart: stop › start › èekání 30s › ping (max 5 pokusù)
- Ukládá `last_context`, `last_production_mode`, `last_data`
- Ukládá `total_sent` + `sent_list` (poslané soubory)

### `pektool/core/runner.py`
- Skenuje složku (polling) a plní frontu
- Odesílá snímky pøes `ConnectionManager.client`
- Není-li pøipojeno, èeká (žádné odesílání)
- Loguje hodnotu `data` a výsledek do JSONL

### `pektool/clients/rest_client.py`
- REST endpointy:
  - `GET /ping`
  - `POST /analyze_image` s PNG bytes
- Podporuje `data` jako URL parametr
- Pokud vstup není PNG, provede konverzi pøes OpenCV › PNG
- Parsování odpovìdi:
  - `response_type=context` › `response.json()`
  - jinak `ContextBase64utf` nebo `ImageLen` pøi `context_in_body`

### `pektool/clients/sdk_client.py`
- SDK instance `Instance(...).analyze(...)`
- `data` je posláno pøes argument `data=`

### `pektool/clients/tcp_controller.py`
- TCP pøíkazy pro Projects Manager:
  - `start:<project_path>`
  - `stop:<project_path>`
  - `status:<project_path>`
- Odpovìdi se oèekávají dle dokumentace PM (done, running, stopped, ...)

## Tok dat (zjednodušenì)

1. GUI/CLI sestaví `AppConfig`
2. ConnectionManager vytvoøí klienta a provede `ping`
3. Runner skenuje složku › fronta
4. Worker odesílá obrázek + `data` pøes REST/SDK
5. Po úspìchu uloží:
   - `last_context`
   - `Production_Mode` indikaci
   - `last_data`
6. JSONL log + text log

## Sestavení `data`

`data` se skládá z volitelných èástí:
- `Include string` › uživatelský prefix
- `Include filename` › `path.stem`
- `Include timestamp` › `_HH_MM_SS_`

Výsledný `data` je vždy jeden øetìzec bez oddìlovaèù (kromì timestampu).

## Production Mode indikace

Z posledního úspìšného `context` se ète `Production_Mode`:
- `True` › ON
- `False` › OFF
- není k dispozici › Unknown

## PM TCP policy

`connection.policy`:
- `off`: pouze status/ping
- `auto_start`: startuje projekt pøi Connect
- `auto_start_stop`: startuje pøi Connect a stopuje pøi Disconnect
- `auto_restart`: pøi odmítnutí pøipojení stop/start + retry (5×, 30s)

TCP policy funguje jen když:
- `projects_manager.tcp_enabled = true`
- `project_path` není prázdný

## Logy

- `logs/app.log`: systémové logy + odesílané `data`
- `logs/results.jsonl`: per-image záznamy (timestamp, filename, data, status, ok_nok)

## Konfigurace

Základní config je v `configs/config.example.yaml`.
GUI si ukládá poslední nastavení do `~/.pektool_gui.yaml`.

## Omezení

- `data` je interní argument projektu a v REST odpovìdi se bìžnì nevrací.
- Project Manager HTTP (port 7000) poskytuje list/status, ne start/stop.
- PM TCP musí být aktivní v Projects Manager Settings.