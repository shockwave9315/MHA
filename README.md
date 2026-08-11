# MHA — Mitsubishi WF-RAC for Home Assistant

[![Validate](https://github.com/shockwave9315/MHA/actions/workflows/validate.yml/badge.svg)](https://github.com/shockwave9315/MHA/actions/workflows/validate.yml)

Eksperymentalny, utwardzony fork integracji **Mitsubishi Heavy Industries WF-RAC** dla Home Assistant.

Bazuje na projekcie [blues-sechseck/Mitsubishi-WF-RAC-Integration](https://github.com/blues-sechseck/Mitsubishi-WF-RAC-Integration), ale ten fork skupia się na dwóch rzeczach:

- odporności na realne zachowanie modułów WF-RAC,
- dalszym reverse engineeringu lokalnego protokołu i danych serwisowych.

**Nie dotyczy Mitsubishi Electric / MELCloud.**

## Stan projektu

Baza runtime: **upstream 2026.9.4-beta1** + własne poprawki i testy regresyjne.

Testowany lokalnie m.in. na module:

`WF-RAC / MCU 131 / wireless 010`

Na tej wersji potwierdzono, że operation-data dla sprężarki działa poprawnie — mimo wcześniejszych raportów, że `0x11` i `0x90` mogą zwracać stałe zero.

## Co zostało poprawione w tym forku

| Obszar | Stan |
|---|---|
| Krótkie zaniki WF-RAC / okresowy reconnect Wi-Fi | nie są traktowane jak awaria konta |
| HTTP / HTTPS recovery | zachowanie sprawdzonego transportu + bezpieczne rediscovery |
| Błędnie zapamiętany protokół | recovery także gdy zły transport odpowiada HTTP 4xx/5xx |
| Logowanie | warning dopiero przy realnej zmianie stanu / niedostępności |
| Service Data | fresh read przed pełnym `setAirconStat` |
| Service Data retry | ponowny fresh read przed każdym retry; brak stale-state write-back |
| Freshness Service Data | śledzenie per pole, nie jednym timestampem dla całego bloku |
| Home Leave | poprawione signed temperatures i zakresy |
| Target temperature offset | spójne offsety per tryb w climate i sensorze |
| Energy Usage Total | poprawione liczenie po resecie licznika bieżącego cyklu |
| CI | HACS + Hassfest + Pytest |

Kod był dodatkowo przepuszczany przez wielokrotne review Codexa; znalezione edge-case'y zostały pokryte testami regresyjnymi.

## Co już odczytujemy

### Bez dodatkowego requestu

- temperatura wewnętrzna i zewnętrzna,
- setpoint, tryb, fan, żaluzje,
- błędy jednostki,
- `Compressor Demand` — czy ta konkretna jednostka wewnętrzna żąda pracy sprężarki,
- licznik energii bieżącego cyklu,
- Home Leave / Vacant / podstawowa diagnostyka modułu.

### Service Data

Service Data jest opcjonalne i korzysta z generic operation-data channel.

| Kod | Dane | Status |
|---|---|---|
| `0x11` | Compressor Frequency | ✅ potwierdzone |
| `0x90` | Operating Current | ✅ potwierdzone |
| `0x85` | Discharge / Hot Gas Temperature | ✅ potwierdzone |
| `0x13` | EEV pulses | ✅ potwierdzone |
| `0x81` | THI-R1 indoor coil | ✅ raw + częściowa konwersja |
| `0x87` | THI-R3 indoor coil outlet | ✅ raw + częściowa konwersja |
| `0x82` | THO-R1 outdoor coil | ✅ raw, skala nieznana |
| `0xB1` | TDSH | 🟡 raw, znaczenie/skala do potwierdzenia |
| `0x7C` | Protection number | 🟡 request istnieje, odpowiedź zależna od jednostki |

`EEV Position %` jest wyłącznie normalizacją `0..255 -> 0..100%`. Nie jest skalibrowanym procentem mechanicznego otwarcia zaworu. Źródłem pozostaje `EEV Pulses`.

## Co wiemy o protokole

WF-RAC jest w praktyce mostkiem:

`Home Assistant -> HTTP/HTTPS -> WF-RAC -> RL78 -> CNS/SPI -> klimatyzator`

Najważniejsza część to generic variable segment:

`[CODE, OP1, OP2, OP3]`

- `OP1 = 0xFF` — odczyt / request,
- `OP1 = 0x10` — odpowiedź/status,
- `OP1 = 0x00` — write do sterownika AC.

**Eksploracja w tym forku ma pozostać read-only: `OP1=0xFF`.** Nie zgadujemy komend zapisu do nieznanych kodów.

Pełny opis warstw i ramek: [`docs/wf-rac-module-reference.md`](docs/wf-rac-module-reference.md).

## Co można dodać od razu

| Funkcja | Dlaczego |
|---|---|
| Controller Room Temperature (`DB3`) | już jedzie w każdym zwykłym statusie; zero dodatkowego ruchu |
| Evaporator Superheat | derived: `THI-R3 - THI-R1` w potwierdzonym zakresie chłodzenia |
| Raw state bytes | pasywne logowanie nieznanych bitów `DB5`, `state[13..17]` |
| Operation Data Explorer | bezpieczne testowanie kodów wyłącznie przez `OP1=0xFF` |

## Co warto teraz zbadać

| Kod | Hipoteza / cel |
|---|---|
| `0x0C` | Defrost |
| `0x1E` | total indoor / compressor run hours |
| `0x1F` | indoor / outdoor fan speed |
| `0x0D` | unknown |
| `0x21` | unknown |
| `0x32` | unknown |
| `0x34` | unknown, korzysta także z `OP3` — możliwa wartość wielobajtowa |
| `0x35` | unknown |

Dla nieznanych kodów najpierw zapisujemy pełne raw `[code, op1, op2, op3]` i korelujemy je z pracą urządzenia. Nazwa sensora pojawia się dopiero po potwierdzeniu zachowania na sprzęcie.

## Kierunek

Celem nie jest przepisywanie upstreamu.

**Upstream** rozwija obsługę modeli, funkcje i reverse engineering protokołu.  
**Ten fork** bierze te zmiany, przepuszcza je przez diff/review/testy i dokłada hardening oraz eksperymentalną diagnostykę.

Docelowo chcemy dojść do lokalnego panelu serwisowego pokazującego m.in.:

`demand -> Hz -> A -> EEV -> coil temperatures -> discharge temperature -> energy -> protection/defrost`

bez chmury i bez wymiany WF-RAC na ESP.

## Instalacja przez HACS

Dodaj jako **Custom repository**:

`https://github.com/shockwave9315/MHA`

Typ: **Integration**.

Następnie instaluj oznaczone tagi/release'y tego forka i restartuj Home Assistant.

## Ważne

To jest fork testowy rozwijany na realnym sprzęcie. Nowe, niepotwierdzone dane są wystawiane jako raw albo pozostają wyłączone domyślnie — wolimy `unknown` niż ładnie wyglądającą, ale zmyśloną wartość.
