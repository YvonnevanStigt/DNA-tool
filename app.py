import streamlit as st
import io
import csv
import re
import gzip
import json
import urllib.request
import urllib.parse
from datetime import date

st.set_page_config(
    page_title="OPFG DNA Analyse Tool",
    page_icon="🧬",
    layout="centered"
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSE1KrUOUJ8WDNAJ6PYZCxh1toMzUo6ObPQjPaEBO9KDcI6KFHGBpi6FB1aAw03HSUZEWydsGNayZje/pub?gid=0&single=true&output=csv"
LOGO_URL = "https://raw.githubusercontent.com/YvonnevanStigt/DNA-tool/main/logo%20(3).jpg"
ENSEMBL_GRCH37 = "https://grch37.rest.ensembl.org"


def laad_gebruikers():
    try:
        with urllib.request.urlopen(SHEET_URL) as response:
            inhoud = response.read().decode("utf-8")

        gebruikers = {}

        for regel in inhoud.strip().splitlines():
            delen = regel.strip().split(",")

            if len(delen) >= 3:
                email = delen[0].strip().strip('"').lower()
                wachtwoord = delen[1].strip().strip('"')
                verloopdatum = delen[2].strip().strip('"')
                abonnement = (
                    delen[3].strip().strip('"').lower()
                    if len(delen) >= 4
                    else "basis"
                )

                if email:
                    gebruikers[email] = {
                        "wachtwoord": wachtwoord,
                        "verloopdatum": verloopdatum,
                        "abonnement": abonnement
                    }

        return gebruikers

    except Exception:
        return {
            "test@test.nl": {
                "wachtwoord": "test123",
                "verloopdatum": "2099-12-31",
                "abonnement": "basis"
            }
        }


def controleer_login():
    if st.session_state.get("ingelogd"):
        return True

    st.image(LOGO_URL, width=250)
    st.title("OPFG DNA Analyse Tool")
    st.markdown("---")
    st.subheader("Inloggen")

    st.markdown(
        "Vul het e-mailadres en wachtwoord in waarmee je toegang hebt gekocht. "
        "Heb je nog geen toegang? Neem contact op via de website."
    )

    ingevoerd_email = st.text_input(
        "E-mailadres",
        placeholder="jouw@emailadres.nl"
    )

    ingevoerd_wachtwoord = st.text_input(
        "Wachtwoord",
        type="password",
        placeholder="Jouw wachtwoord"
    )

    inloggen = st.button(
        "Inloggen",
        type="primary"
    )

    st.info(
        "🔒 Je DNA-bestand wordt alleen gebruikt voor deze analyse "
        "en wordt door de tool niet blijvend opgeslagen."
    )

    if inloggen:
        email = ingevoerd_email.strip().lower()
        wachtwoord = ingevoerd_wachtwoord.strip()

        gebruikers = laad_gebruikers()

        if email not in gebruikers:
            st.error("❌ Dit e-mailadres heeft geen toegang.")

        elif gebruikers[email]["wachtwoord"] != wachtwoord:
            st.error("❌ Onjuist wachtwoord.")

        else:
            verloopdatum_str = gebruikers[email]["verloopdatum"]

            try:
                verloopdatum = date.fromisoformat(verloopdatum_str)

                if date.today() > verloopdatum:
                    st.error(
                        f"⚠️ Je toegang is verlopen op "
                        f"{verloopdatum.strftime('%d-%m-%Y')}. "
                        "Neem contact op om je abonnement te verlengen."
                    )

                else:
                    st.session_state["ingelogd"] = True
                    st.session_state["email"] = email
                    st.session_state["abonnement"] = (
                        gebruikers[email]["abonnement"]
                    )

                    st.rerun()

            except ValueError:
                st.error(
                    "⚠️ Er is een fout in de verloopdatum. "
                    "Neem contact op met de beheerder."
                )

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
        row = next(
            csv.reader([line], delimiter=";")
        )

    elif "," in line:
        row = next(
            csv.reader([line], delimiter=",")
        )

    else:
        row = line.split()

    row = [
        clean_text(x)
        for x in row
        if clean_text(x)
    ]

    if len(row) < 2:
        return None

    first = (
        row[0]
        .lower()
        .lstrip("#")
        .strip()
    )

    if first in {
        "rsid",
        "snp",
        "markername",
        "rs-nummer",
        "rsnummer"
    }:
        return None

    return row


def extract_rs_and_genotype(row):
    if not row or len(row) < 2:
        return None, None

    rs_nummer = clean_text(
        row[0]
    ).lower()

    if not re.fullmatch(
        r"rs\d+",
        rs_nummer,
        flags=re.IGNORECASE
    ):
        return None, None

    if len(row) >= 4:
        genotype = clean_text(
            row[3]
        ).upper()

        if (
            len(genotype) == 1
            and len(row) >= 5
        ):
            allele2 = clean_text(
                row[4]
            ).upper()

            if len(allele2) == 1:
                genotype = genotype + allele2

    else:
        genotype = clean_text(
            row[-1]
        ).upper()

    return rs_nummer, genotype


def haal_rs_nummers_uit_invoer(tekst):
    rs_lijst = re.findall(
        r"rs\d+",
        tekst,
        flags=re.IGNORECASE
    )

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

    if (
        raw_bytes.startswith(b'\xff\xfe')
        or raw_bytes.startswith(b'\xfe\xff')
    ):
        dna_tekst = raw_bytes.decode(
            "utf-16",
            errors="ignore"
        )

    else:
        dna_tekst = raw_bytes.decode(
            "utf-8-sig",
            errors="ignore"
        )

    dna_tekst = (
        dna_tekst
        .replace('\r\n', '\n')
        .replace('\r', '\n')
    )

    gezochte_set = {
        clean_text(rs).lower()
        for rs in gezochte_rs
        if clean_text(rs)
    }

    gevonden = {}

    for line in io.StringIO(dna_tekst):
        row = parse_line(line)

        if not row:
            continue

        rs_nummer, genotype = (
            extract_rs_and_genotype(row)
        )

        if not rs_nummer:
            continue

        if rs_nummer in gezochte_set:
            gevonden[rs_nummer] = genotype

    return gevonden


# ============================================================
# WGS / TellmeGen
# ============================================================

GRCH37_CHROM_MAP = {
    "NC_000001.10": "1",
    "NC_000002.11": "2",
    "NC_000003.11": "3",
    "NC_000004.11": "4",
    "NC_000005.9": "5",
    "NC_000006.11": "6",
    "NC_000007.13": "7",
    "NC_000008.10": "8",
    "NC_000009.11": "9",
    "NC_000010.10": "10",
    "NC_000011.9": "11",
    "NC_000012.11": "12",
    "NC_000013.10": "13",
    "NC_000014.8": "14",
    "NC_000015.9": "15",
    "NC_000016.9": "16",
    "NC_000017.10": "17",
    "NC_000018.9": "18",
    "NC_000019.9": "19",
    "NC_000020.10": "20",
    "NC_000021.8": "21",
    "NC_000022.10": "22",
    "NC_000023.10": "X",
    "NC_000024.9": "Y",
    "NC_012920.1": "MT",
}


def normaliseer_chromosoom(chrom):
    chrom = clean_text(
        chrom
    ).upper()

    if chrom.startswith("CHR"):
        chrom = chrom[3:]

    if chrom == "M":
        chrom = "MT"

    return chrom


@st.cache_data(
    show_spinner=False,
    ttl=60 * 60 * 24 * 30
)
def rsid_naar_grch37_ncbi(rs_id):
    rs_id = clean_text(rs_id).lower()

    if not re.fullmatch(r"rs\d+", rs_id):
        return None

    rs_nummer = rs_id[2:]

    url = (
        "https://api.ncbi.nlm.nih.gov/"
        "variation/v0/refsnp/"
        + rs_nummer
    )

    for poging in range(2):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "OPFG-DNA-Analyse-Tool/1.0",
                    "Accept": "application/json"
                }
            )

            with urllib.request.urlopen(
                req,
                timeout=20
            ) as response:
                data = json.loads(
                    response.read().decode("utf-8")
                )

            break

        except Exception:
            data = None

    if not data:
        return None

    merged = data.get("merged_snapshot_data")

    if merged:
        merged_into = merged.get("merged_into", [])

        if merged_into:
            nieuw_rs = "rs" + str(merged_into[0])

            resultaat = rsid_naar_grch37(nieuw_rs)

            if resultaat:
                resultaat = dict(resultaat)
                resultaat["requested_rsid"] = rs_id
                resultaat["resolved_rsid"] = nieuw_rs

            return resultaat

        return None

    primary = data.get("primary_snapshot_data")

    if not primary:
        return None

    placements = primary.get(
        "placements_with_allele",
        []
    )

    for placement in placements:
        seq_id = placement.get("seq_id", "")

        chrom = GRCH37_CHROM_MAP.get(seq_id)

        if not chrom:
            continue

        annot = placement.get(
            "placement_annot",
            {}
        )

        assemblies = annot.get(
            "seq_id_traits_by_assembly",
            []
        )

        is_grch37 = any(
            str(
                a.get("assembly_name", "")
            ).startswith("GRCh37")
            for a in assemblies
        )

        if not is_grch37:
            continue

        alleles = placement.get(
            "alleles",
            []
        )

        spdis = []

        for allele_info in alleles:
            try:
                spdi = allele_info["allele"]["spdi"]
                spdis.append(spdi)
            except Exception:
                continue

        if not spdis:
            continue

        positions = {
            int(spdi["position"])
            for spdi in spdis
            if "position" in spdi
        }

        if not positions:
            continue

        pos_vcf = min(positions) + 1

        ref = ""
        alts = []

        for spdi in spdis:
            deleted = str(
                spdi.get(
                    "deleted_sequence",
                    ""
                )
            ).upper()

            inserted = str(
                spdi.get(
                    "inserted_sequence",
                    ""
                )
            ).upper()

            if (
                not ref
                and deleted == inserted
            ):
                ref = deleted

            if (
                inserted != deleted
                and inserted not in alts
            ):
                alts.append(inserted)

        if not ref:
            ref = str(
                spdis[0].get(
                    "deleted_sequence",
                    ""
                )
            ).upper()

        return {
            "requested_rsid": rs_id,
            "resolved_rsid": rs_id,
            "chrom": chrom,
            "pos": pos_vcf,
            "ref": ref,
            "alts": alts,
            "bron": "NCBI"
        }

    return None


def rsid_naar_grch37_ensembl(rs_id):
    rs_id = clean_text(rs_id).lower()

    if not re.fullmatch(r"rs\d+", rs_id):
        return None

    url = (
        "https://grch37.rest.ensembl.org/"
        "variation/human/"
        + rs_id
        + "?content-type=application/json"
    )

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "OPFG-DNA-Analyse-Tool/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

    except Exception:
        return None

    mappings = data.get("mappings", [])

    if not mappings:
        return None

    geldige_chromosomen = {
        str(i) for i in range(1, 23)
    } | {"X", "Y", "MT", "M"}

    for mapping in mappings:
        chrom = str(
            mapping.get(
                "seq_region_name",
                ""
            )
        ).upper()

        if chrom.startswith("CHR"):
            chrom = chrom[3:]

        if chrom == "M":
            chrom = "MT"

        if chrom not in geldige_chromosomen:
            continue

        assembly = str(
            mapping.get(
                "assembly_name",
                ""
            )
        )

        if (
            assembly
            and not assembly.startswith("GRCh37")
        ):
            continue

        try:
            pos = int(
                mapping.get("start")
            )
        except (TypeError, ValueError):
            continue

        allele_string = str(
            mapping.get(
                "allele_string",
                ""
            )
        ).upper()

        alleles = [
            a.strip()
            for a in allele_string.split("/")
            if a.strip()
        ]

        ref = (
            alleles[0]
            if alleles
            else ""
        )

        alts = []

        for allele in alleles[1:]:
            if allele not in alts:
                alts.append(allele)

        return {
            "requested_rsid": rs_id,
            "resolved_rsid": rs_id,
            "chrom": chrom,
            "pos": pos,
            "ref": ref,
            "alts": alts,
            "bron": "Ensembl"
        }

    return None


@st.cache_data(
    show_spinner=False,
    ttl=60 * 60 * 24 * 30
)
def rsid_naar_grch37(rs_id):
    rs_id = clean_text(rs_id).lower()

    if not re.fullmatch(r"rs\d+", rs_id):
        return None

    resultaat = rsid_naar_grch37_ncbi(rs_id)

    if resultaat:
        return resultaat

    resultaat = rsid_naar_grch37_ensembl(rs_id)

    if resultaat:
        return resultaat

    return None


def iter_vcf_regels(uploaded_file):
    uploaded_file.seek(0)

    magic = uploaded_file.read(2)

    uploaded_file.seek(0)

    if magic == b'\x1f\x8b':
        with gzip.GzipFile(
            fileobj=uploaded_file,
            mode="rb"
        ) as gz:

            for raw_line in gz:
                yield raw_line.decode(
                    "utf-8",
                    errors="ignore"
                )

    else:
        for raw_line in uploaded_file:

            if isinstance(
                raw_line,
                bytes
            ):
                yield raw_line.decode(
                    "utf-8",
                    errors="ignore"
                )

            else:
                yield raw_line


def genotype_uit_vcf_regel(delen):
    ref = delen[3].upper()
    alt = delen[4].upper()

    allelen = [
        ref
    ] + alt.split(",")

    if len(delen) < 10:
        return ""

    format_velden = (
        delen[8]
        .split(":")
    )

    sample_velden = (
        delen[9]
        .split(":")
    )

    try:
        gt_index = (
            format_velden
            .index("GT")
        )

        gt = sample_velden[
            gt_index
        ]

    except (
        ValueError,
        IndexError
    ):
        gt = (
            sample_velden[0]
            if sample_velden
            else ""
        )

    if (
        not gt
        or gt in {
            ".",
            "./.",
            ".|."
        }
    ):
        return ""

    indices = re.split(
        r"[/|]",
        gt
    )

    genotype_allelen = []

    try:
        for i in indices:
            if i == ".":
                continue

            index = int(i)

            if (
                0
                <= index
                < len(allelen)
            ):
                genotype_allelen.append(
                    allelen[index]
                )

            else:
                return gt

    except Exception:
        return gt

    if not genotype_allelen:
        return ""

    if all(
        len(a) == 1
        for a in genotype_allelen
    ):
        return "".join(
            genotype_allelen
        )

    return "/".join(
        genotype_allelen
    )


def lees_vcf_bestand(
    uploaded_file,
    gezochte_rs
):
    positie_lookup = {}
    mapping_info = {}
    niet_omgezet = []

    for rs in gezochte_rs:
        info = rsid_naar_grch37(
            rs
        )

        if not info:
            niet_omgezet.append(
                rs
            )
            continue

        sleutel = (
            normaliseer_chromosoom(
                info["chrom"]
            ),
            int(
                info["pos"]
            )
        )

        positie_lookup.setdefault(
            sleutel,
            []
        ).append(rs)

        mapping_info[
            rs
        ] = info

    gevonden = {}

    gezochte_set = {
        rs.lower()
        for rs in gezochte_rs
    }

    nog_nodig = set(
        positie_lookup.keys()
    )

    for line in iter_vcf_regels(
        uploaded_file
    ):
        if (
            not line
            or line.startswith("#")
        ):
            continue

        delen = (
            line
            .rstrip("\n\r")
            .split("\t")
        )

        if len(delen) < 5:
            continue

        chrom = normaliseer_chromosoom(
            delen[0]
        )

        try:
            pos = int(
                delen[1]
            )

        except ValueError:
            continue

        genotype = None

        id_kolom = clean_text(
            delen[2]
        ).lower()

        ids_in_regel = {
            x.lower()
            for x in re.split(
                r"[;,]",
                id_kolom
            )
            if re.fullmatch(
                r"rs\d+",
                x.strip(),
                flags=re.IGNORECASE
            )
        }

        directe_matches = (
            ids_in_regel
            & gezochte_set
        )

        if directe_matches:
            genotype = (
                genotype_uit_vcf_regel(
                    delen
                )
            )

            for rs in directe_matches:
                gevonden[rs] = (
                    genotype
                    or "Genotype niet leesbaar"
                )

        sleutel = (
            chrom,
            pos
        )

        if sleutel in positie_lookup:
            if genotype is None:
                genotype = (
                    genotype_uit_vcf_regel(
                        delen
                    )
                )

            for rs in positie_lookup[
                sleutel
            ]:
                gevonden[rs] = (
                    genotype
                    or "Genotype niet leesbaar"
                )

            nog_nodig.discard(
                sleutel
            )

        if (
            not nog_nodig
            and positie_lookup
        ):
            break

    return (
        gevonden,
        niet_omgezet,
        mapping_info
    )



# ============================================================
# WGS GEN-ANALYSE
# ============================================================

SPLICE_TERMS = {"splice_acceptor_variant", "splice_donor_variant", "splice_region_variant"}
MISSENSE_TERMS = {"missense_variant"}
SYNONYMOUS_TERMS = {"synonymous_variant"}
OTHER_CODING_TERMS = {
    "transcript_ablation", "stop_gained", "frameshift_variant", "stop_lost",
    "start_lost", "transcript_amplification", "inframe_insertion", "inframe_deletion",
    "protein_altering_variant", "incomplete_terminal_codon_variant",
    "start_retained_variant", "stop_retained_variant", "coding_sequence_variant"
}
CODING_TERMS = SPLICE_TERMS | MISSENSE_TERMS | SYNONYMOUS_TERMS | OTHER_CODING_TERMS
UTR_TERMS = {"5_prime_UTR_variant", "3_prime_UTR_variant"}


def haal_genen_uit_invoer(tekst):
    gezien, genen = set(), []
    for gen in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", tekst):
        gen = gen.upper().strip()
        if gen and gen not in gezien:
            gezien.add(gen)
            genen.append(gen)
    return genen


def http_json_get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "OPFG-DNA-Analyse-Tool/2.1",
        "Accept": "application/json"
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_json_post(url, payload, timeout=90):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "User-Agent": "OPFG-DNA-Analyse-Tool/2.1",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24 * 30)
def haal_genregio_grch37(gen):
    gen = clean_text(gen).upper()
    url = (
        f"{ENSEMBL_GRCH37}/lookup/symbol/homo_sapiens/"
        + urllib.parse.quote(gen)
        + "?content-type=application/json"
    )
    try:
        d = http_json_get(url, 25)
        return {
            "gene": gen,
            "chrom": normaliseer_chromosoom(d["seq_region_name"]),
            "start": int(d["start"]),
            "end": int(d["end"]),
            "strand": int(d.get("strand", 0)),
        }
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24 * 30)
def haal_regulatory_features(chrom, start, end):
    regio = urllib.parse.quote(f"{chrom}:{start}-{end}", safe=":-")
    url = (
        f"{ENSEMBL_GRCH37}/overlap/region/homo_sapiens/{regio}"
        "?feature=regulatory;content-type=application/json"
    )
    try:
        data = http_json_get(url, 30)
    except Exception:
        return []
    features = []
    for x in data if isinstance(data, list) else []:
        try:
            features.append({
                "id": x.get("id", ""),
                "start": int(x["start"]),
                "end": int(x["end"]),
                "description": x.get("description") or x.get("feature_type") or x.get("biotype") or "regulatory",
            })
        except Exception:
            pass
    return features


def genotype_en_gt_uit_vcf(delen):
    ref, alt = delen[3].upper(), delen[4].upper()
    allelen = [ref] + alt.split(",")
    if len(delen) < 10:
        return "", "", [], allelen
    fmt, sample = delen[8].split(":"), delen[9].split(":")
    try:
        gt = sample[fmt.index("GT")]
    except Exception:
        gt = sample[0] if sample else ""
    if gt in {"", ".", "./.", ".|."}:
        return "", gt, [], allelen
    indices, vals = [], []
    try:
        for s in re.split(r"[/|]", gt):
            if s == ".":
                continue
            i = int(s)
            indices.append(i)
            if 0 <= i < len(allelen):
                vals.append(allelen[i])
            else:
                return gt, gt, indices, allelen
    except Exception:
        return gt, gt, indices, allelen
    genotype = "".join(vals) if vals and all(len(v) == 1 for v in vals) else "/".join(vals)
    return genotype, gt, indices, allelen


def scan_genregios(uploaded_file, genen, flank=5000):
    gebieden, niet_gevonden = [], []
    for gen in genen:
        g = haal_genregio_grch37(gen)
        if not g:
            niet_gevonden.append(gen)
            continue
        g = dict(g)
        g["scan_start"] = max(1, g["start"] - flank)
        g["scan_end"] = g["end"] + flank
        g["regulatory"] = haal_regulatory_features(g["chrom"], g["scan_start"], g["scan_end"])
        gebieden.append(g)

    per_chrom = {}
    for g in gebieden:
        per_chrom.setdefault(g["chrom"], []).append(g)

    kandidaten, no_calls = [], 0
    uploaded_file.seek(0)
    for line in iter_vcf_regels(uploaded_file):
        if not line or line.startswith("#"):
            continue
        d = line.rstrip("\r\n").split("\t")
        if len(d) < 5:
            continue
        chrom = normaliseer_chromosoom(d[0])
        if chrom not in per_chrom:
            continue
        try:
            pos = int(d[1])
        except ValueError:
            continue
        genotype, gt, indices, allelen = genotype_en_gt_uit_vcf(d)
        if not indices:
            if gt in {".", "./.", ".|."}:
                no_calls += 1
            continue
        if all(i == 0 for i in indices):
            continue
        called_alt_indices = sorted({i for i in indices if 0 < i < len(allelen)})
        if not called_alt_indices:
            continue
        for g in per_chrom[chrom]:
            if not (g["scan_start"] <= pos <= g["scan_end"]):
                continue
            reg_hits = []
            for f in g["regulatory"]:
                if f["start"] <= pos <= f["end"]:
                    label = str(f["description"])
                    if f["id"]:
                        label += f" ({f['id']})"
                    reg_hits.append(label)
            for alt_index in called_alt_indices:
                kandidaten.append({
                    "gene": g["gene"], "chrom": chrom, "pos": pos,
                    "vcf_id": d[2], "ref": d[3].upper(), "alt": allelen[alt_index],
                    "genotype": genotype, "regulatory_hits": reg_hits,
                })
    return kandidaten, niet_gevonden, no_calls


def vep_annotaties(kandidaten):
    uniq = {(k["chrom"], k["pos"], k["ref"], k["alt"]): k for k in kandidaten}
    keys, out, batch_size = list(uniq), {}, 150
    for start in range(0, len(keys), batch_size):
        batch = keys[start:start + batch_size]
        variants = [f"{c} {p} . {r} {a} . . ." for c, p, r, a in batch]
        url = (
            f"{ENSEMBL_GRCH37}/vep/homo_sapiens/region"
            "?canonical=1;hgvs=1;protein=1;numbers=1;variant_class=1;content-type=application/json"
        )
        try:
            data = http_json_post(url, {"variants": variants}, 90)
        except Exception:
            data = []
        for item in data if isinstance(data, list) else []:
            parts = str(item.get("input", "")).split()
            if len(parts) >= 5:
                try:
                    key = (normaliseer_chromosoom(parts[0]), int(parts[1]), parts[3].upper(), parts[4].upper())
                    out[key] = item
                except Exception:
                    pass
    return out


def bepaal_categorieen(terms, regulatory_hits):
    cats = []
    if any(t in SPLICE_TERMS for t in terms): cats.append("splice")
    if any(t in MISSENSE_TERMS for t in terms): cats.append("missense")
    if any(t in SYNONYMOUS_TERMS for t in terms): cats.append("synonymous")
    if any(t in OTHER_CODING_TERMS for t in terms): cats.append("coding")
    if any(t in UTR_TERMS for t in terms): cats.append("UTR")
    reg = " ".join(regulatory_hits).lower()
    if "promoter" in reg: cats.append("promoter")
    if "enhancer" in reg: cats.append("enhancer")
    if regulatory_hits and "promoter" not in reg and "enhancer" not in reg: cats.append("regulatoir")
    return list(dict.fromkeys(cats))


def bouw_gen_resultaten(kandidaten, annotaties):
    rows = []
    for k in kandidaten:
        item = annotaties.get((k["chrom"], k["pos"], k["ref"], k["alt"]), {})
        terms, hgvs, transcripts = [], [], []
        for tc in item.get("transcript_consequences", []) or []:
            gene_symbol = str(tc.get("gene_symbol", "")).upper()
            if gene_symbol and gene_symbol != k["gene"]:
                continue
            rel = set(tc.get("consequence_terms", []) or []) & (CODING_TERMS | UTR_TERMS)
            if not rel:
                continue
            terms.extend(sorted(rel))
            if tc.get("hgvsc"): hgvs.append(str(tc["hgvsc"]))
            if tc.get("hgvsp"): hgvs.append(str(tc["hgvsp"]))
            if tc.get("transcript_id"): transcripts.append(str(tc["transcript_id"]))
        terms = list(dict.fromkeys(terms))
        hgvs = list(dict.fromkeys(hgvs))
        transcripts = list(dict.fromkeys(transcripts))
        if not terms and not k["regulatory_hits"]:
            continue
        rsids = []
        for cv in item.get("colocated_variants", []) or []:
            cid = str(cv.get("id", ""))
            if re.fullmatch(r"rs\d+", cid, re.I):
                rsids.append(cid.lower())
        rs = ", ".join(dict.fromkeys(rsids))
        if not rs and re.fullmatch(r"rs\d+", str(k["vcf_id"]), re.I):
            rs = str(k["vcf_id"]).lower()
        rows.append({
            "Gen": k["gene"], "RS-nummer": rs or "—", "Chr": k["chrom"],
            "Positie GRCh37": k["pos"], "Genotype": k["genotype"], "REF": k["ref"], "ALT": k["alt"],
            "Categorie": " + ".join(bepaal_categorieen(terms, k["regulatory_hits"])),
            "Consequence": ", ".join(terms), "HGVS": " | ".join(hgvs),
            "Transcript": ", ".join(transcripts), "Regulatory feature": "; ".join(k["regulatory_hits"]),
        })
    rows.sort(key=lambda r: (r["Gen"], r["Chr"], int(r["Positie GRCh37"])))
    return rows


def gen_resultaten_naar_csv(resultaten):
    output = io.StringIO()
    velden = ["Gen", "RS-nummer", "Chr", "Positie GRCh37", "Genotype", "REF", "ALT", "Categorie", "Consequence", "HGVS", "Transcript", "Regulatory feature"]
    writer = csv.DictWriter(output, fieldnames=velden)
    writer.writeheader()
    writer.writerows(resultaten)
    return output.getvalue()

def toon_resultaten(
    gevonden,
    rs_lijst,
    wgs=False
):
    resultaten = []

    for rs in rs_lijst:
        if rs in gevonden:
            resultaten.append(
                {
                    "RS-nummer": rs,
                    "Gevonden": "✅",
                    "Genotype": gevonden[rs]
                }
            )

        else:
            niet_gevonden_tekst = (
                "Niet aangetroffen in VCF"
                if wgs
                else "Niet gevonden"
            )

            resultaten.append(
                {
                    "RS-nummer": rs,
                    "Gevonden": "—",
                    "Genotype":
                    niet_gevonden_tekst
                }
            )

    n_gevonden = sum(
        1
        for r in resultaten
        if r["Gevonden"] == "✅"
    )

    n_niet = (
        len(resultaten)
        - n_gevonden
    )

    col1, col2, col3 = (
        st.columns(3)
    )

    col1.metric(
        "Gezocht",
        len(rs_lijst)
    )

    col2.metric(
        "Gevonden",
        n_gevonden
    )

    col3.metric(
        "Niet gevonden",
        n_niet
    )

    st.success(
        "✅ Analyse voltooid!"
    )

    st.dataframe(
        resultaten,
        width="stretch",
        hide_index=True
    )

    if wgs:
        st.warning(
            "Let op: dit WGS-VCF bevat alleen varianten die als afwijking "
            "van het referentiegenoom in het bestand zijn opgenomen. "
            "‘Niet aangetroffen in VCF’ betekent daarom niet automatisch "
            "dat je op die positie het normale of homozygote "
            "referentiegenotype hebt. Het betekent alleen dat deze positie "
            "niet als variantregel in dit VCF-bestand staat."
        )

    csv_regels = [
        "RS-nummer,Gevonden,Genotype"
    ]

    for r in resultaten:
        gevonden_str = (
            "ja"
            if r["Gevonden"] == "✅"
            else "nee"
        )

        csv_regels.append(
            f"{r['RS-nummer']},"
            f"{gevonden_str},"
            f"{r['Genotype']}"
        )

    csv_tekst = "\n".join(
        csv_regels
    )

    st.download_button(
        label=(
            "⬇️ Download resultaten als CSV"
        ),
        data=csv_tekst.encode(
            "utf-8"
        ),
        file_name=(
            "dna_analyse_resultaten.csv"
        ),
        mime="text/csv"
    )


def toon_tool():
    col_logo, col_titel, col_logout = st.columns([1, 4, 1])
    with col_logo:
        st.image(LOGO_URL, width=80)
    with col_titel:
        st.title("OPFG DNA Analyse Tool")
    with col_logout:
        st.write("")
        if st.button("Uitloggen", width="stretch"):
            st.session_state["ingelogd"] = False
            st.session_state["email"] = ""
            st.session_state["abonnement"] = ""
            st.rerun()

    abonnement = st.session_state.get("abonnement", "basis")
    st.markdown("---")
    st.info("🔒 Je DNA-bestand wordt alleen gebruikt voor deze analyse en wordt door de tool niet blijvend opgeslagen.")

    if abonnement == "wgs":
        tab1, tab2, tab3 = st.tabs([
            "📂 Normaal DNA",
            "🧬 WGS – RS-nummers",
            "🧬 WGS – Gen-analyse",
        ])

        with tab1:
            st.subheader("RS-nummers zoeken in normaal DNA-bestand")
            rs_tekst = st.text_area("🔎 Plak hier de RS-nummers:", height=180, key="rs_normaal_wgs")
            uploaded_file = st.file_uploader("Upload DNA-bestand", type=["txt", "csv"], key="normaal")
            if st.button("🚀 Start Analyse", type="primary", key="start_normaal"):
                if not uploaded_file:
                    st.error("⚠️ Upload eerst een DNA-bestand.")
                elif not rs_tekst.strip():
                    st.error("⚠️ Plak eerst RS-nummers.")
                else:
                    rs_lijst = haal_rs_nummers_uit_invoer(rs_tekst)
                    if not rs_lijst:
                        st.error("⚠️ Geen geldige RS-nummers herkend.")
                    else:
                        with st.spinner(f"🔬 {len(rs_lijst)} RS-nummers opzoeken..."):
                            gevonden = lees_dna_bestand(uploaded_file, rs_lijst)
                        toon_resultaten(gevonden, rs_lijst, wgs=False)

        with tab2:
            st.subheader("RS-nummers zoeken in WGS")
            st.markdown("Upload je WGS VCF-bestand (`.vcf` of `.vcf.gz`). Gebruik bij voorkeur het originele `.vcf.gz`-bestand; uitpakken is niet nodig.")
            st.info("ℹ️ Deze route gebruik je als je al weet welke RS-nummers je wilt onderzoeken.")
            rs_tekst = st.text_area("🔎 Plak hier de RS-nummers:", height=180, key="rs_wgs")
            uploaded_vcf = st.file_uploader("Upload WGS-bestand (.vcf of .vcf.gz)", type=["vcf", "gz"], key="vcf_rs")
            if st.button("🚀 Start VCF Analyse", type="primary", key="start_vcf"):
                if not uploaded_vcf:
                    st.error("⚠️ Upload eerst een VCF- of VCF.GZ-bestand.")
                elif not rs_tekst.strip():
                    st.error("⚠️ Plak eerst RS-nummers.")
                else:
                    rs_lijst = haal_rs_nummers_uit_invoer(rs_tekst)
                    if not rs_lijst:
                        st.error("⚠️ Geen geldige RS-nummers herkend.")
                    else:
                        with st.spinner(f"🧬 {len(rs_lijst)} RS-nummers omzetten naar GRCh37 en opzoeken in WGS..."):
                            gevonden, niet_omgezet, mapping_info = lees_vcf_bestand(uploaded_vcf, rs_lijst)
                        toon_resultaten(gevonden, rs_lijst, wgs=True)
                        if niet_omgezet:
                            st.warning("Voor deze RS-nummers kon via NCBI én Ensembl geen GRCh37-positie worden bepaald: " + ", ".join(niet_omgezet))
                        with st.expander("🔎 Toon gebruikte GRCh37-posities"):
                            mapping_tabel = []
                            for rs in rs_lijst:
                                info = mapping_info.get(rs)
                                if not info:
                                    mapping_tabel.append({"RS-nummer": rs, "Chromosoom": "", "GRCh37 positie": "", "REF": "", "ALT": "", "Bron": "", "Status": "Niet omgezet"})
                                    continue
                                resolved = info.get("resolved_rsid", rs)
                                mapping_tabel.append({
                                    "RS-nummer": rs,
                                    "Chromosoom": info["chrom"],
                                    "GRCh37 positie": info["pos"],
                                    "REF": info.get("ref", ""),
                                    "ALT": ", ".join(info.get("alts", [])),
                                    "Bron": info.get("bron", ""),
                                    "Status": f"Samengevoegd naar {resolved}" if resolved != rs else "OK",
                                })
                            st.dataframe(mapping_tabel, width="stretch", hide_index=True)

        with tab3:
            st.subheader("Gen-analyse WGS")
            st.markdown("Gebruik deze route als je wilt onderzoeken welke relevante varianten in één of meer genen aanwezig zijn, ook als je de RS-nummers nog niet kent.")
            st.info("ℹ️ De tool zoekt in het gen en standaard 5 kb eromheen en toont coding-, splice-, missense-, synonymous-, UTR-, promoter- en enhancer-hits. Ook varianten zonder RS-nummer kunnen worden gevonden.")
            gen_tekst = st.text_area("🧬 Plak hier de gensymbolen:", height=180, placeholder="FKBP4\nHSP90AA1\nHSP90AB1\nHSPA8\nSTIP1", key="gen_tekst_wgs")
            flank = st.number_input("Flank rond het gen voor regulatoire features (bp)", min_value=0, max_value=20000, value=5000, step=1000, key="gen_flank")
            uploaded_vcf_gen = st.file_uploader("Upload WGS-bestand (.vcf of .vcf.gz)", type=["vcf", "gz"], key="vcf_gen")
            if st.button("🚀 Start Gen-analyse", type="primary", key="start_genanalyse"):
                if not uploaded_vcf_gen:
                    st.error("⚠️ Upload eerst een VCF- of VCF.GZ-bestand.")
                elif not gen_tekst.strip():
                    st.error("⚠️ Plak eerst één of meer gensymbolen.")
                else:
                    genen = haal_genen_uit_invoer(gen_tekst)
                    if not genen:
                        st.error("⚠️ Geen geldige gensymbolen herkend.")
                    elif len(genen) > 20:
                        st.error("⚠️ Gebruik maximaal 20 genen per analyse.")
                    else:
                        try:
                            with st.spinner(f"🧬 Gen-analyse uitvoeren voor {len(genen)} gen(en)..."):
                                kandidaten, niet_gevonden_genen, no_calls = scan_genregios(uploaded_vcf_gen, genen, flank=int(flank))
                                annotaties = vep_annotaties(kandidaten)
                                resultaten = bouw_gen_resultaten(kandidaten, annotaties)
                            st.success("✅ Gen-analyse voltooid!")
                            c1, c2 = st.columns(2)
                            c1.metric("Relevante varianten", len(resultaten))
                            c2.metric("No-calls uitgesloten", no_calls)
                            if resultaten:
                                st.dataframe(resultaten, width="stretch", hide_index=True)
                                csv_tekst = gen_resultaten_naar_csv(resultaten)
                                st.download_button("⬇️ Download gen-analyse als CSV", data=csv_tekst.encode("utf-8"), file_name="wgs_genanalyse_resultaten.csv", mime="text/csv")
                            else:
                                st.info("Er zijn binnen de gekozen genen geen gecallde coding-, splice-, UTR- of regulatoire varianten gevonden die aan de selectie voldoen.")
                            if niet_gevonden_genen:
                                st.warning("Voor deze genen kon geen GRCh37-genregio worden opgehaald: " + ", ".join(niet_gevonden_genen))
                            st.warning("Let op: een positie die niet als variantregel in dit VCF staat, wordt niet automatisch als homozygoot referentie geïnterpreteerd.")
                        except Exception as fout:
                            st.error(f"⚠️ De gen-analyse kon niet worden voltooid. Technische melding: {fout}")

    else:
        st.subheader("RS-nummers zoeken")
        rs_tekst = st.text_area("🔎 Plak hier de RS-nummers (elke opmaak werkt):", height=180, placeholder="rs4680\nrs1801131\nrs12069019, rs76698872\n...")
        st.markdown("📂 Upload het originele ruwe DNA-bestand (.txt of .csv). Let op: zet het bestand niet eerst om naar een ander formaat.")
        st.markdown("De tool zoekt exact op kolom 1 (rs4680 matcht **niet** op rs4680899).")
        uploaded_file = st.file_uploader("Upload DNA-bestand", type=["txt", "csv"])
        if st.button("🚀 Start Analyse", type="primary"):
            if not uploaded_file:
                st.error("⚠️ Upload eerst een DNA-bestand.")
            elif not rs_tekst.strip():
                st.error("⚠️ Plak eerst RS-nummers.")
            else:
                rs_lijst = haal_rs_nummers_uit_invoer(rs_tekst)
                if not rs_lijst:
                    st.error("⚠️ Geen geldige RS-nummers herkend.")
                else:
                    with st.spinner(f"🔬 {len(rs_lijst)} RS-nummers opzoeken..."):
                        gevonden = lees_dna_bestand(uploaded_file, rs_lijst)
                    toon_resultaten(gevonden, rs_lijst, wgs=False)


if controleer_login():
    toon_tool()
