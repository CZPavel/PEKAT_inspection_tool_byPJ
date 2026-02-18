# PEKAT CODE Script Catalog (v3.4)

Source synchronized from C:\VS_CODE_PROJECTS\SCRIPTY_PEKAT_CODE using destructive replace mode.

Metadata fields reflect XLSX table style:
- Soubor
- Kategorie
- K cemu slouzi
- Co dela
- Klicove context
- Zavislosti

Metadata source priority:
1. XLSX overview file
2. Supplemental TXT description file
3. Generated fallback

Note: PYZBAR_BARCODE_READER.txt is intentionally excluded from sync because the source file is empty.

## Scripts

| Soubor | Kategorie | K cemu slouzi | Co dela | Klicove context | Zavislosti | Source |
|---|---|---|---|---|---|---|
| AI_TRIGGER_V06_TESTED.txt | Flow control | Gate pro propouštění snímků dle tříd/OK-NG | Debounce, mapování OK/NG, okno CAPTURE, řízení přes Operator View, stav v __main__ | detectedRectangles, result, operatorInput, exit | – | xlsx |
| AUTO_HDR.txt | Zprac. obrazu | Stabilizace expozice/kontrastu | Linear stretch, gamma/CLAHE/blur-division, blend; gray/RGB, 8/16 bit | image, (volit. operatorInput) | cv2, numpy | xlsx |
| CUT_ON_DETECTED.txt | Zprac. obrazu | Ořez podle 1. detekce | Pokud není přesně 1 detekce → exit=True; jinak ořízne | detectedRectangles, image, exit | cv2, numpy | xlsx |
| DEL_CLASS.txt | Detekce | Filtrování tříd | Odstraní/ponechá vybrané třídy v seznamu detekcí | detectedRectangles | – | xlsx |
| FLOW_ON_DETECTED.txt | Flow control | Pokračuj jen když jsou přítomné dvě třídy | Kontroluje koexistenci (např. „Levá“ & „Pravá“), jinak exit=True | detectedRectangles, exit | – | xlsx |
| LOGO_DATE_TIME_TO_IMAGE.txt | Ukladani/overlay | Branding & timestamp | Vloží PNG logo + datum/čas/text s kotvami/offsety | image, operatorInput | cv2, numpy | xlsx |
| MEASURE_DETECTED_DISTANCE.txt | Mereni | Vzdálenost mezi středy dvou tříd | Výběr kandidátů, měření v px→mm, vykreslení spojnice a hodnoty | detectedRectangles, image | cv2, numpy | xlsx |
| OVLADANI_MAJAKU_IFMDV2131.txt | IO-Link | Ovládání majáku IFM DV2131 | Skládá HEX PDOut (barva, blikání, bzučák) dle result/UI, REST na AL1306 | result, (volit. operatorInput) | requests | xlsx |
| RESULT_FILTER.txt | Flow control | Hystereze výsledku | Počty po sobě jdoucích OK/NG, přepíše result až po splnění prahu | result, operatorInput | – | xlsx |
| RESULT_MAKER.txt | Flow control | Rychlé vynucení výsledku | Nastaví result=True (OK) – test/obchvat | result | – | xlsx |
| ROZSIRENI_SNIMKU_OKRAJE.txt | Zprac. obrazu | Padding obrazu | Přidá okraje (barva/velikost), zachová typ/datový rozsah | image | cv2, numpy | xlsx |
| SAVE_IMAGE_OKNOK_SIMPLE.txt | Ukladani | Ukládání surových snímků | Uloží do složek OK/NOK, název s časem a top-1 třídou | image, result, detectedRectangles | cv2, pathlib, datetime | xlsx |
| SAVE_IMAGE_W_ANOT_OKNOK.txt | Ukladani | Ukládání anotovaných snímků | Vykreslí detekce, barví dle OK/NOK, uloží do OK/NOK | image, detectedRectangles, result | cv2, pathlib, datetime | xlsx |
| SJEDNOCENI_2_UNIFIER.txt | Geometrie | Zarovnání podle dvou tříd | Spočte středy, natočí obraz do horizontály (self-check), vyřízne pevný výřez | detectedRectangles, image | cv2, numpy, math | xlsx |
| SOBEL_IMAGE_FILTER.txt | Zprac. obrazu | Zvýraznění hran | Gray → rozostření → Sobel ∇I → prahování → výstup gray/RGB | image | cv2, numpy | xlsx |
| STOP_IF_NOK.txt | Flow control | Zastavit větev při NG | Když result=False, nastaví exit=True | result, exit | – | xlsx |
| STOP_IF_OK.txt | Flow control | Zastavit větev při OK | Když result=True, nastaví exit=True | result, exit | – | xlsx |
| UNSHARP_LAPLAC.txt | Zprac. obrazu | Doostření | Unsharp nebo Laplace; síla podle „Variance of Laplacian“; debug overlay | image | cv2, numpy | xlsx |
| VAIT_FOR_BUTTON.txt | IO-Link | Čekání na tlačítko/senzor | Čte PDIn přes AL1306 ("00"=stop větev, "01"=pokračuj) | exit, (volit. operatorInput) | requests | xlsx |
| ZASTAVENI_VETVE.txt | Flow control | Okamžité ukončení | Nastaví exit=True a končí | exit | – | xlsx |
