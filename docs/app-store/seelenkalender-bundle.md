# GA und Seelenkalender Jahresbundle Entwurf

Stand: 10. Oktober 2026. Vorgesehen ist ein gemeinsamer Jahreszugang zu **Rudolf Steiner: Gesamtausgabe** und **Steiners Seelenkalender** für insgesamt **35 € pro Jahr** im deutschen App Store. Die Zuordnung zur GA-App und die jährliche Laufzeit sind aus dem Projektkontext abgeleitet und müssen noch bestätigt werden. Das Bundle ist noch nicht bei Apple beantragt oder eingerichtet.

## Angebot

| Eigenschaft | Vorgesehener Wert |
| --- | --- |
| Name | GA und Seelenkalender |
| Bundle-Art | Apple Single Developer Subscription Bundle |
| Inhalt | GA-Jahresabo und Seelenkalender-Jahreszugang |
| Laufzeit | Ein Jahr, automatisch verlängernd |
| Gesamtpreis | 35,00 € pro Jahr |
| Preis bei Einzelabos | 37,99 € pro Jahr |
| Ersparnis | 2,99 € pro Jahr |
| Erste Zielregion | Deutschland |
| Gemeinsame Zielplattformen | iPhone, iPad und Mac |
| Starttermin | Nach Apple-Konfiguration und erfolgreicher Prüfung beider Apps |

Der Bundle-Zugang umfasst die Funktionen beider enthaltenen Jahresabos. Eine Einführungsaktion ist für das Bundle noch nicht festgelegt. Die drei kostenlosen Einführungsmonate der Einzelabos sind keine Zusage für das Bundle.

## Produkte für Apple

Die Apple-API bestätigt am 10. Oktober 2026 folgende Produkte, Laufzeiten, Prüfzustände und deutschen Preise:

| App | Apple-App-ID | Enthaltenes Produkt | Apple-Produkt-ID | Laufzeit | Einzelpreis | Prüfzustand |
| --- | --- | --- | --- | --- | --- | --- |
| Rudolf Steiner: Gesamtausgabe | `6820947669` | `com.jonathankutscher.ga.annual` | `6820967918` | `ONE_YEAR` | 30,00 € | `WAITING_FOR_REVIEW` |
| Steiners Seelenkalender | `6780030656` | `de.jonathankutscher.seelenkalender.yearly` | `6780419642` | `ONE_YEAR` | 7,99 € | `APPROVED` |

Beide Produkte haben dieselbe Laufzeit. Die GA-App verwendet die Bundle-ID `com.jonathankutscher.ga`, Seelenkalender die Bundle-ID `de.jonathankutscher.seelenkalender`.

Das GA-Förderabo, der kostenlose GA-Jahreszugang und bestehende lebenslange Seelenkalender-Käufe sind keine Komponenten dieses Entwurfs.

## Einrichtung bei Apple

Apple verlangt für native Subscription Bundles StoreKit 2 und mindestens iOS 27, iPadOS 27, macOS 27 beziehungsweise tvOS 27 für den Kauf. Interessierte Entwickler beantragen den Zugang über ein Formular. Nach Genehmigung stimmt Apple die Produkte, Preise und den Starttermin ab und richtet das Bundle in einem gemeinsamen Veröffentlichungsdurchgang ein. Die derzeitige Mindestversion 26 der GA-App allein ermöglicht noch keinen Bundle-Kauf. [Apple-Anforderungen](https://developer.apple.com/app-store/subscriptions/bundles-and-suites/)

Das [Antragsformular](https://appstoreconnect.apple.com/forms/755b71a0-aba1-4c81-bbd9-391369e485ea) erfordert eine Anmeldung bei App Store Connect. Der genaue Bundle-Produktbezeichner und die Preisaufteilung zwischen den Komponenten werden mit Apple geklärt.

### Text für die Anfrage

We would like to offer a single-developer annual subscription Bundle combining Rudolf Steiner: Gesamtausgabe (Apple app ID 6820947669) and Steiners Seelenkalender (Apple app ID 6780030656).

The component subscriptions are com.jonathankutscher.ga.annual (subscription ID 6820967918) and de.jonathankutscher.seelenkalender.yearly (subscription ID 6780419642). Both renew annually. Their current German storefront prices are EUR 30.00 and EUR 7.99 per year. We request a total Bundle price of EUR 35.00 per year for Germany, with access to both services on iPhone, iPad, and Mac.

The Seelenkalender annual subscription is approved; the GA annual subscription is waiting for review. We plan to support Bundle purchases through StoreKit 2 on the required OS versions. Please advise on eligibility, configuration, component pricing, transaction verification, and the earliest launch after approval of both apps. The launch date and any introductory offer will be confirmed during configuration.

## Kauf und Freischaltung

Beide Apps müssen einen Bundle-Kauf zuverlässig als Zugang zu ihrem jeweiligen enthaltenen Jahresabo erkennen. Die GA-App verwendet RevenueCat-Projekt `34fd17d0` mit `ga_access`, Seelenkalender Projekt `3c17a0a5` mit `seelenkalender_pro`. Die Apps verwenden getrennte anonyme Kundenkennungen. Die Freischaltung über Apples Bundle-Transaktionen und die Unterstützung durch RevenueCat müssen vor einem Angebot in der App geprüft werden.

Ein alternatives gemeinsames Abo für ältere Betriebssysteme benötigt eine gemeinsame, verifizierte Kundenidentität und eine Freischaltung über beide Apps. Apples Anleitung beschreibt hierfür eine gemeinsame Kontoverwaltung und serverseitige Kaufprüfung. Das ist eine eigene Umsetzung, die zusätzliche Konto- und Datenschutzentscheidungen erfordert. [Apple-Anleitung für mehrere Apps](https://developer.apple.com/documentation/storekit/offering-a-subscription-across-multiple-apps)

### Vorgesehener deutscher Angebotstext

**GA und Seelenkalender**

Die Rudolf-Steiner-Gesamtausgabe und der Seelenkalender in einem Jahresabo. Vollständiger Zugang zu beiden Apps für insgesamt 35 € pro Jahr.

**Für 35 € jährlich abonnieren**

Das Abo verlängert sich automatisch um ein Jahr. Jederzeit zum Laufzeitende kündbar.

In der veröffentlichten App müssen Preis und Laufzeit aus dem tatsächlich gelieferten Apple-Produkt stammen. Dieser Text wird erst nach Einrichtung und geprüfter Freischaltung verwendet.

## Nächster Schritt

Die Zusammenstellung und jährliche Laufzeit bestätigen, bei App Store Connect anmelden und die Anfrage an Apple anhand der vorstehenden Angaben ausfüllen. Anschließend Apples Konfiguration und die Freischaltung in beiden Apps prüfen, bevor das Angebot aktiviert wird.
