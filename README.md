# Van SEO naar GEO – analysetool (prototype v2)

Gebouwd volgens het document *Systeem SEO en GEO uitleg* (methode v2.0).

## Wat de tool doet

1. **Basis (stap 1):** pagina werkt, geen noindex, Googlebot mag lezen. Gaat een van de drie mis, dan verschijnt een rode melding. De andere scores worden wel berekend; de totaalscore krijgt "onder voorbehoud".
2. **21 checks (hoofdstuk 5):** 11 SEO-checks en 4 GEO-checks tellen mee, 6 checks zijn tips. Alles wat meetelt, telt even zwaar. Score = goede checks ÷ aantal checks × 100. Een check die niet te meten is (bijv. geen afbeeldingen, of geen snelheidsgegevens bij Google) telt niet mee.
3. **AI-beoordeling (hoofdstuk 6):** 6 punten, cijfer 1–5, met voorbeelden per cijfer. De AI beoordeelt 5 keer en het middelste cijfer telt. Bij elk cijfer moet de AI een letterlijk citaat geven. De code controleert of dat citaat echt op de pagina staat; zo niet, dan telt dat cijfer niet mee. Een spreiding van 2 punten of meer krijgt "onzeker".
4. **Totaalscore (hoofdstuk 7):** 0,4 × SEO + 0,2 × GEO-techniek + 0,4 × GEO-inhoud.
5. **Advies:** de AI schrijft 3–5 adviezen, gemarkeerd als "Geschreven door AI". Feiten die niet op de pagina staan, worden een invulplek, zoals [vul uw prijs in].
6. **Vergelijking:** alle analyses in één tabel, met de gevoeligheidsanalyse uit hoofdstuk 8 (totaal_a/b/c) als extra kolommen. Te downloaden als CSV.

De tool volgt zelf robots.txt (naam: `GEO-Analysetool`) en bewaart geen teksten van websites.

## Bestanden

| Bestand | Inhoud |
|---|---|
| `app.py` | De webpagina |
| `analyzer.py` | Ophalen van de pagina en alle checks |
| `llm.py` | De 6 beoordelingspunten met voorbeelden, de prompts, de bewijscontrole en de mediaan |
| `config.py` | **De instellingen van de methode**: gewichten, robots, drempels, aantal runs, model |

## Online zetten (geen installatie nodig)

1. Maak een account op **github.com**. Klik op **New repository**, noem hem `geo-tool` en kies **Public**.
2. Klik op **uploading an existing file**, sleep alle bestanden uit deze map erin en klik op **Commit changes**.
3. Ga naar **share.streamlit.io**, log in met GitHub en klik op **Create app**. Kies de repository `geo-tool` en als bestand `app.py`.
4. Open **Advanced settings → Secrets** en plak:
   ```
   GEMINI_API_KEY = "..."
   PAGESPEED_API_KEY = "..."
   ```
   `ANTHROPIC_API_KEY` mag ook, als je Claude wilt gebruiken.
5. Klik op **Deploy**. Je krijgt een link die je kunt delen met het team en de externe organisaties.

Zet een sleutel **nooit** in de code, alleen bij Secrets.

## Sleutels

- **Gemini:** aistudio.google.com → Get API key.
- **PageSpeed (snelheid):** console.cloud.google.com → schakel de *PageSpeed Insights API* in → maak een API-sleutel. Zonder sleutel werkt het soms ook, maar dan loop je snel tegen een limiet aan.
- **Claude (optioneel):** console.anthropic.com → API Keys.

## Tips voor het testen

- Zet tijdens het uitproberen het aantal AI-beoordelingen in de zijbalk op 1. Dat is sneller en goedkoper. Gebruik voor de echte test op de 12 websites altijd 5.
- Kies bij elke pagina het juiste paginatype. Dat bepaalt wat de AI onder "directe antwoorden" verstaat.
- Download de vergelijkingstabel vóór je de pagina ververst.

## Bekende beperkingen

- Er wordt één pagina per keer geanalyseerd.
- De snelheid komt uit gebruikersgegevens van Google. Kleine sites hebben die vaak niet; de check telt dan niet mee.
- "Robots niet geblokkeerd" wordt getest met de herkenningsnaam (user-agent) van OAI-SearchBot. Sommige beveiligingen controleren ook het IP-adres; dat kan de tool niet nabootsen.
- "Afzender duidelijk" zoekt naar een over-ons- of contactlink, adres, KvK-nummer of organisatiegegevens in de code. Dat is een benadering.
- Gestructureerde data wordt gecontroleerd op leesbare JSON-LD met een type. Een volledige controle zoals de Rich Results Test van Google doet de tool niet.
- Er gaan maximaal 12.000 tekens tekst naar de AI. Bij langere pagina's meldt de tool dat de tekst is afgekapt.
