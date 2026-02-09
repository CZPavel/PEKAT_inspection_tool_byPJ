# PEKAT Inspection Tool - Uzivatelsky navod

Tento dokument popisuje ovladani aplikace z pohledu uzivatele.

## Hlavni okno (Konfigurace)

### 1) Rezim (SDK/REST)
- `REST` je default
- `SDK` pouzijte pouze pokud bezi lokalne s dostupnym SDK

### 2) Host / Port
- IP adresa a port beziciho projektu
- Default: `127.0.0.1` / `8000`

### 3) Project path
- Cesta k projektu (potrebna pouze pro PM TCP rizeni)

### 4) Slozka / Podslozky / Soubory
- **Slozka**: hlavni vstupni slozka
- **Zahrnout podslozky**: zda skenovat i podadresare
- **Vybrat soubory**: lze odeslat konkretni soubory

### 5) Rezim behu
- `loop`: dokola pres snapshot souboru
- `once`: jednorazove a konec
- `initial_then_watch`: posle aktualni a pak sleduje nove

### 6) Prodleva (ms)
- Pauza mezi odesilanymi snimky

### 7) Data (co se posila do PEKAT jako `data`)
- **Include filename**: nazev souboru bez pripony
- **Include timestamp**: prida `_HH_MM_SS_`
- **Include string**: povoli vlastni text

### 8) API key
- Tlacitko **API key setup** otevre dialog pro nastaveni
- Ponechte prazdne, pokud projekt neni zabezpeceny

### 9) Project control (PM TCP)
- **PM TCP enabled**: zapne TCP rizeni projektu
- **Host / Port**: TCP server Projects Manageru (typicky 7002)
- **Policy**:
  - `Off (status only)` - pouze status/ping
  - `Auto-start on Connect` - start pri Connect
  - `Auto-start + Auto-stop on Disconnect` - start/stop
  - `Automatic restart` - pri odmitnuti pripojeni stop/start + retry

Poznamka: Funguje pouze pokud je TCP server v Projects Manageru aktivni.

### 10) Tlacitka
- **Connect**: pripoji se k bezicimu projektu
- **Disconnect**: odpoji se
- **Start sending**: zahaji odesilani snimku (vyzaduje Connect)
- **Stop sending**: zastavi odesilani

### 11) Indikatory
- **Connection**: stav pripojeni (connected/reconnecting/error)
- **Sending**: stav odesilani
- **Production Mode**:
  - ON -> projekt bezi v production rezimu
  - OFF -> projekt neni v production rezimu
  - Unknown -> zatim nebyl zadny validni context
- **Data preview**: posledni odeslany `data` string
- **Odeslano**: pocet odeslanych snimku
- **Reset counter and list**: rucne resetuje pocitadlo

## Log zalozka

- Zobrazuje prubezny log aplikace
- Dulezite udalosti: pripojeni, restart, odesilani, chyby

## Doporuceny postup

1. Nastavit Host/Port
2. Pokud pouzivate PM TCP, vyplnit Project path a zapnout PM TCP
3. Kliknout **Connect**
4. Kliknout **Start sending**

## Tipy

- Pokud se objevuje `reconnecting`, overte, ze projekt opravdu bezi na danem portu.
- Pro PM TCP funkce musi byt aktivni TCP server v Projects Manageru.
- `data` se nevraci v REST odpovedi - je dostupna uvnitr projektu (Code module).