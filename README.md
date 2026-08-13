# MHA — Mitsubishi WF-RAC for Home Assistant

[![Validate](https://github.com/shockwave9315/MHA/actions/workflows/validate.yml/badge.svg)](https://github.com/shockwave9315/MHA/actions/workflows/validate.yml)

Fork integracji **Mitsubishi Heavy Industries WF-RAC** dla Home Assistant, rozwijany pod kątem stabilnej pracy lokalnej, lepszej diagnostyki i testów regresyjnych.

**Nie dotyczy Mitsubishi Electric / MELCloud.**

## Stan projektu

Bazą runtime pozostaje **2026.9.4-beta1**, uzupełniona selektywnie o istotne poprawki z późniejszego upstreamu 2026.9.4 oraz własne poprawki tego forka.

Zmiany z upstreamu nie są synchronizowane automatycznie. Najpierw są porównywane z kodem forka, a następnie przechodzą testy i review.

Testowany lokalnie m.in. na module:

`WF-RAC / MCU 131 / wireless 010`

Integracja komunikuje się z modułem lokalnie przez HTTP/HTTPS. Opcjonalne sprawdzanie dostępności nowego firmware wymaga połączenia z Internetem.

## Najważniejsze zmiany w tym forku

| Obszar | Zachowanie |
|---|---|
| Krótkie zaniki komunikacji | pojedyncze błędy nie powodują natychmiastowego `unavailable` |
| Availability | urządzenie jest oznaczane jako niedostępne dopiero po kilku kolejnych nieudanych odpytywaniach; minimum 3 |
| HTTP / HTTPS | integracja zachowuje działający transport i potrafi ponownie wykryć właściwy sposób połączenia |
| Kolejka komend | zmiany wykonane blisko siebie są scalane, żeby nie nadpisywały się wzajemnie |
| Odczyty statusowe | Service Data i Home Leave korzystają z ramek tylko do odczytu |
| Home Leave | odczyt statusu nie może już zgubić oczekującej komendy sterującej |
| Service Data | retry po odrzuconym zapytaniu oraz świeżość liczona osobno dla każdego pola |
| Temperatury wymiennika | THI-R1 / THI-R3 korzystają z przeliczenia NTC i działają również podczas grzania |
| Target temperature offset | spójne offsety zależne od trybu |
| Energy Usage Total | poprawione liczenie po resecie licznika bieżącego cyklu |
| Język polski | pełne tłumaczenie konfiguracji, opcji i encji |
| CI | HACS + Hassfest + Pytest |

## Instalacja przez HACS

Dodaj repozytorium jako **Custom repository**:

`https://github.com/shockwave9315/MHA`

Typ: **Integration**.

Następnie zainstaluj oznaczony tag/release tego forka i uruchom ponownie Home Assistant.

Jeśli Home Assistant działa po polsku, konfiguracja, opcje i nazwy encji będą wyświetlane po polsku.

## Opcje integracji

| Opcja | Znaczenie |
|---|---|
| Host (IP) | lokalny adres IP modułu WF-RAC |
| Availability retry limit | liczba kolejnych nieudanych odpytań przed oznaczeniem urządzenia jako niedostępne; minimum 3 |
| Firmware Update Check (Online) | opcjonalne sprawdzanie dostępności nowszego firmware |
| Service Data | dodatkowe lokalne dane diagnostyczne |
| Create swing mode selectors | ustawienie dostępne tylko podczas pierwszego dodawania urządzenia; tworzy osobne selektory poziomego i pionowego kierunku nawiewu. Późniejsza zmiana wymaga usunięcia i ponownego dodania urządzenia |
| Indoor Temp. Sensor Offset | korekta temperatury wewnętrznej |
| Outdoor Temp. Sensor Offset | korekta temperatury zewnętrznej |
| Target Temp. Offset | ogólna korekta temperatury zadanej |
| Target Temp. Offset (Cooling) | osobna korekta temperatury zadanej dla chłodzenia |
| Target Temp. Offset (Heating) | osobna korekta temperatury zadanej dla grzania |

## Service Data

Service Data jest opcjonalne i działa lokalnie. Odczyt danych diagnostycznych nie powinien zmieniać power, trybu pracy, nawiewu, temperatury zadanej ani położenia żaluzji.

| Kod | Dane | Status |
|---|---|---|
| `0x11` | Compressor Frequency | potwierdzone |
| `0x90` | Operating Current | potwierdzone |
| `0x85` | Discharge / Hot Gas Temperature | potwierdzone |
| `0x13` | EEV pulses | potwierdzone |
| `0x81` | THI-R1 indoor coil | raw + konwersja NTC |
| `0x87` | THI-R3 indoor coil outlet | raw + konwersja NTC |
| `0x82` | THO-R1 outdoor coil | raw, skala nieznana |
| `0xB1` | TDSH | raw, skala do potwierdzenia |
| `0x7C` | Protection number | raw / zależne od jednostki |

`EEV Position %` jest normalizacją wartości `0..255` do `0..100%`. Nie jest skalibrowanym procentem mechanicznego otwarcia zaworu. Źródłem pozostaje `EEV Pulses`.

Freshness danych serwisowych jest liczony osobno dla każdego pola. Jeśli jedno pole nadal przychodzi, a inne przestanie być raportowane, brakujący sensor po określonym czasie przejdzie w `unknown` zamiast pokazywać starą wartość jako aktualną.

## Ważne

To jest fork testowy rozwijany na realnym sprzęcie. Dla niepotwierdzonych danych preferujemy `unknown` lub wartość surową zamiast zgadywania znaczenia sensora.

Dodatkowa dokumentacja techniczna znajduje się w katalogu `docs/`.
