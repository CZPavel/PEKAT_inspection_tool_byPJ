# Sound camera

Tento dokument shrnuje prakticke profily pro kartu `Sound camera` v GUI.

## Rychly start

1. Otevri kartu `Sound camera`.
2. Zapni `Povolit Sound camera`.
3. Vyber `Pristup` (`Payload`, `Lissajous`, `Classic`).
4. Vyber `Zdroj` (`Loopback`, `Microphone`, `Sine`).
5. Nastav `FPS` a `Delka snimku`.
6. Otestuj `Start preview`, pak `Start sending`.

## FPS a kontinuita

- GUI pouziva `FPS` (frames per second).
- Interni perioda je `interval_sec = 1 / FPS`.
- Pro `Payload` a `Lissajous` plati:
  - `interval_sec >= window_sec`
  - ekvivalentne `FPS <= 1 / window_sec`
- Pro `Classic` je overlap povoleny:
  - `overlap_sec = max(0, window_sec - interval_sec)`
  - `overlap_pct = 100 * overlap_sec / window_sec`
  - `gap_sec = max(0, interval_sec - window_sec)`
  - GUI zobrazuje `Stride | Overlap` nebo `Stride | Gap`.

## Payload profile

Doporucene pro rychlou diagnostiku datovych vzoru:

- `Pristup`: `Payload`
- `frame_seconds`: `1.0`
- `overlap`: `50 %`
- `style_mode`: `stack3`
- `y_repeat`: `4`
- `variant`: `none`

Payload ma samostatne prepinace overlay:

- `Zobrazit rastr`
- `Zobrazit casove znacky`
- `Zobrazit hranice stacku`
- `Zobrazit popisek`

Vsechny lze vypnout, pokud chces cisty snimek bez dokresleni.

## Lissajous profile

Vhodne pro periodicitu a tvar signalu:

- `Pristup`: `Lissajous`
- `tau`: `5` (nebo `both` pro vedle sebe tau=1 a tau=5)
- `width/height`: `512/512`
- `accum`: `avg`
- `point_size_step`: `2`
- `value_mode`: `radial`
- `rotation`: `none`

## Classic profile

Vhodne pro spektralni kontrolu:

- `Pristup`: `Classic`
- `Styl`: `CLASSIC` | `FUSE7` | `FUSE4_base`
- `Osa Y` (jen pro styl `CLASSIC`): `Linear` | `Log` | `Mel`
- `preset`: `classic_fhd` nebo `classic_impulse`
- `W/H`: `1024/768` (nebo dle potreby)
- `colormap`: `gray` nebo `turbo`
- `detail_mode`: `highpass` / `edgesobel`
- pokrocile STFT volby jsou v sekci `Pokrocile nastaveni`:
  - `N FFT`, `Win ms`, `Hop ms`, `Top dB`, `Fmax`, `Freq interp`

Poznamka: preset se chova jako sablona GUI, ne jako tvrdy runtime lock.

Pro `FUSE7/FUSE4_base` jsou dostupne dalsi parametry:
- `fuse7_profile`
- `scale_mode`, `p_lo`, `p_hi`
- `n_mels_hue`, `n_mels_layers`
- `norm_p`, `flux_gain`, `edge_gain`
- `freq_green_bias`, `edge_base_alpha`

## Send mode

### Save+Send

- Snimky se ukladaji do `snapshot_dir`.
- Do analyzy jde cesta na ulozeny PNG.
- Vzdy se ulozi a odesle jen jeden snimek podle aktualne vybraneho stylu.

### Send-only

- Snimky jdou primo in-memory.
- Source move/delete akce jsou pri behu vypnute.
- Artifacty (JSON/processed) lze ponechat zapnute.
- Odesila se vzdy jen jeden snimek podle aktualne vybraneho stylu.

## Preview workflow

- `Start preview` spusti samostatny preview worker i bez odesilani.
- Pri aktivnim preview se zmeny nastaveni aplikuji automaticky (live reconfigure, debounce).
- Pri `Start sending` se standalone preview zastavi a preview okno dostava frame z runner callbacku.

## Windows troubleshooting

### Loopback nevraci data

- Vyzkousej `Backend policy = Prefer pyaudiowpatch`.
- Pokud backend neni dostupny, pouzij fallback `sounddevice`.
- Over `Stereo Mix` pokud jej ovladac podporuje.

### Snapshot slozka nejde vytvorit

- V `Save+Send` musi byt platny zapisovatelny adresar.

### Zarizeni neni v seznamu

- Klikni `Obnovit zarizeni`.
- U `Loopback` zkus `Default loopback output` nebo explicitni endpoint.

### Classic preview/sending hlasi chybejici scipy

- Classic rezim vyzaduje `scipy>=1.10`.
- Pouzij stejny interpreter jako aplikace:
  - `"C:\\Users\\P_J\\AppData\\Local\\Programs\\Python\\Python313\\python.exe" -m pip install "scipy>=1.10"`
