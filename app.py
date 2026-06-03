import streamlit as st
import io
import csv
import re
import urllib.request
from datetime import date

st.set_page_config(
    page_title="OPFG DNA Analyse Tool",
    page_icon="🧬",
    layout="centered"
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSE1KrUOUJ8WDNAJ6PYZCxh1toMzUo6ObPQjPaEBO9KDcI6KFHGBpi6FB1aAw03HSUZEWydsGNayZje/pub?gid=0&single=true&output=csv"

LOGO_URL = "https://raw.githubusercontent.com/YvonnevanStigt/DNA-tool/main/logo%20(3).jpg"

def laad_gebruikers():
    try:
        with urllib.request.urlopen(SHEET_URL) as response:
            inhoud = response.read().decode("utf-8")
        gebruikers = {}
        for regel in inhoud.strip().splitlines():
            delen = regel.strip().split(",")
            if len(delen) >= 2:
                email = delen[0].strip().strip('"').lower()
                verloopdatum = delen[1].strip().strip('"')
                if email:
                    gebruikers[email] = verloopdatum
        return gebruikers
    except Exception:
        return {"testcode123@test.nl": "2099-12-31"}

def controleer_login():
    if st.session_state.get("ingelogd"):
        return True

    st.image(LOGO_URL, width=250)
    st.title("OPFG DNA Analyse Tool")
    st.markdown("---")
    st.subheader("Inloggen met je e-mailadres")
    st.markdown(
        "Vul het e-mailadres in waarmee je toegang hebt gekocht. "
        "Heb je nog geen toegang? Neem contact op via de website."
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        ingevoerd_email = st.text_input(
            "E-mailadres",
            placeholder="jouw@emailadres.nl",
            label_visibility="collapsed"
        )
    with col2:
        inloggen = st.button("Inloggen", type="primary", use_container_width=True)

    st.info("🔒 Je DNA-bestand wordt alleen lokaal verwerkt in je browser en nooit opgeslagen of verstuurd naar een server.")

    if inloggen:
        email = ingevoerd_email.strip().lower()
        gebruikers = laad_gebruikers()
        if email not in gebruikers:
            st.error("❌ Dit e-mailadres heeft geen toegang.")
        else:
            verloopdatum_str = gebruikers[email]
            try:
                verloopdatum = date.fromisoformat(verloopdatum_str)
                if date.today() > verloopdatum:
                    st.error(f"⚠️ Je toegang is verlopen op {verloopdatum.strftime('%d-%m-%Y')}. Neem contact op om je abonnement te verlengen.")
                else:
                    st.session_state["ingelogd"] = True
                    st.session_state["email"] = email
                    st.rerun()
            except ValueError:
                st.error("⚠️ Er is een fout in de verloopdatum. Neem contact op met de beheerder.")

    return False

def clean_text(s):
    if s is None:
        return ""
    return (
        str(s)
        .replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\xa0", "")
        .replace('"', "")
        .strip()
    )

def parse_line(line):
    line = clean_text(line)
    if not line:
        return None
    if line.lstrip().startswith("#"):
        return None
    if ";" in line:
        row = next(csv.reader([line], delimiter=";"))
    elif "," in line:
        row = next(csv.reader([line], delimiter=","))
    else:
        row = line.split()
    row = [clean_text(x) for x in row if clean_text(x)]
    if len(row) < 2:
        return None
    first = row[0].lower().lstrip("#").strip()
    if first in {"rsid", "snp", "markername", "rs-nummer", "rsnummer"}:
        return None
    return row

def extract_rs_and_genotype(row):
    if not row or len(row) < 2:
        return None, None
    rs_nummer = clean_text(row[0]).lower()
    if not re.fullmatch(r"rs\d+", rs_nummer, flags=re.IGNORECASE):
        return None, None
    if len(row) >= 4:
        genotype = clean_text(row[3]).upper()
        if len(genotype) == 1 and len(row) >= 5:
            allele2 = clean_text(row[4]).upper()
            if len(allele2) == 1:
                genotype = genotype + allele2
    else:
        genotype = clean_text(row[-1]).upper()
    return rs_nummer, genotype

def haal_rs_nummers_uit_invoer(tekst):
    rs_lijst = re.findall(r"rs\d+", tekst, flags=re.IGNORECASE)
    gezien = set()
    uniek = []
    for rs in rs_lijst:
        rs_lower = rs.lower()
        if rs_lower not in gezien:
            gezien.add(rs_lower)
            uniek.append(rs_lower)
    return uniek

def lees_dna_bestand(uploaded_file, gezochte_rs):
    uploaded_file.seek(0)
    raw_bytes = uploaded_file.read()
    if raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
        dna_tekst = raw_bytes.decode("utf-16", errors="ignore")
    else:
        dna_tekst = raw_bytes.decode("utf-8-sig", errors="ignore")
    gezochte_set = {clean_text(rs).lower() for rs in gezochte_rs if clean_text(rs)}
    gevonden = {}
    string_stroom = io.StringIO(dna_tekst)
    for line in string_stroom:
        row = parse_line(line)
        if not row:
            continue
        rs_nummer, genotype = extract_rs_and_genotype(row)
        if not rs_nummer:
            continue
        if rs_nummer in gezochte_set:
            gevonden[rs_nummer] = genotype
    return gevonden

def toon_tool():
    col_logo, col_titel, col_logout = st.columns([1, 4, 1])
    with col_logo:
        st.image(LOGO_URL, width=80)
    with col_titel:
        st.title("OPFG DNA Analyse Tool")
    with col_logout:
        st.write("")
        if st.button("Uitloggen", use_container_width=True):
            st.session_state["ingelogd"] = False
            st.session_state["email"] = ""
            st.rerun()

    st.markdown("---")
    st.info("🔒 Je DNA-bestand wordt alleen lokaal verwerkt in je browser en nooit opgeslagen of verstuurd naar een server.")
    st.markdown(
        "Upload je ruwe DNA-bestand en plak de RS-nummers die je wilt opzoeken. "
        "De tool zoekt exact op kolom 1 (rs4680 matcht **niet** op rs4680899)."
    )

    uploaded_file = st.file_uploader(
        "📂 Upload het ruwe DNA-bestand (.txt of .csv)",
        type=["txt", "csv"]
    )

    rs_tekst = st.text_area(
        "🔎 Plak hier de RS-nummers (elke opmaak werkt):",
        height=180,
        placeholder="rs4680\nrs1801131\nrs12069019, rs76698872\n..."
    )

    if st.button("🚀 Start Analyse", type="primary"):
        if not uploaded_file:
            st.error("⚠️ Upload eerst een DNA-bestand.")
            return
        if not rs_tekst.strip():
            st.error("⚠️ Plak eerst RS-nummers in het tekstvak.")
            return
        rs_lijst = haal_rs_nummers_uit_invoer(rs_tekst)
        if not rs_lijst:
            st.error("⚠️ Geen geldige RS-nummers herkend in je invoer.")
            return
        with st.spinner(f"🔬 {len(rs_lijst)} RS-nummers opzoeken..."):
            try:
                gevonden = lees_dna_bestand(uploaded_file, rs_lijst)
            except Exception as e:
                st.error(f"❌ Fout bij lezen van bestand: {e}")
                return

        resultaten = []
        for rs in rs_lijst:
            if rs in gevonden:
                resultaten.append({"RS-nummer": rs, "Gevonden": "✅", "Genotype": gevonden[rs]})
            else:
                resultaten.append({"RS-nummer": rs, "Gevonden": "—", "Genotype": "Niet gevonden"})

        n_gevonden = sum(1 for r in resultaten if r["Gevonden"] == "✅")
        n_niet = len(resultaten) - n_gevonden

        col1, col2, col3 = st.columns(3)
        col1.metric("Gezocht", len(rs_lijst))
        col2.metric("Gevonden", n_gevonden)
        col3.metric("Niet gevonden", n_niet)

        st.success("✅ Analyse voltooid!")
        st.dataframe(resultaten, use_container_width=True, hide_index=True)

        csv_regels = ["RS-nummer,Gevonden,Genotype"]
        for r in resultaten:
            gevonden_str = "ja" if r["Gevonden"] == "✅" else "nee"
            csv_regels.append(f"{r['RS-nummer']},{gevonden_str},{r['Genotype']}")
        csv_tekst = "\n".join(csv_regels)

        st.download_button(
            label="⬇️ Download resultaten als CSV",
            data=csv_tekst.encode("utf-8"),
            file_name="dna_analyse_resultaten.csv",
            mime="text/csv"
        )

if controleer_login():
    toon_tool()
