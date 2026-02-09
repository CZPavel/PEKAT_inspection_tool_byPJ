# PEKAT Inspection Tool – Uživatelský návod

Tento dokument popisuje ovládání aplikace z pohledu uživatele.

## Hlavní okno (Konfigurace)

### 1) Režim (SDK/REST)
- `REST` je default
- `SDK` použijte pouze pokud bìží lokálnì s dostupným SDK

### 2) Host / Port
- IP adresa a port bìžícího projektu
- Default: `127.0.0.1` / `8000`

### 3) Project path
- Cesta k projektu (potøebná pouze pro PM TCP øízení)

### 4) Složka / Podsložky / Soubory
- **Složka**: hlavní vstupní složka
- **Zahrnout podsložky**: zda skenovat i podadresáøe
- **Vybrat soubory**: lze odeslat konkrétní soubory

### 5) Režim bìhu
- `loop`: dokola pøes snapshot souborù
- `once`: jednorázovì a konec
- `initial_then_watch`: pošle aktuální a pak sleduje nové

### 6) Prodleva (ms)
- Pauza mezi odesílanými snímky

### 7) Data (co se posílá do PEKAT jako `data`)
- **Include filename**: název souboru bez pøípony
- **Include timestamp**: pøidá `_HH_MM_SS_`
- **Include string**: povolí vlastní text

### 8) API key
- Tlaèítko **API key setup** otevøe dialog pro nastavení
- Ponechte prázdné, pokud projekt není zabezpeèený

### 9) Project control (PM TCP)
- **PM TCP enabled**: zapne TCP øízení projektu
- **Host / Port**: TCP server Projects Manageru (typicky 7002)
- **Policy**:
  - `Off (status only)` – pouze status/ping
  - `Auto-start on Connect` – start pøi Connect
  - `Auto-start + Auto-stop on Disconnect` – start/stop
  - `Automatic restart` – pøi odmítnutí pøipojení stop/start + retry

Poznámka: Funguje pouze pokud je TCP server v Projects Manageru aktivní.

### 10) Tlaèítka
- **Connect**: pøipojí se k bìžícímu projektu
- **Disconnect**: odpojí se
- **Start sending**: zahájí odesílání snímkù (vyžaduje Connect)
- **Stop sending**: zastaví odesílání

### 11) Indikátory
- **Connection**: stav pøipojení (connected/reconnecting/error)
- **Sending**: stav odesílání
- **Production Mode**:
  - ON › projekt bìží v production režimu
  - OFF › projekt není v production režimu
  - Unknown › zatím nebyl žádný validní context
- **Data preview**: poslední odeslaný `data` string
- **Odesláno**: poèet odeslaných snímkù
- **Reset counter and list**: ruènì resetuje poèítadlo

## Log záložka

- Zobrazuje prùbìžný log aplikace
- Dùležité události: pøipojení, restart, odesílání, chyby

## Doporuèený postup

1. Nastavit Host/Port
2. Pokud používáte PM TCP, vyplnit Project path a zapnout PM TCP
3. Kliknout **Connect**
4. Kliknout **Start sending**

## Tipy

- Pokud se objevuje `reconnecting`, ovìøte, že projekt opravdu bìží na daném portu.
- Pro PM TCP funkce musí být aktivní TCP server v Projects Manageru.
- `data` se nevrací v REST odpovìdi – je dostupná uvnitø projektu (Code module).