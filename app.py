"""
app.py - webinterface van de SEO/GEO-analysetool (Streamlit).
Starten:  streamlit run app.py
"""

import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

import config as C
from analyzer import RobotsVerbod, analyseer, basis_ok, gevoeligheid, haal_op, onderdeelscore, totaal
from llm import PUNTEN, advies, beoordeel

st.set_page_config(page_title="Van SEO naar GEO", page_icon="🔎", layout="wide")


def geheim(naam):
    try:
        return st.secrets.get(naam, "")
    except Exception:
        return ""


def status(r):
    if r is None or r != r:  # None of NaN = niet meetbaar
        return "– n.v.t."
    if r >= 1:
        return "✅ goed"
    if r <= 0:
        return "❌ fout"
    return f"⚠️ {r:.0%}"


# ---------------- Zijbalk ----------------
with st.sidebar:
    st.header("Instellingen")
    aanbieder = st.radio("Taalmodel", ["Gemini", "Claude", "Geen (alleen checks)"])
    if aanbieder == "Gemini":
        api_key = st.text_input("Gemini API-sleutel", value=geheim("GEMINI_API_KEY"), type="password")
        model = st.text_input("Model", value=C.GEMINI_MODEL)
    elif aanbieder == "Claude":
        api_key = st.text_input("Claude API-sleutel", value=geheim("ANTHROPIC_API_KEY"), type="password")
        model = st.text_input("Model", value=C.CLAUDE_MODEL)
    else:
        api_key, model = "", ""
    runs = st.slider("Aantal beoordelingen door de AI", 1, 5, C.AANTAL_RUNS,
                     help="De methode schrijft 5 voor. Minder is sneller en goedkoper om te testen.")
    snelheid = st.checkbox("Snelheid meten (Google PageSpeed, ±30 sec.)", value=C.PAGESPEED_AAN)
    met_advies = st.checkbox("Verbeteradvies laten schrijven", value=True,
                             help="Uitzetten scheelt tijd tijdens de test. De scores en de CSV veranderen niet.")
    ps_key = geheim("PAGESPEED_API_KEY")
    st.caption(f"Methode v{C.METHODE_VERSIE} · prompt v{C.PROMPT_VERSIE} · totaal = "
               f"{C.GEWICHT_SEO:.0%} SEO + {C.GEWICHT_GEO_TECHNIEK:.0%} GEO-techniek + {C.GEWICHT_GEO_INHOUD:.0%} GEO-inhoud")

# ---------------- Invoer ----------------
st.title("🔎 Van SEO naar GEO")
st.write("Hoe goed wordt deze pagina gevonden in Google (SEO), en hoe geschikt is hij voor AI-zoekmachines zoals "
         "ChatGPT en Perplexity (GEO)? Elke score laat zien waar hij op gebaseerd is.")

c1, c2 = st.columns([3, 2])
url = c1.text_input("URL van de webpagina", value="https://www.thuisarts.nl")
paginatype = c2.selectbox("Soort pagina", list(C.PAGINATYPES))
start = st.button("Analyseer", type="primary")

if "historie" not in st.session_state:
    st.session_state.historie = []

if start and url:
    try:
        with st.spinner("Pagina, robots.txt en sitemap ophalen" + (" en snelheid meten" if snelheid else "") + "..."):
            data = haal_op(url, pagespeed=snelheid, pagespeed_key=ps_key)
    except RobotsVerbod as e:
        st.warning(str(e))
        st.stop()
    except requests.RequestException as e:
        st.error(f"De pagina kon niet worden opgehaald: {e}")
        st.stop()

    analyse = analyseer(data)
    beoordeling, adv, llm_fout = None, None, None
    if aanbieder != "Geen (alleen checks)":
        if not api_key:
            llm_fout = "Geen API-sleutel ingevuld: de AI-beoordeling en het advies zijn overgeslagen."
        else:
            try:
                balk = st.progress(0.0, text=f"De AI beoordeelt de tekst: beoordeling 1 van {runs}...")
                def voortgang(klaar, totaal):
                    tekst = (f"De AI beoordeelt de tekst: beoordeling {klaar + 1} van {totaal}... "
                             "(bij drukte wacht de tool even en probeert opnieuw)") if klaar < totaal else "Beoordeling klaar."
                    balk.progress(klaar / totaal, text=tekst)
                beoordeling = beoordeel(analyse, paginatype, aanbieder, api_key, model, runs, voortgang)
                balk.empty()
                if met_advies:
                    with st.spinner("De AI schrijft verbeteradvies..."):
                        adv = advies(analyse, paginatype, beoordeling, aanbieder, api_key, model)
            except Exception as e:
                llm_fout = f"Fout bij het taalmodel: {e}"

    seo = onderdeelscore(analyse["checks"], "SEO")
    geo_t = onderdeelscore(analyse["checks"], "GEO-techniek")
    geo_i = beoordeling["score"] if beoordeling else None
    res = {"data": data, "analyse": analyse, "beoordeling": beoordeling, "advies": adv, "fout": llm_fout,
           "paginatype": paginatype, "model": f"{aanbieder} {model}".strip(),
           "scores": {"SEO": seo, "GEO-techniek": geo_t, "GEO-inhoud": geo_i, "Totaal": totaal(seo, geo_t, geo_i)},
           "basis_ok": basis_ok(analyse["checks"])}
    st.session_state.laatste = res
    st.session_state.historie.append({
        "datum": datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%d %H:%M"), "url": data["url"], "paginatype": paginatype,
        "basis_ok": res["basis_ok"], "seo": seo, "geo_techniek": geo_t, "geo_inhoud": geo_i,
        "totaal": res["scores"]["Totaal"], **gevoeligheid(analyse["checks"], geo_i),
        **{f"check_{c['id']}": c["resultaat"] for c in analyse["checks"]},
        **({f"ai_{k}": v["mediaan"] for k, v in beoordeling["punten"].items()} if beoordeling else {}),
        "ai_onzeker": sum(v["onzeker"] for v in beoordeling["punten"].values()) if beoordeling else None,
        "model": res["model"], "methode": C.METHODE_VERSIE, "prompt": C.PROMPT_VERSIE,
    })

# ---------------- Resultaat ----------------
res = st.session_state.get("laatste")
if res:
    a, s = res["analyse"], res["scores"]
    st.subheader(res["data"]["url"])
    if not res["basis_ok"]:
        fout = [c["naam"] for c in a["checks"] if c["onderdeel"] == "Basis" and c["resultaat"] != 1.0]
        st.error("**Deze pagina kan niet goed gevonden worden door Google. Los dit eerst op.**  \n"
                 f"Probleem: {', '.join(fout)}. De andere scores zijn wel berekend, zodat je ziet wat er verder beter kan.")
    if res["fout"]:
        st.info(res["fout"])

    fmt = lambda v: "–" if v is None else f"{v}/100"
    k = st.columns(4)
    k[0].metric("Totaalscore" + ("" if res["basis_ok"] else " (onder voorbehoud)"), fmt(s["Totaal"]))
    k[1].metric("SEO", fmt(s["SEO"]), help="Aantal goede SEO-checks / aantal SEO-checks x 100")
    k[2].metric("GEO-techniek", fmt(s["GEO-techniek"]), help="Aantal goede GEO-checks / aantal GEO-checks x 100")
    k[3].metric("GEO-inhoud", fmt(s["GEO-inhoud"]), help="(gemiddeld AI-cijfer - 1) / 4 x 100")
    if s["GEO-inhoud"] is None:
        st.caption("Zonder AI-beoordeling is de totaalscore berekend uit SEO en GEO-techniek, naar verhouding.")

    t_adv, t_checks, t_ai, t_info, t_verg = st.tabs(["Verbeteradvies", "Checks", "AI-beoordeling", "Overige info", "Vergelijking"])

    with t_adv:
        adv = res["advies"]
        if not adv and res["beoordeling"]:
            st.caption("Het AI-advies is voor deze analyse overgeslagen (vinkje in de zijbalk).")
        if adv:
            st.caption("🤖 Geschreven door AI, controleer dit voordat je het uitvoert.")
            st.write(adv.get("samenvatting", ""))
            icoon = {"hoog": "🔴", "middel": "🟠", "laag": "🟢"}
            for i, x in enumerate(adv.get("adviezen", []), 1):
                st.markdown(f"**{i}. {icoon.get(str(x.get('prioriteit', '')).lower(), '•')} {x.get('titel', '')}**")
                st.write(x.get("uitleg", ""))
                if x.get("voorbeeld"):
                    st.info(x["voorbeeld"])
                st.caption(f"Gebaseerd op: {x.get('gebaseerd_op', '')}")
        st.markdown("##### Checks die niet goed gaan")
        fout = [c for c in a["checks"] if c["soort"] in ("basis", "telt mee") and c["resultaat"] is not None and c["resultaat"] < 1]
        tips = [c for c in a["checks"] if c["soort"] == "tip" and c["resultaat"] == 0.0]
        if not fout:
            st.write("Alle checks die meetellen zijn goed.")
        for c in fout:
            st.markdown(f"- **{c['naam']}** ({c['onderdeel']}): {c['meting']}. {c['advies']}")
        if tips:
            st.markdown("##### Tips (tellen niet mee, zwak bewijs)")
            for c in tips:
                st.markdown(f"- **{c['naam']}**: {c['advies']}")

    with t_checks:
        st.caption("Elke check die meetelt, telt even zwaar. Tips en informatie tellen niet mee voor de score.")
        df = pd.DataFrame(a["checks"])
        df["status"] = df["resultaat"].map(status)
        for onderdeel in ["Basis", "SEO", "GEO-techniek"]:
            g = df[df["onderdeel"] == onderdeel]
            st.markdown(f"##### {onderdeel}" + ("" if onderdeel == "Basis" else f" · {fmt(s[onderdeel])}"))
            st.dataframe(g[["status", "naam", "soort", "bewijs", "meting", "norm", "waarom", "bron"]].astype(str),
                         hide_index=True, width="stretch")
        w = [c for c in a["checks"] if c["waarschuwing"]]
        for c in w:
            st.warning(f"{c['naam']}: {c['waarschuwing']}")

    with t_ai:
        b = res["beoordeling"]
        if not b:
            st.info("Geen AI-beoordeling uitgevoerd.")
        else:
            if b["gemiddelde"] is None:
                st.warning("Geen enkel cijfer had geldig bewijs van de pagina. GEO-inhoud kan niet worden berekend "
                           "(vaak omdat er te weinig leesbare tekst op de pagina staat).")
            else:
                st.write(f"Gemiddeld cijfer **{b['gemiddelde']:.1f}** van 5 → GEO-inhoud **{b['score']}/100**. ")
            st.caption(f"{b['runs']} beoordelingen, het middelste cijfer telt"
                       + (f", {b['mislukte_runs']} mislukt" if b["mislukte_runs"] else "") + ".")
            if b["afgekapt"]:
                st.warning(f"De tekst was langer dan {C.MAX_TEKST_LLM} tekens; alleen het begin is beoordeeld.")
            for kk, v in b["punten"].items():
                p = PUNTEN[kk]
                m = v["mediaan"]
                kop = f"**{p['naam']}**: {'–' if m is None else (int(m) if m == int(m) else m)}/5"
                if v["onzeker"]:
                    kop += " · ⚠️ onzeker"
                st.markdown(kop)
                st.caption(f"Cijfers per run: {v['cijfers']} · geldig bewijs in {v['geldige_runs']} van {len(v['cijfers'])} runs · bron: {p['bron']}")
                if v["bewijs"]:
                    st.markdown(f"> {v['bewijs']}  \n✅ staat letterlijk op de pagina")
                st.write(v["toelichting"])
                if v["verworpen_bewijs"]:
                    with st.expander("Verworpen bewijs (niet op de pagina gevonden)"):
                        for vb in v["verworpen_bewijs"]:
                            st.write(f"❌ {vb}")
            with st.expander("Gebruikte prompt (navolgbaarheid)"):
                st.code(b["prompt"], language="markdown")

    with t_info:
        st.caption("Ter informatie. Hier is geen bewijs voor, of het heeft geen gevolg voor de score.")
        st.table(pd.DataFrame(list(a["info"].items()), columns=["Onderdeel", "Waarde"]).astype(str))

    with t_verg:
        st.caption("Alle analyses in deze sessie. Download vóór je de pagina ververst. "
                   "De kolommen totaal_a/b/c zijn de gevoeligheidsanalyse uit hoofdstuk 8. Er worden geen teksten van websites bewaard.")
        hist = pd.DataFrame(st.session_state.historie)
        st.dataframe(hist, hide_index=True, width="stretch")
        buf = io.StringIO()
        hist.to_csv(buf, index=False, sep=";")
        st.download_button("Download vergelijking (CSV voor Excel)", buf.getvalue().encode("utf-8-sig"),
                           file_name="vergelijking_websites.csv", mime="text/csv")
        rapport = {"url": res["data"]["url"], "paginatype": res["paginatype"], "model": res["model"],
                   "methode": C.METHODE_VERSIE, "prompt": C.PROMPT_VERSIE, "scores": s, "basis_ok": res["basis_ok"],
                   "checks": a["checks"], "info": a["info"],
                   "ai_beoordeling": {k: v for k, v in (res["beoordeling"] or {}).items() if k != "prompt"},
                   "advies": res["advies"]}
        st.download_button("Download deze analyse (JSON)", json.dumps(rapport, ensure_ascii=False, indent=2, default=str),
                           file_name="analyse.json", mime="application/json")
