"""
analyzer.py - haalt een pagina op en voert de vaste checks uit (hoofdstuk 4 en 5 van de methode).

Elke check is een dict met:
  id, onderdeel ("Basis", "SEO", "GEO-techniek"), naam, soort ("telt mee", "tip", "info"),
  bewijs ("Sterk", "Vuistregel", "Zwak", "Geen bewijs"), resultaat (1.0 goed, 0.0 fout,
  tussenwaarde bij AI-zoekrobots, None = niet meetbaar), meting, norm, waarom, bron, advies,
  waarschuwing (optioneel).

Score per onderdeel = som van de resultaten / aantal meetbare checks die meetellen x 100.
Alle checks die meetellen, tellen even zwaar (hoofdstuk 4, stap 3).
"""

import json
import re
import time
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config as C

TIMEOUT = 20


class RobotsVerbod(Exception):
    """De site verbiedt onze tool via robots.txt; we analyseren dan niet (ethiek, hoofdstuk 9)."""


# ---------------------------------------------------------------------------
# Ophalen
# ---------------------------------------------------------------------------

def _get(url, ua, timeout=TIMEOUT):
    return requests.get(url, headers={"User-Agent": ua, "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.7"},
                        timeout=timeout, allow_redirects=True)


def normaliseer(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def haal_op(url: str, pagespeed: bool = C.PAGESPEED_AAN, pagespeed_key: str = "") -> dict:
    url = normaliseer(url)
    p = urlparse(url)
    basis = f"{p.scheme}://{p.netloc}"

    # 1. robots.txt eerst: de tool volgt zelf de regels van de site
    robots_txt = None
    try:
        r = _get(urljoin(basis, "/robots.txt"), C.TOOL_USER_AGENT, 10)
        if r.status_code == 200 and "<html" not in r.text[:500].lower():
            robots_txt = r.text
    except requests.RequestException:
        pass
    rp = robotparser.RobotFileParser()
    rp.parse((robots_txt or "").splitlines())
    if robots_txt and not rp.can_fetch(C.TOOL_NAAM, url):
        raise RobotsVerbod("Deze site verbiedt automatische tools zoals de onze via robots.txt. "
                           "Uit respect voor de site analyseren we deze pagina niet.")

    # 2. de pagina zelf
    start = time.time()
    resp = _get(url, C.TOOL_USER_AGENT)
    laadtijd = time.time() - start

    # 3. dezelfde pagina als AI-zoekrobot (voor de check "Robots niet geblokkeerd")
    try:
        ai = _get(resp.url, C.AI_TEST_USER_AGENT)
        ai_resp = {"status": ai.status_code, "html": ai.text}
    except requests.RequestException as e:
        ai_resp = {"status": None, "html": "", "fout": str(e)}

    # 4. sitemap: uit robots.txt of op /sitemap.xml
    sitemap = None
    if robots_txt:
        m = re.search(r"(?im)^\s*sitemap:\s*(\S+)", robots_txt)
        if m:
            sitemap = m.group(1)
    if not sitemap:
        try:
            s = _get(urljoin(basis, "/sitemap.xml"), C.TOOL_USER_AGENT, 10)
            if s.status_code == 200 and re.search(r"<(urlset|sitemapindex)", s.text[:3000]):
                sitemap = urljoin(basis, "/sitemap.xml")
        except requests.RequestException:
            pass

    # 5. llms.txt (alleen ter informatie)
    llms = False
    try:
        lt = _get(urljoin(basis, "/llms.txt"), C.TOOL_USER_AGENT, 10)
        llms = lt.status_code == 200 and "<html" not in lt.text[:500].lower() and len(lt.text.strip()) > 0
    except requests.RequestException:
        pass

    return {
        "url_invoer": url,
        "url": resp.url,
        "status": resp.status_code,
        "headers": {k.lower(): v for k, v in resp.headers.items()},
        "html": resp.text,
        "laadtijd": laadtijd,
        "robots_txt": robots_txt,
        "ai_resp": ai_resp,
        "sitemap": sitemap,
        "llms_txt": llms,
        "pagespeed": meet_snelheid(resp.url, pagespeed_key) if pagespeed else {"status": "uit"},
    }


def meet_snelheid(url: str, key: str = "") -> dict:
    """Core Web Vitals (veldgegevens) via Google PageSpeed Insights. Goed = LCP, INP en CLS alle drie 'FAST'."""
    params = {"url": url, "strategy": "mobile", "category": "performance"}
    if key:
        params["key"] = key
    try:
        r = requests.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", params=params, timeout=90)
        if r.status_code != 200:
            return {"status": "fout", "detail": f"PageSpeed gaf status {r.status_code}"}
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return {"status": "fout", "detail": str(e)}

    for bron, label in (("loadingExperience", "deze pagina"), ("originLoadingExperience", "het hele domein")):
        metrics = (data.get(bron) or {}).get("metrics") or {}
        nodig = ["LARGEST_CONTENTFUL_PAINT_MS", "INTERACTION_TO_NEXT_PAINT", "CUMULATIVE_LAYOUT_SHIFT_SCORE"]
        if all(k in metrics for k in nodig):
            cats = {k: metrics[k].get("category") for k in nodig}
            return {"status": "ok", "gemeten_op": label, "categorieen": cats,
                    "goed": all(v == "FAST" for v in cats.values())}
    return {"status": "geen_veldgegevens"}


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def _check(id, onderdeel, naam, soort, bewijs, resultaat, meting, norm, waarom, bron, advies="", waarschuwing=""):
    return {"id": id, "onderdeel": onderdeel, "naam": naam, "soort": soort, "bewijs": bewijs,
            "resultaat": resultaat, "meting": meting, "norm": norm, "waarom": waarom, "bron": bron,
            "advies": advies, "waarschuwing": waarschuwing}


def _zonder_ruis(soup: BeautifulSoup) -> BeautifulSoup:
    s = BeautifulSoup(str(soup), "html.parser")
    for tag in s(["script", "style", "noscript", "svg", "template", "iframe"]):
        tag.decompose()
    return s


def hoofdtekst(soup: BeautifulSoup) -> str:
    """Zichtbare tekst van de hoofdinhoud (zonder menu, header en footer)."""
    s = _zonder_ruis(soup)
    hoofd = s.find("main") or s.find("article") or s.body or s
    for tag in hoofd.find_all(["nav", "header", "footer", "aside"]):
        tag.decompose()
    return re.sub(r"\s+", " ", hoofd.get_text(" ")).strip()


def _jsonld(soup):
    blokken, fouten, types = [], 0, set()

    def verzamel(o):
        if isinstance(o, dict):
            t = o.get("@type")
            if isinstance(t, str):
                types.add(t)
            elif isinstance(t, list):
                types.update(x for x in t if isinstance(x, str))
            for v in o.values():
                verzamel(v)
        elif isinstance(o, list):
            for v in o:
                verzamel(v)

    for b in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(b.string or b.get_text() or "")
            blokken.append(data)
            verzamel(data)
            items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
            for it in items:
                if isinstance(it, dict) and "@type" not in it:
                    fouten += 1
        except (json.JSONDecodeError, TypeError, AttributeError):
            fouten += 1
    for el in soup.find_all(attrs={"itemtype": True}):
        types.add(str(el["itemtype"]).rstrip("/").split("/")[-1])
    return blokken, fouten, sorted(types)


def _robots_mag(robots_txt, agent, url):
    if not robots_txt:
        return True
    rp = robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch(agent, url)


CHALLENGE = re.compile(r"just a moment|cf-browser-verification|challenge-platform|attention required|"
                       r"captcha|access denied|even geduld|checking your browser|ddos-guard", re.I)


# ---------------------------------------------------------------------------
# Alle checks
# ---------------------------------------------------------------------------

def analyseer(data: dict) -> dict:
    soup = BeautifulSoup(data["html"], "html.parser")
    tekst = hoofdtekst(soup)
    woorden = len(tekst.split())
    domein = urlparse(data["url"]).netloc
    checks = []
    GSC = "Google Search Central"

    # ======================= Stap 1: basis =======================
    ok = data["status"] == 200
    checks.append(_check("pagina_werkt", "Basis", "Pagina werkt", "basis", "Sterk", 1.0 if ok else 0.0,
                         f"statuscode {data['status']}", "200",
                         "Alleen een werkende pagina kan in Google komen.", f"{GSC} (z.d.-b)",
                         "Zorg dat de pagina zonder foutmelding laadt (statuscode 200)."))
    meta_robots = " ".join(m.get("content", "") for m in soup.find_all("meta", attrs={"name": re.compile("^(robots|googlebot)$", re.I)}))
    noindex = "noindex" in meta_robots.lower() or "noindex" in data["headers"].get("x-robots-tag", "").lower()
    checks.append(_check("geen_noindex", "Basis", "Mag in Google (geen noindex)", "basis", "Sterk", 0.0 if noindex else 1.0,
                         "noindex gevonden" if noindex else "geen noindex", "geen noindex",
                         "Met noindex komt de pagina niet in Google en ook niet in de AI-antwoorden van Google.",
                         f"{GSC} (2026a)", "Verwijder de noindex-code als de pagina gevonden moet worden."))
    gb = _robots_mag(data["robots_txt"], "Googlebot", data["url"])
    checks.append(_check("robots_google", "Basis", "Zoekmachines mogen lezen (robots.txt)", "basis", "Sterk",
                         1.0 if gb else 0.0, "Googlebot toegestaan" if gb else "Googlebot geblokkeerd",
                         "Googlebot toegestaan", "Een geblokkeerde pagina kan Google niet lezen.",
                         f"{GSC} (z.d.-b); Koster et al. (2022)", "Sta Googlebot toe in robots.txt."))

    # ======================= SEO: telt mee (11) =======================
    O = "SEO"
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    checks.append(_check("mobiel", O, "Mobiel", "telt mee", "Sterk", 1.0 if viewport else 0.0,
                         "viewport-code aanwezig" if viewport else "geen viewport-code", "viewport-code aanwezig",
                         "Google gebruikt de mobiele versie om pagina's op te nemen en te rangschikken.",
                         f"{GSC} (z.d.-g)", "Voeg <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> toe."))

    title = soup.title.get_text(strip=True) if soup.title else ""
    w = ""
    if title and not (C.TITEL_WAARSCHUWING[0] <= len(title) <= C.TITEL_WAARSCHUWING[1]):
        w = f"De titel is {len(title)} tekens. Google kort lange titels zelf in; dit telt niet mee."
    checks.append(_check("titel", O, "Titel", "telt mee", "Sterk", 1.0 if title else 0.0,
                         f"“{title[:80]}” ({len(title)} tekens)" if title else "geen titel", "titel aanwezig",
                         "Google maakt de titel in de zoekresultaten vooral van deze titel.", f"{GSC} (z.d.-f)",
                         "Geef de pagina een eigen titel die de inhoud beschrijft.", w))

    imgs = soup.find_all("img")
    # alt="" is volgens WCAG de juiste manier om een afbeelding als versiering te markeren:
    # die tellen we niet mee. Fout = geen alt-attribuut. Goed = alt met tekst.
    met_tekst = sum(1 for i in imgs if (i.get("alt") or "").strip())
    versiering = sum(1 for i in imgs if i.has_attr("alt") and not (i.get("alt") or "").strip())
    zonder_alt = len(imgs) - met_tekst - versiering
    inhoudelijk = met_tekst + zonder_alt
    if inhoudelijk:
        aandeel = met_tekst / inhoudelijk
        res = 1.0 if aandeel >= C.ALT_TEKST_MINIMUM else 0.0
        meting = f"{met_tekst} van {inhoudelijk} met beschrijving ({aandeel:.0%}); {versiering} als versiering gemarkeerd (alt=\"\")"
    else:
        res, meting = None, (f"alleen versiering ({versiering} afbeeldingen met alt=\"\")" if imgs else "geen afbeeldingen (niet meetbaar)")
    checks.append(_check("alt", O, "Alt-tekst", "telt mee", "Sterk", res, meting,
                         f"minstens {C.ALT_TEKST_MINIMUM:.0%} van de niet-decoratieve afbeeldingen",
                         "Google noemt alt-tekst het belangrijkste kenmerk om een afbeelding te begrijpen.",
                         f"{GSC} (z.d.-e); W3C (2023)", "Geef inhoudelijke afbeeldingen een korte beschrijving (alt-tekst); geef pure versiering alt=\"\"."))

    intern = 0
    extern_hoofd = 0
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        if h.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        host = urlparse(urljoin(data["url"], h)).netloc
        if host == domein:
            intern += 1
    checks.append(_check("interne_links", O, "Interne links", "telt mee", "Sterk", 1.0 if intern >= 1 else 0.0,
                         f"{intern} gewone links naar dezelfde website", "minstens 1",
                         "Google vindt pagina's via gewone links (<a href>).", f"{GSC} (z.d.-h)",
                         "Link met gewone <a href>-links naar andere pagina's van de website."))

    https = data["url"].startswith("https://")
    checks.append(_check("https", O, "HTTPS", "telt mee", "Vuistregel", 1.0 if https else 0.0,
                         "https" if https else "http", "https", "Onderdeel van page experience.",
                         f"{GSC} (2023b)", "Zet een SSL-certificaat op de website."))

    d = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    desc = (d.get("content") or "").strip() if d else ""
    w = ""
    if desc and not (C.DESCRIPTION_WAARSCHUWING[0] <= len(desc) <= C.DESCRIPTION_WAARSCHUWING[1]):
        w = f"De omschrijving is {len(desc)} tekens. Er is geen vaste regel; dit telt niet mee."
    checks.append(_check("meta_description", O, "Meta-description", "telt mee", "Vuistregel", 1.0 if desc else 0.0,
                         f"{len(desc)} tekens" if desc else "geen omschrijving", "omschrijving aanwezig",
                         "Google gebruikt de omschrijving soms in de zoekresultaten.", f"{GSC} (z.d.-d)",
                         "Schrijf een korte omschrijving van de pagina in <meta name=\"description\">.", w))

    can = soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, list) else [v]))
    checks.append(_check("canonical", O, "Canonical", "telt mee", "Vuistregel", 1.0 if can else 0.0,
                         can.get("href", "") if can else "geen canonical", "canonical aanwezig",
                         "Google noemt het een sterk signaal, maar niet verplicht.", f"{GSC} (z.d.-c)",
                         "Voeg <link rel=\"canonical\" href=\"...\"> toe met het adres van de echte versie."))

    checks.append(_check("sitemap", O, "Sitemap", "telt mee", "Vuistregel", 1.0 if data["sitemap"] else 0.0,
                         data["sitemap"] or "niet gevonden", "sitemap aanwezig",
                         "Helpt Google om pagina's te vinden.", f"{GSC} (z.d.-j)",
                         "Maak een sitemap.xml en noem hem in robots.txt."))

    ps = data["pagespeed"]
    if ps.get("status") == "ok":
        afk = {"LARGEST_CONTENTFUL_PAINT_MS": "LCP", "INTERACTION_TO_NEXT_PAINT": "INP", "CUMULATIVE_LAYOUT_SHIFT_SCORE": "CLS"}
        cats = ", ".join(f"{afk.get(k, k)}: {'goed' if v == 'FAST' else v.lower()}" for k, v in ps["categorieen"].items())
        res, meting = (1.0 if ps["goed"] else 0.0), f"{cats} (gemeten op {ps['gemeten_op']})"
    else:
        uitleg = {"uit": "niet gemeten (uitgezet)", "geen_veldgegevens": "geen veldgegevens bij Google (te weinig bezoekers)"}
        res, meting = None, uitleg.get(ps.get("status"), f"niet meetbaar: {ps.get('detail', '')}")
    checks.append(_check("snelheid", O, "Snelheid (Core Web Vitals)", "telt mee", "Vuistregel", res, meting,
                         "LCP, INP en CLS alle drie 'goed'", "Core Web Vitals horen bij page experience.",
                         f"{GSC} (2023b); web.dev (z.d.)", "Verbeter laadtijd en stabiliteit volgens PageSpeed Insights."))

    h1s = soup.find_all("h1")
    checks.append(_check("hoofdkop", O, "Hoofdkop (H1)", "telt mee", "Vuistregel", 1.0 if h1s else 0.0,
                         f"{len(h1s)} H1" + (f": “{h1s[0].get_text(' ', strip=True)[:60]}”" if h1s else ""),
                         "minstens 1", "Google raadt aan de titel in de eerste zichtbare kop te zetten.",
                         f"{GSC} (z.d.-f)", "Zet bovenaan de pagina een duidelijke hoofdkop (H1)."))

    blokken, fouten, types = _jsonld(soup)
    if types and fouten == 0:
        res, meting = 1.0, "zonder fouten: " + ", ".join(types[:8])
    elif types or fouten:
        res, meting = 0.0, f"{fouten} fout(en) in de code" + (": " + ", ".join(types[:8]) if types else "")
    else:
        res, meting = 0.0, "geen gestructureerde data"
    checks.append(_check("gestructureerde_data", O, "Gestructureerde data", "telt mee", "Vuistregel", res, meting,
                         "aanwezig en zonder fouten", "Maakt een pagina geschikt voor extra functies in Google.",
                         f"{GSC} (z.d.-i)", "Voeg schema.org-code (JSON-LD) toe, bijvoorbeeld Organization."))

    # ======================= SEO: tips =======================
    h2s = soup.find_all("h2")
    if woorden > C.TUSSENKOP_VANAF_WOORDEN:
        res, meting = (1.0 if h2s else 0.0), f"{woorden} woorden, {len(h2s)} H2"
    else:
        res, meting = None, f"{woorden} woorden (korte tekst, niet van toepassing)"
    checks.append(_check("tussenkoppen", O, "Tussenkoppen", "tip", "Zwak", res, meting,
                         f"tekst > {C.TUSSENKOP_VANAF_WOORDEN} woorden heeft minstens 1 H2",
                         "Maakt de tekst duidelijker voor de lezer; voor Google maakt het aantal niet uit.",
                         f"{GSC} (z.d.-i)", "Deel lange teksten op met tussenkoppen (H2)."))
    stop = set("de het een en van in op te voor met is zijn je uw wat hoe bij naar of aan als ook om door onze".split())
    tw = {w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", title.lower()) if w not in stop}
    hw = set(re.findall(r"[a-zà-ÿ0-9]{3,}", h1s[0].get_text(" ").lower())) if h1s else set()
    gedeeld = sorted(tw & hw)
    checks.append(_check("titel_hoofdkop", O, "Titel en hoofdkop", "tip", "Zwak",
                         (1.0 if gedeeld else 0.0) if (title and h1s) else None,
                         ", ".join(gedeeld) if gedeeld else ("geen gedeeld woord" if title and h1s else "titel of H1 ontbreekt"),
                         "delen een belangrijk woord", "Logisch vermoeden; geen bron zegt dit letterlijk.",
                         f"{GSC} (z.d.-f)", "Laat titel en hoofdkop over hetzelfde onderwerp gaan."))
    lang = soup.html.get("lang") if soup.html else None
    checks.append(_check("taal", O, "Taal", "tip", "Zwak", 1.0 if lang else 0.0, lang or "niet ingesteld",
                         "lang-attribuut aanwezig", "Nodig voor toegankelijkheid; Google noemt het niet als regel.",
                         "W3C (2023)", "Zet de taal in de code: <html lang=\"nl\">."))

    # ======================= GEO-techniek: telt mee (4) =======================
    O = "GEO-techniek"
    toegestaan = [b for b in C.AI_ZOEKROBOTS if _robots_mag(data["robots_txt"], b, data["url"])]
    geblokt = [b for b in C.AI_ZOEKROBOTS if b not in toegestaan]
    checks.append(_check("ai_zoekrobots", O, "AI-zoekrobots", "telt mee", "Sterk",
                         len(toegestaan) / len(C.AI_ZOEKROBOTS),
                         f"{len(toegestaan)} van {len(C.AI_ZOEKROBOTS)} toegestaan" + (f" (geblokkeerd: {', '.join(geblokt)})" if geblokt else ""),
                         ", ".join(C.AI_ZOEKROBOTS) + " toegestaan in robots.txt",
                         "Wie een zoekrobot blokkeert, komt niet of minder in de antwoorden van die AI.",
                         "Anthropic (z.d.); OpenAI (2026); Perplexity (2026)",
                         "Sta " + ", ".join(geblokt or C.AI_ZOEKROBOTS) + " toe in robots.txt."))

    ruw = _zonder_ruis(soup)
    ruwe_woorden = len(re.sub(r"\s+", " ", (ruw.body or ruw).get_text(" ")).split())
    scripts = len(soup.find_all("script"))
    js_root = soup.find(id=re.compile(r"^(root|app|__next|__nuxt)$"))
    direct = ruwe_woorden >= C.TEKST_DIRECT_MIN_WOORDEN
    checks.append(_check("tekst_direct", O, "Tekst direct leesbaar", "telt mee", "Sterk", 1.0 if direct else 0.0,
                         f"{ruwe_woorden} woorden in de HTML zonder JavaScript ({scripts} scripts"
                         + (", JavaScript-app gevonden" if js_root else "") + ")",
                         f"minstens {C.TEKST_DIRECT_MIN_WOORDEN} woorden zonder JavaScript",
                         "Geen van de grote AI-robots voert JavaScript uit.", "Vercel (2024)",
                         "Laat de server de tekst direct in de HTML zetten (server-side rendering)."))

    ai = data["ai_resp"]
    if ai.get("status") is None:
        res, meting = 0.0, f"geen antwoord: {ai.get('fout', '')[:80]}"
    else:
        challenge = bool(CHALLENGE.search(ai["html"][:20000]))
        geweigerd = ai["status"] in (401, 403, 429, 503)
        res = 0.0 if (geweigerd or challenge) else 1.0
        meting = f"status {ai['status']}" + (", beveiligingspagina gevonden" if challenge else "")
    checks.append(_check("robots_niet_geblokkeerd", O, "Robots niet geblokkeerd", "telt mee", "Sterk", res, meting,
                         "AI-zoekrobot krijgt de pagina (status 200, geen beveiligingspagina)",
                         "Een beveiligingspagina houdt de robot net zo goed tegen als robots.txt.",
                         "Anthropic (z.d.); OpenAI (2026); Koster et al. (2022)",
                         "Zet AI-zoekrobots op de toegestane lijst van je beveiliging (bijv. Cloudflare)."))

    linkteksten = " ".join((a.get("href", "") + " " + a.get_text(" ")) for a in soup.find_all("a", href=True)).lower()
    volledige = soup.get_text(" ")
    wie = bool(re.search(r"\bover[- ]|about|wie-zijn-wij|wie zijn wij|organisatie|colofon|missie", linkteksten)) \
        or any(t in types for t in ("Organization", "LocalBusiness", "Corporation", "GovernmentOrganization", "NGO")) \
        or bool(re.search(r"\bkvk\b|kamer van koophandel", volledige, re.I))
    contact = bool(re.search(r"contact|mailto:|tel:", linkteksten)) \
        or bool(re.search(r"\b\d{4}\s?[A-Z]{2}\b", volledige)) \
        or bool(re.search(r'"(telephone|contactPoint|address)"', data["html"]))
    checks.append(_check("afzender", O, "Afzender duidelijk", "telt mee", "Vuistregel", 1.0 if (wie and contact) else 0.0,
                         f"wie: {'ja' if wie else 'nee'}, contact: {'ja' if contact else 'nee'}",
                         "zichtbaar wie de organisatie is én hoe je contact opneemt",
                         "Google wil weten wie een tekst heeft gemaakt, hoe en waarom.", f"{GSC} (z.d.-a)",
                         "Link naar een over-ons- en contactpagina en noem adres of KvK-nummer."))

    # ======================= GEO: tips =======================
    datum = soup.find("time") or soup.find("meta", attrs={"property": re.compile("(published|modified)_time")}) \
        or re.search(r'"date(Published|Modified)"', data["html"])
    checks.append(_check("actueel", O, "Actueel (datum)", "tip", "Zwak", 1.0 if datum else 0.0,
                         "datum gevonden" if datum else "geen datum", "datum op de pagina",
                         "Kleine, nog niet gecontroleerde onderzoeken.", "Chen et al. (2025); Kumar & Palkhouski (2025)",
                         "Zet een publicatie- of wijzigingsdatum op de pagina."))
    lt = len(soup.find_all(["ul", "ol", "table"]))
    checks.append(_check("lijsten", O, "Lijsten of tabellen", "tip", "Zwak", 1.0 if lt else 0.0,
                         f"{lt} lijsten/tabellen", "minstens 1", "Logisch vermoeden, geen bron gevonden.", "-",
                         "Zet opsommingen of vergelijkingen in een lijst of tabel."))
    vk = [h for h in soup.find_all(re.compile("^h[1-6]$")) if h.get_text(strip=True).endswith("?")]
    checks.append(_check("vraagkoppen", O, "Koppen als vraag", "tip", "Zwak", 1.0 if vk else 0.0,
                         f"{len(vk)} vraagkoppen", "minstens 1", "Logisch vermoeden, geen bron gevonden.",
                         "Chen & Koudas (2026)", "Schrijf een kop als vraag, bijv. 'Wat kost een abonnement?'"))

    # ======================= Alleen informatie =======================
    train = [b for b in C.AI_TRAININGSROBOTS if not _robots_mag(data["robots_txt"], b, data["url"])]
    info = {
        "Woorden in hoofdtekst": woorden,
        "Trainingsrobots geblokkeerd (geen gevolg)": ", ".join(train) or "geen",
        "llms.txt": "aanwezig" if data["llms_txt"] else "niet aanwezig (geen bewijs dat het helpt)",
        "FAQ-code (FAQPage)": "aanwezig" if "FAQPage" in types else "niet aanwezig (Google toont FAQ's bijna nergens meer)",
        "Open Graph": "aanwezig" if soup.find("meta", attrs={"property": "og:title"}) else "niet aanwezig",
        "Schema-types": ", ".join(types) or "geen",
    }

    return {"checks": checks, "tekst": tekst, "info": info,
            "kern": {"url": data["url"], "titel": title, "description": desc,
                     "h1": h1s[0].get_text(" ", strip=True) if h1s else "",
                     "koppen": [h.get_text(" ", strip=True) for h in soup.find_all(["h2", "h3"])][:30],
                     "woorden": woorden}}


# ---------------------------------------------------------------------------
# Scores (hoofdstuk 4, stap 4 en hoofdstuk 7)
# ---------------------------------------------------------------------------

def onderdeelscore(checks, onderdeel, gewichten=None):
    """Aantal goede checks / aantal checks x 100. Alleen checks die meetellen en meetbaar zijn."""
    tel = [c for c in checks if c["onderdeel"] == onderdeel and c["soort"] == "telt mee" and c["resultaat"] is not None]
    if not tel:
        return None
    g = gewichten or {}
    w = [g.get(c["id"], 1) for c in tel]
    return round(100 * sum(c["resultaat"] * wi for c, wi in zip(tel, w)) / sum(w))


def basis_ok(checks):
    return all(c["resultaat"] == 1.0 for c in checks if c["onderdeel"] == "Basis")


def totaal(seo, geo_t, geo_i, verdeling=(C.GEWICHT_SEO, C.GEWICHT_GEO_TECHNIEK, C.GEWICHT_GEO_INHOUD)):
    delen = [(seo, verdeling[0]), (geo_t, verdeling[1]), (geo_i, verdeling[2])]
    delen = [(s, w) for s, w in delen if s is not None]
    if not delen:
        return None
    return round(sum(s * w for s, w in delen) / sum(w for _, w in delen))


def gevoeligheid(checks, geo_inhoud):
    """Alternatieve totaalscores voor hoofdstuk 8, stap 4."""
    kritiek = {i: 2 for i in C.KRITIEKE_CHECKS}
    oud = {c["id"]: C.OUDE_PUNTEN.get(c["bewijs"], 1) for c in checks}
    return {
        "totaal_a_kritiek_dubbel": totaal(onderdeelscore(checks, "SEO", kritiek),
                                          onderdeelscore(checks, "GEO-techniek", kritiek), geo_inhoud),
        "totaal_b_oude_punten": totaal(onderdeelscore(checks, "SEO", oud),
                                       onderdeelscore(checks, "GEO-techniek", oud), geo_inhoud),
        "totaal_c_33_33_33": totaal(onderdeelscore(checks, "SEO"), onderdeelscore(checks, "GEO-techniek"),
                                    geo_inhoud, C.ALTERNATIEVE_VERDELING),
    }
