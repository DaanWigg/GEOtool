"""
config.py - instellingen van de methode (zie 'Systeem SEO en GEO uitleg').

Pas hier de methode aan zonder de rest van de code te veranderen.
Leg elke wijziging en de reden vast in het rapport.
"""

METHODE_VERSIE = "2.0"
PROMPT_VERSIE = "2.0"

# ---------------------------------------------------------------------------
# Totaalscore (hoofdstuk 7)
# ---------------------------------------------------------------------------
GEWICHT_SEO = 0.40
GEWICHT_GEO_TECHNIEK = 0.20
GEWICHT_GEO_INHOUD = 0.40

# ---------------------------------------------------------------------------
# Robots (hoofdstuk 2 en 5)
# ---------------------------------------------------------------------------
# Zoekrobots: tellen mee voor de check "AI-zoekrobots" (2 van 3 toegestaan = 2/3 goed)
AI_ZOEKROBOTS = ["OAI-SearchBot", "Claude-SearchBot", "PerplexityBot"]
# Trainingsrobots: alleen ter informatie, geen gevolg voor de score
AI_TRAININGSROBOTS = ["GPTBot", "ClaudeBot", "Google-Extended"]

# User-agent waarmee we testen of een site AI-robots echt doorlaat (check "Robots niet geblokkeerd")
AI_TEST_USER_AGENT = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; "
    "+https://openai.com/searchbot)"
)
# User-agent van de tool zelf (de tool volgt robots.txt voor deze naam)
TOOL_NAAM = "GEO-Analysetool"
TOOL_USER_AGENT = f"Mozilla/5.0 (compatible; {TOOL_NAAM}/2.0; studentenproject Hogeschool Rotterdam)"

# ---------------------------------------------------------------------------
# Drempels van de checks (hoofdstuk 5)
# ---------------------------------------------------------------------------
ALT_TEKST_MINIMUM = 0.90          # eigen keuze, zie methode
TEKST_DIRECT_MIN_WOORDEN = 100    # minimaal aantal woorden in de ruwe HTML (zonder JavaScript)
TUSSENKOP_VANAF_WOORDEN = 300     # tip "tussenkoppen" geldt voor teksten langer dan dit
TITEL_WAARSCHUWING = (10, 70)     # alleen waarschuwing, telt niet mee
DESCRIPTION_WAARSCHUWING = (50, 170)

# Snelheid via Google PageSpeed Insights (Core Web Vitals, veldgegevens).
# Zonder veldgegevens (vaak bij kleine sites) telt de check niet mee: "niet meetbaar".
PAGESPEED_AAN = True

# ---------------------------------------------------------------------------
# AI-beoordeling (hoofdstuk 6)
# ---------------------------------------------------------------------------
AANTAL_RUNS = 5          # elke pagina 5 keer beoordelen, mediaan per punt
ONZEKER_SPREIDING = 2    # verschil hoogste - laagste >= 2 punten -> "onzeker"
TEMPERATUUR = 0.0        # zo reproduceerbaar mogelijk; de 5 runs meten de variatie die overblijft
MAX_TEKST_LLM = 12000   # aantal tekens paginatekst naar het taalmodel (rest wordt afgekapt en gemeld)

GEMINI_MODEL = "gemini-3.5-flash-lite"
CLAUDE_MODEL = "claude-sonnet-5-5"

PAGINATYPES = {
    "Informatief (artikel, kennisbank, FAQ)": "Het kernantwoord op de hoofdvraag van de pagina staat bovenaan.",
    "Homepage": "Direct zichtbaar is wie de organisatie is, wat ze doet en voor wie.",
    "Product": "Bovenaan staat wat het product is, voor wie, en de belangrijkste gegevens zoals prijs.",
    "Dienst": "Bovenaan staat wat de dienst oplevert, voor wie, hoe het werkt en wat het kost.",
    "Contact / locatie": "Adres, openingstijden en contactmogelijkheden staan direct zichtbaar.",
}

# ---------------------------------------------------------------------------
# Gevoeligheidsanalyse (hoofdstuk 8, stap 4) - alleen in de export
# ---------------------------------------------------------------------------
# (a) checks die een pagina onvindbaar maken als ze misgaan, tellen dubbel
KRITIEKE_CHECKS = ["ai_zoekrobots", "tekst_direct", "robots_niet_geblokkeerd", "interne_links", "mobiel"]
# (b) oude manier: punten per bewijsniveau
OUDE_PUNTEN = {"Sterk": 3, "Vuistregel": 2}
# (c) andere verdeling totaalscore
ALTERNATIEVE_VERDELING = (1 / 3, 1 / 3, 1 / 3)
