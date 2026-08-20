# MHA — Mitsubishi WF-RAC for Home Assistant

[![Validate](https://github.com/shockwave9315/MHA/actions/workflows/validate.yml/badge.svg)](https://github.com/shockwave9315/MHA/actions/workflows/validate.yml)

Fork integracji **Mitsubishi Heavy Industries WF-RAC** dla Home Assistant, rozwijany pod kątem stabilnej pracy lokalnej, lepszej diagnostyki i testów regresyjnych.

**Nie dotyczy Mitsubishi Electric / MELCloud.**

## Stan projektu

Aktualny runtime zawiera selektywnie podciągniętą architekturę upstream **2026.9.5-beta2** oraz poprawki specyficzne dla tego forka. Zmiany z upstreamu nie są synchronizowane automatycznie — najpierw są porównywane z naszym kodem, a następnie przechodzą testy i review.

Testowany lokalnie m.in. na module:

`WF-RAC / MCU 131 / wireless 010`

Integracja komunikuje się z modułem lokalnie przez HTTP/HTTPS. Opcjonalne sprawdzanie dostępności nowego firmware jest jedyną funkcją wymagającą połączenia z Internetem.

## Najważniejsze zachowanie

| Obszar | Zachowanie |
|---|---|
| Krótkie zaniki komunikacji | pojedyncze błędy nie powodują natychmiastowego `unavailable` |
| Availability | urządzenie jest oznaczane jako niedostępne dopiero po kilku kolejnych nieudanych odpytywaniach; minimum 3 |
| HTTP / HTTPS | integracja zachowuje działający transport i potrafi odzyskać właściwy protokół także w tym samym wywołaniu |
| Kolejka komend | zmiany wykonane blisko siebie są scalane, żeby nie nadpisywały się wzajemnie |
| Odczyty statusowe | operation data i Home Leave używają ramek bez bitów SET |
| Home Leave | STATUS nie może połknąć ani wyprzedzić oczekującej komendy SET; signed temperatures są zachowane |
| Operation data | requesty są demand-driven — pobierane są tylko kody potrzebne przez aktywne encje |
| Freshness operation data | świeżość liczona osobno dla każdego pola, więc jeden żywy sensor nie podtrzymuje innego zamrożonego odczytu |
| Temperatury wymiennika | THI-R1 / THI-R3 korzystają z przeliczenia NTC i działają również podczas grzania |
| Target temperature offset | spójne offsety zależne od trybu |
| Energy Usage Total | poprawione liczenie po resecie licznika bieżącego cyklu |
| Diagnostyka HA | bezpieczny, zredagowany eksport danych diagnostycznych |
| Repairs | pełna tabela kont WF-RAC jest zgłaszana jako problem w Home Assistant Repairs |
| Język polski | tłumaczenie konfiguracji, reconfigure, błędów, Repairs, opcji i encji |
| CI | HACS + Hassfest + Pytest + mypy `--strict` |

## Instalacja przez HACS

Dodaj repozytorium jako **Custom repository**:

`https://github.com/shockwave9315/MHA`

Typ: **Integration**.

Następnie zainstaluj oznaczony tag/release tego forka i uruchom ponownie Home Assistant.

## Konfiguracja i opcje

Zmiana **nazwy, hosta/IP lub portu** odbywa się przez **Reconfigure**. Nowe dane połączenia są sprawdzane z urządzeniem przed zapisaniem, więc błędny adres nie zostanie zapisany jako zwykła opcja.

W zwykłym **Configure / Options** pozostają:

| Opcja | Znaczenie |
|---|---|
| Availability retry limit | liczba kolejnych nieudanych odpytań przed oznaczeniem urządzenia jako niedostępne; minimum 3 |
| Firmware Update Check (Online) | opcjonalne sprawdzanie dostępności nowszego firmware |
| Indoor Temp. Sensor Offset | korekta temperatury wewnętrznej |
| Outdoor Temp. Sensor Offset | korekta temperatury zewnętrznej |
| Target Temp. Offset | ogólna korekta temperatury zadanej |
| Target Temp. Offset (Cooling) | osobna korekta temperatury zadanej dla chłodzenia; puste = użyj wartości ogólnej |
| Target Temp. Offset (Heating) | osobna korekta temperatury zadanej dla grzania; puste = użyj wartości ogólnej |

Selektory poziomego/pionowego kierunku nawiewu i prędkości wentylatora są zawsze rejestrowane jako encje. Dla starszych wpisów konfiguracji wcześniejszy wybór tylko decyduje, czy są domyślnie włączone — można je później włączać i wyłączać normalnie z rejestru encji bez usuwania integracji.

## Operation data / dane serwisowe

Nie ma już globalnego przełącznika **Service Data**. Encje operation-data są rejestrowane jako diagnostyczne i domyślnie wyłączone. **Włączenie konkretnej encji powoduje pobieranie tylko kodu/kodów potrzebnych tej encji.** Jeżeli żadna z tych encji nie jest aktywna, integracja nie wykonuje dodatkowego requestu operation-data.

| Kod | Dane | Status |
|---|---|---|
| `0x11` | Compressor Frequency | potwierdzone + raw |
| `0x90` | Operating Current | potwierdzone + raw |
| `0x85` | Discharge / Hot Gas Temperature | potwierdzone + raw |
| `0x13` | EEV pulses / relative position | potwierdzone |
| `0x81` | THI-R1 indoor coil | raw + konwersja NTC |
| `0x87` | THI-R3 indoor coil outlet | raw + konwersja NTC |
| `0x82` | THO-R1 outdoor coil | raw, skala nieustalona |
| `0xB1` | TDSH | raw, znaczenie/skala do potwierdzenia |
| `0x7C` | Protection number | raw; wygląda na protective stop, nie zwykły overload clamp |

`EEV Position %` jest normalizacją wartości `0..255` do `0..100%`. Nie jest skalibrowanym procentem mechanicznego otwarcia zaworu. Źródłem pozostaje `EEV Pulses`.

Raw sensory pozostają domyślnie wyłączone i są przeznaczone głównie do reverse engineeringu. Freshness jest liczony per pole: jeżeli np. częstotliwość sprężarki nadal przychodzi, a prąd przestanie być raportowany, sensor prądu po czasie przejdzie w `unknown` zamiast wisieć ze starą wartością.

## Diagnostyka i Repairs

Home Assistant może pobrać diagnostykę integracji zawierającą m.in. stan urządzenia, sposób połączenia, firmware, capabilities i bieżący stan `Aircon`. Dane pozwalające zidentyfikować lub kontrolować jednostkę — host/IP, `operator_id`, `device_id` i `airco_id` — są redagowane przed eksportem.

Jeżeli WF-RAC ma pełną wewnętrzną tabelę zarejestrowanych kont i ponowna rejestracja Home Assistanta nie może się udać, integracja tworzy problem w **Ustawienia → System → Naprawy**. Problem znika po udanej rejestracji.

## Ważne

To jest fork testowy rozwijany na realnym sprzęcie. Dla niepotwierdzonych danych preferujemy `unknown` lub wartość surową zamiast zgadywania znaczenia sensora.

Dodatkowa dokumentacja techniczna znajduje się w katalogu `docs/`.
