# PEKAT Inspection Tool - Technical Overview

Tento dokument popisuje technickou architekturu aplikace, tok dat a volani do PEKAT VISION.

## Prehled architektury

Aplikace je rozdelena na ctyri vrstvy:

1. GUI/CLI vrstva - ovladani, validace vstupu, ulozeni nastaveni
2. Connection Manager - rizeni pripojeni, ping, PM TCP akce, stav pripojeni
3. Runner - skenovani souboru, fronta, odesilani snimku
4. Klienti - REST/SDK/TCP

## Moduly a odpovednosti

### `pektool/core/connection.py`
- Stav pripojeni: `disconnected | connecting | connected | reconnecting | error | disconnecting`
- Vytvari klienta (REST/SDK), provadi `ping`
- PM TCP ovladani (start/stop/status) dle policy
- Automatic restart: stop -> start -> cekani 30s -> ping (max 5 pokusu)
- Uklada `last_context`, `last_production_mode`, `last_data`
- Uklada `total_sent` + `sent_list` (poslane soubory)

### `pektool/core/runner.py`
- Skenuje slozku (polling) a plni frontu
- Odesila snimky pres `ConnectionManager.client`
- Neni-li pripojeno, ceka (zadne odesilani)
- Loguje hodnotu `data` a vysledek do JSONL

### `pektool/clients/rest_client.py`
- REST endpointy:
  - `GET /ping`
  - `POST /analyze_image` s PNG bytes
- Podporuje `data` jako URL parametr
- Pokud vstup neni PNG, provede konverzi pres OpenCV -> PNG
- Parsovani odpovedi:
  - `response_type=context` -> `response.json()`
  - jinak `ContextBase64utf` nebo `ImageLen` pri `context_in_body`

### `pektool/clients/sdk_client.py`
- SDK instance `Instance(...).analyze(...)`
- `data` je poslano pres argument `data=`

### `pektool/clients/tcp_controller.py`
- TCP prikazy pro Projects Manager:
  - `start:<project_path>`
  - `stop:<project_path>`
  - `status:<project_path>`
  - `switch:<project_path>`
- Podporuje optional request_id ve formatu `<id>.<command>:<project_path>`
- Odpovedi mohou obsahovat prefix `<id>.` (ten se odstrani)
- Ocekavane odpovedi: `done`, `running`, `stopped`, `starting`, `stopping`, `success`, `error:port`, `not-found`
- Chybne prikazy vraci `Unknown command` nebo `invalid-command` (server zavisi na verzi)

## Tok dat (zjednodusene)

1. GUI/CLI sestavi `AppConfig`
2. ConnectionManager vytvori klienta a provede `ping`
3. Runner skenuje slozku -> fronta
4. Worker odesila obrazek + `data` pres REST/SDK
5. Po uspechu ulozi:
   - `last_context`
   - `Production_Mode` indikaci
   - `last_data`
6. JSONL log + text log

## Sestaveni `data`

`data` se sklada z volitelnych casti:
- `Include string` -> uzivatelsky prefix
- `Include filename` -> `path.stem`
- `Include timestamp` -> `_HH_MM_SS_`

Vysledny `data` je vzdy jeden retezec bez oddelovacu (krome timestampu).

## Production Mode indikace

Z posledniho uspesneho `context` se cte `Production_Mode`:
- `True` -> ON
- `False` -> OFF
- neni k dispozici -> Unknown

## PM TCP policy

`connection.policy`:
- `off`: pouze status/ping
- `auto_start`: startuje projekt pri Connect
- `auto_start_stop`: startuje pri Connect a stopuje pri Disconnect
- `auto_restart`: pri odmitnuti pripojeni stop/start + retry (5x, 30s)

TCP policy funguje jen kdyz:
- `projects_manager.tcp_enabled = true`
- `project_path` neni prazdny

## Logy

- `logs/app.log`: systemove logy + odesilane `data`
- `logs/results.jsonl`: per-image zaznamy (timestamp, filename, data, status, ok_nok)

## Konfigurace

Zakladni config je v `configs/config.example.yaml`.
GUI si uklada posledni nastaveni do `~/.pektool_gui.yaml`.

## Omezeni

- `data` je interni argument projektu a v REST odpovedi se bezne nevraci.
- Project Manager HTTP (port 7000) poskytuje list/status, ne start/stop.
- PM TCP musi byt aktivni v Projects Manager Settings.
