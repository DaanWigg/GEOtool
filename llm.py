"""
llm.py - de AI beoordeelt de tekst (hoofdstuk 6 van de methode) en schrijft verbeteradvies.

Zo zorgen we dat de AI eerlijk beoordeelt:
 1. Voorbeelden per cijfer (1, 3 en 5) staan in de prompt.
 2. Bewijs verplicht: bij elk cijfer een letterlijk stukje tekst. De code controleert of dat
    stukje echt op de pagina staat. Zo niet, dan telt dat cijfer niet mee.
 3. Vijf keer beoordelen, het middelste cijfer (mediaan) telt. Grote spreiding = "onzeker".
 4. Lengte telt niet: dat staat expliciet in de prompt.
 5. Altijd hetzelfde model en dezelfde prompt (versie staat in config.py en in de export).
"""

import json
import re
import statistics
import unicodedata

import config as C

PUNTEN = {
    "directe_antwoorden": {
        "naam": "Directe antwoorden",
        "vraag": "Sluiten de titel en de tekst aan bij de vragen die mensen over dit onderwerp stellen? En staan de antwoorden bovenaan?",
        "1": "Lange inleiding of reclametekst; het antwoord op de vraag van de bezoeker staat er niet of pas onderaan.",
        "3": "Het antwoord staat in de tekst, maar niet bovenaan, of het is omslachtig geformuleerd.",
        "5": "De tekst sluit duidelijk aan op de vragen van de doelgroep en het kernantwoord staat in de eerste zinnen.",
        "bron": "Chen & Koudas (2026); Martinez (2026)",
    },
    "feiten_cijfers": {
        "naam": "Feiten en cijfers",
        "vraag": "Staan er concrete gegevens in, zoals prijzen, tijden, adressen, aantallen of jaartallen?",
        "1": "Alleen algemene beweringen, zoals 'wij bieden goede service'.",
        "3": "Enkele concrete gegevens, maar de meeste beweringen zijn algemeen.",
        "5": "Veel concrete gegevens, zoals 'open ma-vr 8:00-17:00, consult €45, Coolsingel 10'.",
        "bron": "Aggarwal et al. (2024)",
    },
    "bronnen": {
        "naam": "Bronnen",
        "vraag": ("Worden concrete beweringen in de tekst onderbouwd met een bron, onderzoek of expert? Een lijst met "
                  "partners, logo's of organisatienamen zonder koppeling aan een bewering telt NIET als bron."),
        "1": "Geen enkele verwijzing naar een bron of expert.",
        "3": "Af en toe wordt een organisatie of expert genoemd, maar zonder duidelijke bron.",
        "5": "Belangrijke beweringen worden onderbouwd met een genoemde bron, zoals 'volgens de NHG-richtlijn...' of 'uit onderzoek van het RIVM blijkt...'.",
        "bron": "Aggarwal et al. (2024)",
    },
    "duidelijkheid": {
        "naam": "Duidelijkheid",
        "vraag": "Is de tekst makkelijk te lezen en logisch opgebouwd?",
        "1": "Lange, ingewikkelde zinnen, veel vakjargon en geen duidelijke opbouw.",
        "3": "Redelijk leesbaar, maar met lange alinea's of een onduidelijke volgorde.",
        "5": "Korte zinnen, gewone woorden en een logische volgorde; je begrijpt het in één keer.",
        "bron": "Aggarwal et al. (2024)",
    },
    "betrouwbaarheid": {
        "naam": "Betrouwbaarheid",
        "vraag": "Is duidelijk wie de afzender is en waarom je die kunt vertrouwen?",
        "1": "Onduidelijk wie de tekst schrijft of waarom die deskundig is.",
        "3": "De organisatie wordt genoemd, maar er blijkt weinig over haar ervaring of deskundigheid.",
        "5": "Duidelijk wie de afzender is, met concrete ervaring, deskundigheid of erkenning.",
        "bron": "Google Search Central (z.d.-a)",
    },
    "eigen_informatie": {
        "naam": "Eigen informatie",
        "vraag": ("Bevat de tekst informatie die alleen deze organisatie kan geven, zoals eigen prijzen, cases, "
                  "ervaringen, eigen cijfers of een eigen werkwijze? Beoordeel dit alleen op basis van de tekst; "
                  "je hoeft niet te vergelijken met andere websites."),
        "1": "Algemene tekst die vrijwel letterlijk op elke vergelijkbare website kan staan.",
        "3": "Enkele eigen gegevens, maar het grootste deel is algemeen.",
        "5": "Veel specifieke informatie die alleen deze organisatie kan geven.",
        "bron": "Google Search Central (2026b)",
    },
}

SYSTEEM = ("Je bent een strenge, consequente beoordelaar van webteksten voor generatieve AI-zoekmachines "
           "(zoals ChatGPT, Perplexity en Google AI-antwoorden). Je beoordeelt alleen wat in de tekst staat. "
           "Je antwoordt in het Nederlands en uitsluitend met geldige JSON.")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[“”„\"'‘’`´]", "", s)
    s = re.sub(r"[–—-]", "-", s)
    return re.sub(r"\s+", " ", s).strip()


def bewijs_klopt(citaat: str, tekst_norm: str) -> bool:
    c = _norm(citaat).strip(" .…")
    if len(c) < 8:
        return False
    if c in tekst_norm:
        return True
    # het model kort citaten soms in met '...': elk deel moet dan letterlijk voorkomen
    delen = [d.strip(" .") for d in re.split(r"\.\.\.|…", c) if len(d.strip(" .")) >= 8]
    return bool(delen) and all(d in tekst_norm for d in delen)


def beoordelingsprompt(analyse: dict, paginatype: str) -> str:
    kern = analyse["kern"]
    tekst = analyse["tekst"][:C.MAX_TEKST_LLM]
    punten = "\n".join(
        f'- "{k}" ({p["naam"]}): {p["vraag"]}\n    1 = {p["1"]}\n    3 = {p["3"]}\n    5 = {p["5"]}'
        for k, p in PUNTEN.items())
    verwachting = C.PAGINATYPES.get(paginatype, "")
    return f"""Beoordeel de tekst van deze webpagina op 6 punten, elk met een cijfer van 1 tot 5 (2 en 4 mogen ook).

Paginatype: {paginatype}. Wat bij dit type 'directe antwoorden' betekent: {verwachting}

Punten, met voorbeelden per cijfer:
{punten}

Regels:
- De lengte van de tekst is NIET belangrijk. Een lange tekst is niet beter dan een korte.
- Wees streng: geef een 5 alleen als de pagina het voorbeeld bij 5 echt waarmaakt.
- Geef bij elk cijfer als bewijs een LETTERLIJK stukje tekst van de pagina (maximaal 25 woorden), precies
  zoals het in de paginatekst hieronder staat. Verander er niets aan. Verzin geen bewijs.
- Geef bij elk cijfer een toelichting van maximaal 2 zinnen.

Paginagegevens:
URL: {kern['url']}
Titel: {kern['titel']}
Hoofdkop: {kern['h1']}
Tussenkoppen: {' | '.join(kern['koppen'])}

Paginatekst:
\"\"\"{tekst}\"\"\"

Antwoord alleen met JSON in deze vorm:
{{"punten": {{"<punt>": {{"cijfer": <1-5>, "bewijs": "<letterlijk citaat>", "toelichting": "<tekst>"}}}}}}"""


def adviesprompt(analyse: dict, paginatype: str, punten: dict) -> str:
    fout = [c for c in analyse["checks"] if c["soort"] in ("telt mee", "basis", "tip") and c["resultaat"] is not None and c["resultaat"] < 1]
    checks = "\n".join(f'- [{c["onderdeel"]}, {c["soort"]}] {c["naam"]}: {c["meting"]} (norm: {c["norm"]})' for c in fout) or "- alle checks zijn goed"
    beoordeling = "\n".join(f'- {PUNTEN[k]["naam"]}: {v["mediaan"]}/5. {v["toelichting"]}' for k, v in punten.items() if v["mediaan"] is not None)
    return f"""Je schrijft verbeteradvies voor de beheerder van een webpagina (paginatype: {paginatype}).
Het doel: de pagina beter vindbaar en bruikbaar maken voor Google én voor AI-zoekmachines.

Checks die niet goed gingen:
{checks}

AI-beoordeling van de tekst (1-5):
{beoordeling}

Paginatekst (begin):
\"\"\"{analyse['tekst'][:5000]}\"\"\"

Opdracht:
- Geef de 3 tot 5 adviezen met de meeste impact, belangrijkste eerst. Technische problemen die een AI-robot
  tegenhouden gaan altijd voor.
- Elk advies is concreet en uitvoerbaar door iemand zonder technische kennis, in eenvoudige taal.
- Noem bij elk advies op welke check of welk beoordelingspunt het gebaseerd is.
- Geef waar nuttig een korte voorbeeldtekst. Verzin GEEN feiten, cijfers, prijzen, namen of bronnen.
  Gebruik dan een invulplek, bijvoorbeeld "[vul uw prijs in]".

Antwoord alleen met JSON:
{{"samenvatting": "<max 2 zinnen>", "adviezen": [{{"titel": "<kort>", "uitleg": "<wat en waarom>", "gebaseerd_op": "<check of punt>", "prioriteit": "hoog|middel|laag", "voorbeeld": "<optioneel>"}}]}}"""


# ---------------------------------------------------------------------------
# Modellen
# ---------------------------------------------------------------------------

def _json(tekst: str) -> dict:
    m = re.search(r"\{.*\}", tekst or "", re.S)
    if not m:
        raise ValueError("Het taalmodel gaf geen JSON terug.")
    return json.loads(m.group(0))


TIJDELIJK = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded", "high demand", "529")


def vraag(prompt: str, aanbieder: str, api_key: str, model: str, pogingen: int = 4) -> dict:
    """Vraagt het model; bij een tijdelijke drukte-fout (503/429) wacht hij even en probeert opnieuw."""
    import time
    for poging in range(pogingen):
        try:
            return _vraag(prompt, aanbieder, api_key, model)
        except Exception as e:
            tijdelijk = any(t.lower() in str(e).lower() for t in TIJDELIJK)
            if not tijdelijk or poging == pogingen - 1:
                raise
            time.sleep([10, 30, 60][min(poging, 2)])


def _vraag(prompt: str, aanbieder: str, api_key: str, model: str) -> dict:
    if aanbieder == "Gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120_000))
        r = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEEM, temperature=C.TEMPERATUUR,
                                               response_mime_type="application/json"))
        return _json(r.text)
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    r = client.messages.create(model=model, max_tokens=3000, temperature=C.TEMPERATUUR, system=SYSTEEM,
                               messages=[{"role": "user", "content": prompt}])
    return _json("".join(b.text for b in r.content if b.type == "text"))


# ---------------------------------------------------------------------------
# Beoordeling: 5 runs, bewijscontrole, mediaan
# ---------------------------------------------------------------------------

def beoordeel(analyse: dict, paginatype: str, aanbieder: str, api_key: str, model: str,
              runs: int = C.AANTAL_RUNS, voortgang=None) -> dict:
    prompt = beoordelingsprompt(analyse, paginatype)
    tekst_norm = _norm(analyse["tekst"][:C.MAX_TEKST_LLM] + " " + analyse["kern"]["titel"] + " " + analyse["kern"]["h1"])

    resultaten = []
    for i in range(runs):  # na elkaar, zodat we de gratis limiet per minuut niet overschrijden
        if voortgang:
            voortgang(i, runs)
        try:
            resultaten.append(vraag(prompt, aanbieder, api_key, model))
        except Exception as e:  # een mislukte run telt niet mee
            resultaten.append({"fout": str(e)})
    if voortgang:
        voortgang(runs, runs)

    mislukt = [r["fout"] for r in resultaten if "fout" in r]
    if len(mislukt) == runs:
        raise RuntimeError("Alle runs van het taalmodel zijn mislukt: " + mislukt[0])

    punten = {}
    for k in PUNTEN:
        geldig, alle = [], []
        for r in resultaten:
            p = (r.get("punten") or {}).get(k)
            if not isinstance(p, dict):
                continue
            try:
                cijfer = int(round(float(p.get("cijfer"))))
            except (TypeError, ValueError):
                continue
            if not 1 <= cijfer <= 5:
                continue
            ok = bewijs_klopt(p.get("bewijs", ""), tekst_norm)
            alle.append({"cijfer": cijfer, "bewijs": p.get("bewijs", ""), "bewijs_klopt": ok,
                         "toelichting": p.get("toelichting", "")})
            if ok:
                geldig.append(cijfer)
        mediaan = statistics.median(geldig) if geldig else None
        spreiding = (max(geldig) - min(geldig)) if geldig else None
        # toelichting en bewijs van de geldige run die het dichtst bij de mediaan ligt
        rep = min((a for a in alle if a["bewijs_klopt"]), key=lambda a: abs(a["cijfer"] - mediaan), default=None) if geldig else None
        punten[k] = {
            "mediaan": mediaan,
            "cijfers": [a["cijfer"] for a in alle],
            "geldige_runs": len(geldig),
            "spreiding": spreiding,
            "onzeker": spreiding is not None and spreiding >= C.ONZEKER_SPREIDING,
            "bewijs": rep["bewijs"] if rep else "",
            "toelichting": rep["toelichting"] if rep else "Geen geldig bewijs gevonden; dit punt telt niet mee.",
            "verworpen_bewijs": [a["bewijs"] for a in alle if not a["bewijs_klopt"]],
        }

    medianen = [v["mediaan"] for v in punten.values() if v["mediaan"] is not None]
    gemiddelde = sum(medianen) / len(medianen) if medianen else None
    score = round((gemiddelde - 1) / 4 * 100) if gemiddelde is not None else None

    return {"punten": punten, "gemiddelde": gemiddelde, "score": score, "runs": runs,
            "mislukte_runs": len(mislukt), "afgekapt": len(analyse["tekst"]) > C.MAX_TEKST_LLM,
            "prompt": prompt}


def advies(analyse: dict, paginatype: str, beoordeling: dict | None, aanbieder: str, api_key: str, model: str) -> dict:
    punten = beoordeling["punten"] if beoordeling else {}
    return vraag(adviesprompt(analyse, paginatype, punten), aanbieder, api_key, model)
