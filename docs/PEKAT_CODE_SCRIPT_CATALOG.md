# PEKAT CODE Script Catalog (v3.6)

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
3. Manual override metadata for selected scripts
4. Generated fallback

## Scripts

| Soubor | Kategorie | K cemu slouzi | Co dela | Klicove context | Zavislosti | Source |
|---|---|---|---|---|---|---|
| AI_TRIGGER_V06_TESTED.txt | Flow control | Gate pro propouĹˇtÄ›nĂ­ snĂ­mkĹŻ dle tĹ™Ă­d/OK-NG | Debounce, mapovĂˇnĂ­ OK/NG, okno CAPTURE, Ĺ™Ă­zenĂ­ pĹ™es Operator View, stav v __main__ | detectedRectangles, result, operatorInput, exit | â€“ | xlsx |
| AUTO_HDR.txt | Zprac. obrazu | Stabilizace expozice/kontrastu | Linear stretch, gamma/CLAHE/blur-division, blend; gray/RGB, 8/16 bit | image, (volit. operatorInput) | cv2, numpy | xlsx |
| CUT_ON_DETECTED.txt | Zprac. obrazu | OĹ™ez podle 1. detekce | Pokud nenĂ­ pĹ™esnÄ› 1 detekce â†’ exit=True; jinak oĹ™Ă­zne | detectedRectangles, image, exit | cv2, numpy | xlsx |
| DEL_CLASS.txt | Detekce | FiltrovĂˇnĂ­ tĹ™Ă­d | OdstranĂ­/ponechĂˇ vybranĂ© tĹ™Ă­dy v seznamu detekcĂ­ | detectedRectangles | â€“ | xlsx |
| FLOW_ON_DETECTED.txt | Flow control | PokraÄŤuj jen kdyĹľ jsou pĹ™Ă­tomnĂ© dvÄ› tĹ™Ă­dy | Kontroluje koexistenci (napĹ™. â€žLevĂˇâ€ś & â€žPravĂˇâ€ś), jinak exit=True | detectedRectangles, exit | â€“ | xlsx |
| LOGO_DATE_TIME_TO_IMAGE.txt | Ukladani/overlay | Branding & timestamp | VloĹľĂ­ PNG logo + datum/ÄŤas/text s kotvami/offsety | image, operatorInput | cv2, numpy | xlsx |
| MEASURE_DETECTED_DISTANCE.txt | Mereni | VzdĂˇlenost mezi stĹ™edy dvou tĹ™Ă­d | VĂ˝bÄ›r kandidĂˇtĹŻ, mÄ›Ĺ™enĂ­ v pxâ†’mm, vykreslenĂ­ spojnice a hodnoty | detectedRectangles, image | cv2, numpy | xlsx |
| OVLADANI_MAJAKU_IFMDV2131.txt | IO-Link | OvlĂˇdĂˇnĂ­ majĂˇku IFM DV2131 | SklĂˇdĂˇ HEX PDOut (barva, blikĂˇnĂ­, bzuÄŤĂˇk) dle result/UI, REST na AL1306 | result, (volit. operatorInput) | requests | xlsx |
| PYZBAR_BARCODE_READER.txt | Detekce | Dekodovani carovych a 2D kodu pomoci pyzbar | V ROI vytvori vice predzpracovanych variant (upscale/CLAHE/Otsu/adaptive/invert), dekoduje pyzbar, zapisuje vystup do context['barcode'] a context['barcode_debug'], volitelne kresli overlay a debug vystupy. | image, barcode, barcode_debug | pyzbar, cv2, numpy | manual |
| RESULT_FILTER.txt | Flow control | Hystereze vĂ˝sledku | PoÄŤty po sobÄ› jdoucĂ­ch OK/NG, pĹ™epĂ­Ĺˇe result aĹľ po splnÄ›nĂ­ prahu | result, operatorInput | â€“ | xlsx |
| RESULT_MAKER.txt | Flow control | RychlĂ© vynucenĂ­ vĂ˝sledku | NastavĂ­ result=True (OK) â€“ test/obchvat | result | â€“ | xlsx |
| ROZSIRENI_SNIMKU_OKRAJE.txt | Zprac. obrazu | Padding obrazu | PĹ™idĂˇ okraje (barva/velikost), zachovĂˇ typ/datovĂ˝ rozsah | image | cv2, numpy | xlsx |
| SAVE_IMAGE_OKNOK_SIMPLE.txt | Ukladani | UklĂˇdĂˇnĂ­ surovĂ˝ch snĂ­mkĹŻ | UloĹľĂ­ do sloĹľek OK/NOK, nĂˇzev s ÄŤasem a top-1 tĹ™Ă­dou | image, result, detectedRectangles | cv2, pathlib, datetime | xlsx |
| SAVE_IMAGE_W_ANOT_OKNOK.txt | Ukladani | UklĂˇdĂˇnĂ­ anotovanĂ˝ch snĂ­mkĹŻ | VykreslĂ­ detekce, barvĂ­ dle OK/NOK, uloĹľĂ­ do OK/NOK | image, detectedRectangles, result | cv2, pathlib, datetime | xlsx |
| SJEDNOCENI_2_UNIFIER.txt | Geometrie | ZarovnĂˇnĂ­ podle dvou tĹ™Ă­d | SpoÄŤte stĹ™edy, natoÄŤĂ­ obraz do horizontĂˇly (self-check), vyĹ™Ă­zne pevnĂ˝ vĂ˝Ĺ™ez | detectedRectangles, image | cv2, numpy, math | xlsx |
| SOBEL_IMAGE_FILTER.txt | Zprac. obrazu | ZvĂ˝raznÄ›nĂ­ hran | Gray â†’ rozostĹ™enĂ­ â†’ Sobel â‡I â†’ prahovĂˇnĂ­ â†’ vĂ˝stup gray/RGB | image | cv2, numpy | xlsx |
| STOP_IF_NOK.txt | Flow control | Zastavit vÄ›tev pĹ™i NG | KdyĹľ result=False, nastavĂ­ exit=True | result, exit | â€“ | xlsx |
| STOP_IF_OK.txt | Flow control | Zastavit vÄ›tev pĹ™i OK | KdyĹľ result=True, nastavĂ­ exit=True | result, exit | â€“ | xlsx |
| UNSHARP_LAPLAC.txt | Zprac. obrazu | DoostĹ™enĂ­ | Unsharp nebo Laplace; sĂ­la podle â€žVariance of Laplacianâ€ś; debug overlay | image | cv2, numpy | xlsx |
| VAIT_FOR_BUTTON.txt | IO-Link | ÄŚekĂˇnĂ­ na tlaÄŤĂ­tko/senzor | ÄŚte PDIn pĹ™es AL1306 ("00"=stop vÄ›tev, "01"=pokraÄŤuj) | exit, (volit. operatorInput) | requests | xlsx |
| ZASTAVENI_VETVE.txt | Flow control | OkamĹľitĂ© ukonÄŤenĂ­ | NastavĂ­ exit=True a konÄŤĂ­ | exit | â€“ | xlsx |

