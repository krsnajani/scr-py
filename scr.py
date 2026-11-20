#!/usr/bin/env python3
"""
scr.py / hc.py — pull Supreme Court (SCR / INSC / Case No) and High Court judgment PDFs
off official eCourts portals (scr.sci.gov.in & judgments.ecourts.gov.in) with no browser.

Usage:
  Supreme Court (SCR / INSC / Case No):
    scr "2026 INSC 5"                    # Neutral Citation
    scr "[1978] 2 S.C.R. 621"           # SCR volume/page
    scr "WP (C) 123/2021"               # Case Number (Writ Petition, SLP, Civil Appeal, etc.)
    scr "SLP 1234/2022"                 # Special Leave Petition
    scr "CA 36/2026"                    # Civil Appeal
    scr "Kesavananda Bharati"           # Keyword search (lists all hits)
    scr "right to privacy" -y 2017

  High Courts (eCourts Judgments):
    scr --hc "patent infringement"      # High Court search across India
    scr "2024:DHC:1234"                 # High Court Neutral Citation (auto-detects HC)
    hc "intellectual property" -y 2023  # Via 'hc' command alias
    hc "2024:BHC-OS:567"

Options:
    -n 10, -a, --no-pager, -o /Users/Shared/CASES, --list

What it does: opens a session, displays the captcha image in Preview (on macOS),
you type six characters, it searches, displays results (paged via less if long),
and downloads the PDF.

No Playwright, no Selenium, no third-party packages.
"""

import argparse
import http.cookiejar
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

PORTALS = {
    "sc": {
        "name": "Supreme Court of India (e-SCR)",
        "base": "https://scr.sci.gov.in/scrsearch/",
        "domain": "https://scr.sci.gov.in",
        "fcourt_type": "3",
    },
    "hc": {
        "name": "High Courts of India (eCourts Judgments)",
        "base": "https://judgments.ecourts.gov.in/pdfsearch/",
        "domain": "https://judgments.ecourts.gov.in",
        "fcourt_type": "2",
    },
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

CAPTCHA_PATH = os.environ.get("SCR_CAPTCHA_IMG") or os.path.join(
    tempfile.gettempdir(), "court-captcha.png")


# --------------------------------------------------------------------------- #
# session plumbing
# --------------------------------------------------------------------------- #
class CourtSession:
    def __init__(self, target="sc"):
        self.target = target
        self.portal = PORTALS[target]
        self.base = self.portal["base"]
        self.domain = self.portal["domain"]
        self.fcourt_type = self.portal["fcourt_type"]
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.op.addheaders = [
            ("User-Agent", UA),
            ("Accept-Language", "en-US,en;q=0.9"),
            ("Referer", self.base),
        ]

    def get(self, url):
        with self.op.open(url, timeout=60) as r:
            return r.read()

    def post(self, route, params):
        params = dict(params)
        params.update({"ajax_req": "true", "app_token": ""})
        data = urllib.parse.urlencode(params).encode()
        with self.op.open(self.base + "?p=" + route, data, timeout=60) as r:
            return r.read().decode("utf-8", "replace")

    def open_home(self):
        self.get(self.base)


def find_json(text):
    """Server prefixes junk whitespace; grab the first JSON object/array."""
    m = re.search(r"[\[{]", text)
    if not m:
        raise RuntimeError("no JSON in response:\n" + text[:400])
    return json.loads(text[m.start():])


def strip_tags(html):
    html = re.sub(r"<sup.*?</sup>", "", html, flags=re.S)
    html = re.sub(r"<br\s*/?>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&ndash;", "–").replace("&dagger;", "†")
                .replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"[ \t]+", " ", html)


# --------------------------------------------------------------------------- #
# captcha
# --------------------------------------------------------------------------- #
def ask_captcha(session, why="Enter captcha"):
    """Fetch a fresh captcha image, show it, read the answer."""
    blob = session.get(session.base + "vendor/securimage/securimage_show.php?%f" % random.random())
    with open(CAPTCHA_PATH, "wb") as f:
        f.write(blob)
    if sys.platform == "darwin" and not os.environ.get("SCR_NO_OPEN"):
        subprocess.run(["open", "-a", "Preview", CAPTCHA_PATH], check=False)
    else:
        print("captcha image:", CAPTCHA_PATH)
    ansfile = os.environ.get("SCR_CAPTCHA_ANSWER")   # headless/automation hook
    if ansfile:
        for _ in range(600):
            if os.path.exists(ansfile) and open(ansfile).read().strip():
                ans = open(ansfile).read().strip()
                os.remove(ansfile)
                return ans
            time.sleep(0.5)
        sys.exit("timed out waiting for captcha answer")

    try:
        ans = input(f"{why} [{CAPTCHA_PATH}]: ").strip()
    except EOFError:
        sys.exit("\naborted")
    return ans


# --------------------------------------------------------------------------- #
# citation parsing
# --------------------------------------------------------------------------- #
def parse_citation(text):
    """Return Supreme Court field dict for checkCaptcha / home, or None."""
    if not text:
        return None
    t = (text.upper().replace("[", " ").replace("]", " ")
             .replace("(", " ").replace(")", " ").replace(".", " "))
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("S C R", "SCR")          # "[2006] 3 S.C.R. 1" -> "2006 3 SCR 1"

    fields = {
        "neu_cit_year": "", "neu_no": "", "ncn": "",
        "citation_year": "", "citation_vol": "", "citation_supl": "",
        "citation_page": "",
    }

    m = re.match(r"^(\d{4}) (?:INSC|NCN) (\d+)$", t)
    if m:
        fields["neu_cit_year"], fields["neu_no"] = m.group(1), m.group(2)
        return fields

    # [1973] Supp. S.C.R. 1   /   1973 SUPP SCR 1
    m = re.match(r"^(\d{4}) (SUPP|SUP|S) SCR (\d+)$", t)
    if m:
        fields["citation_year"] = m.group(1)
        fields["citation_vol"] = "Supp"
        fields["citation_page"] = m.group(3)
        return fields

    m = re.match(r"^(\d{4}) (\d+) SCR (\d+)$", t)
    if m:
        fields["citation_year"] = m.group(1)
        fields["citation_vol"] = m.group(2)
        fields["citation_page"] = m.group(3)
        return fields

    m = re.match(r"^SCR (\d{4}) (\d+) (\d+)$", t)
    if m:
        fields["citation_year"] = m.group(1)
        fields["citation_vol"] = m.group(2)
        fields["citation_page"] = m.group(3)
        return fields

    return None


def describe_citation(f):
    if f["neu_no"]:
        return f"[{f['neu_cit_year']}] INSC {f['neu_no']}  (neutral citation)"
    vol = "Supp" if f["citation_vol"].lower().startswith("sup") else f["citation_vol"]
    return f"[{f['citation_year']}] {vol} S.C.R. {f['citation_page']}  (SCR volume/page)"


# --------------------------------------------------------------------------- #
# case number parsing (Supreme Court only)
# --------------------------------------------------------------------------- #
def parse_case(text):
    """Parse Supreme Court case numbers (e.g. 'WP 123/2021', 'SLP 1234/2022',
    'Civil Appeal No. 36 of 2026'). Returns case dict or None."""
    if not text:
        return None
    raw = text.strip()
    # High Court neutral citation check: 2024:DHC:1234
    if re.search(r"^\s*\[?\s*\d{4}\s*:\s*[A-Za-z0-9_-]+\s*:\s*\d+\s*\]?\s*$", raw):
        return None
    # SC neutral citation: 2026 INSC 5
    if re.search(r"^\s*(\d{4})\s*(?:INSC|NCN)\s*(\d+)\s*$", raw, re.I):
        return None
    # SCR citation: [1978] 2 S.C.R. 621
    if re.search(r"^\s*(?:\[?\d{4}\]?|\bSCR\b).*S\.?C\.?R\.?", raw, re.I):
        return None

    # Normalise abbreviations: remove dots in words like W.P., S.L.P., C.A., Crl.A.
    t = re.sub(r"(?<=[a-zA-Z])\.(?=[a-zA-Z\s\(\)\[\]]|$)", "", raw)
    t = re.sub(r"[\(\)\[\],]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().upper()

    # Match: <TYPE> [NO / NOS / NUMBER] <NUMBER> [OF / / / - / SPACE] <YEAR>
    m = re.match(
        r"^(.*?)(?:\s*(?:NO\b|NOS\b|NUMBER\b|NUM\b))?\s*[:\s#\-]*(\d+)\s*(?:OF|/|-|\s)\s*(\d{4})$",
        t, re.I
    )
    if not m:
        return None

    type_raw = m.group(1).strip()
    case_no = m.group(2).strip()
    case_year = m.group(3).strip()

    # Remove trailing 'NO' or 'NOS' if any survived
    type_clean = re.sub(r"\b(NO|NOS|NUMBER|NUM)\b", "", type_raw).strip()
    type_clean = re.sub(r"\s+", " ", type_clean).strip()

    case_type = None
    if any(type_clean == k or type_clean.startswith(k + " ") for k in ["DIARY", "DIARYNO"]):
        case_type = "DIARYNO AND DIARYYR"
    elif "CRIMINAL" in type_clean or "CRL" in type_clean or "CRA" in type_clean:
        if "WRIT" in type_clean or "WP" in type_clean:
            case_type = "WRIT PETITION (CRIMINAL)"
        elif "SPECIAL LEAVE" in type_clean or "SLP" in type_clean:
            case_type = "SPECIAL LEAVE PETITION (CRIMINAL)"
        elif "APPEAL" in type_clean or "CA" in type_clean or "CRA" in type_clean or "CRLA" in type_clean or re.search(r"\bA\b", type_clean):
            case_type = "CRIMINAL APPEAL"
        elif "TRANSFER" in type_clean or "TP" in type_clean:
            case_type = "TRANSFER PETITION (CRIMINAL)"
        elif "REVIEW" in type_clean or "RP" in type_clean:
            case_type = "REVIEW PETITION (CRIMINAL)"
        elif "CONTEMPT" in type_clean or "CP" in type_clean:
            case_type = "CONTEMPT PETITION (CRIMINAL)"
        elif "CURATIVE" in type_clean:
            case_type = "CURATIVE PETITION (CRL)"
        else:
            case_type = "CRIMINAL APPEAL"
    elif "CIVIL" in type_clean or re.search(r"\bC\b", type_clean):
        if "WRIT" in type_clean or "WP" in type_clean:
            case_type = "WRIT PETITION (CIVIL)"
        elif "SPECIAL LEAVE" in type_clean or "SLP" in type_clean:
            case_type = "SPECIAL LEAVE PETITION (CIVIL)"
        elif "APPEAL" in type_clean or "CA" in type_clean:
            case_type = "CIVIL APPEAL"
        elif "TRANSFER" in type_clean or "TP" in type_clean:
            case_type = "TRANSFER PETITION (CIVIL)"
        elif "REVIEW" in type_clean or "RP" in type_clean:
            case_type = "REVIEW PETITION (CIVIL)"
        elif "CONTEMPT" in type_clean or "CP" in type_clean:
            case_type = "CONTEMPT PETITION (CIVIL)"
        elif "CURATIVE" in type_clean:
            case_type = "CURATIVE PETITION (CIVIL)"
        else:
            case_type = "CIVIL APPEAL"
    else:
        # Defaults without Civil / Criminal explicitly specified
        if type_clean in ("WP", "WRIT", "WRIT PETITION"):
            case_type = "WRIT PETITION (CIVIL)"
        elif type_clean in ("SLP", "SPECIAL LEAVE", "SPECIAL LEAVE PETITION"):
            case_type = "SPECIAL LEAVE PETITION (CIVIL)"
        elif type_clean in ("CA", "CIVIL APPEAL"):
            case_type = "CIVIL APPEAL"
        elif type_clean in ("CRA", "CRL A", "CRLA", "CRIMINAL APPEAL"):
            case_type = "CRIMINAL APPEAL"
        elif type_clean in ("TP", "TRANSFER PETITION"):
            case_type = "TRANSFER PETITION (CIVIL)"
        elif type_clean in ("RP", "REVIEW PETITION"):
            case_type = "REVIEW PETITION (CIVIL)"
        elif type_clean in ("CP", "CONTEMPT PETITION"):
            case_type = "CONTEMPT PETITION (CIVIL)"
        elif type_clean in ("MA", "MISC APPLICATION", "MISCELLANEOUS APPLICATION"):
            case_type = "MISCELLANEOUS APPLICATION"
        elif type_clean in ("ARB PET", "ARBITRATION PETITION"):
            case_type = "ARBITRATION PETITION"
        elif type_clean in ("OS", "ORIGINAL SUIT"):
            case_type = "ORIGINAL SUIT"
        elif not type_clean:
            case_type = ""
        else:
            return None

    return {
        "case_no": case_no,
        "case_year": case_year,
        "fulltext_case_type": case_type,
        "case_no1": case_no,
        "case_year1": case_year,
        "fulltext_case_type1": case_type,
        "raw_type": type_clean,
    }


def describe_case(f):
    c_type = f.get("fulltext_case_type") or "Case"
    return f"{c_type} No. {f['case_no']} of {f['case_year']}"


# --------------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------------- #
ROW_PARAMS = {
    "iDisplayStart": "0",
    "search_txt1": "", "search_txt2": "", "search_txt3": "",
    "search_txt4": "", "search_txt5": "",
    "pet_res": "", "state_code": "", "state_code_li": "", "dist_code": "",
    "case_no": "", "case_year": "", "from_date": "", "to_date": "",
    "judge_name": "", "reg_year": "", "fulltext_case_type": "",
    "judge_txt": "", "act_txt": "", "section_txt": "",
    "judge_val": "", "act_val": "", "year_val": "", "judge_arr": "",
    "flag": "", "disp_nature": "", "search_opt": "PHRASE",
    "date_val": "", "fcourt_type": "3", "citation_yr": "",
    "citation_vol": "", "citation_supl": "", "citation_page": "",
    "case_no1": "", "case_year1": "", "pet_res1": "",
    "fulltext_case_type1": "", "citation_keyword": "", "sel_lang": "",
    "proximity": "", "ncn": "", "part": "", "bool_opt": "",
}


def parse_rows(raw_data):
    """Parse raw aaData items into clean judgment dictionaries."""
    rows = []
    for raw in raw_data:
        cell = raw[1] if len(raw) > 1 else ""
        text = strip_tags(cell)
        args = re.search(r"open_pdf\('(\d+)','(\d+)','([^']*)','([^']*)'", cell)
        if not args:
            continue
        label = re.search(r'aria-label="([^"]+)"', cell)
        if label:
            title = re.sub(r"\s*pdf\s*$", "", label.group(1)).strip()
        else:
            title = re.split(r"\s*-\s*\[|\s*Coram\s*:", text.split("Coram")[0])[0].strip()
        escr = re.search(r"\[(\d{4})\]\s*(Supp\.?\s*)?([\d]+)?\s*S\.C\.R\.\s*(\d+)",
                         text, re.I)
        ncn = re.search(r"\b(\d{4})\s*INSC\s*(\d+)\b", text)
        hc_ncn = re.search(r"\b(\d{4}\s*:\s*[A-Za-z0-9_-]+\s*:\s*\d+)\b", text)
        coram = re.search(r"Coram\s*:\s*(.+?)(?:\n|Issue|Headnote|$)", text)
        court_m = re.search(r"(?:Court|Bench)\s*:\s*([^|\n]+)", text)
        court_str = court_m.group(1).strip() if court_m else ""
        court_str = re.split(r"\s*(?:Split\s+view|HTML\s+view|Flip\s+view|PDF)\b", court_str, flags=re.I)[0].strip()
        date = re.search(r"Decision Date\s*:\s*([\d-]+)", text)
        case_no_m = re.search(r"Case No\s*:\s*([^|\n]+)", text, re.I)

        citation_tag = ""
        if ncn:
            citation_tag = f"{ncn.group(1)} INSC {ncn.group(2)}"
        elif hc_ncn:
            citation_tag = re.sub(r"\s+", "", hc_ncn.group(1))

        rows.append({
            "title": title,
            "escr": (lambda m: "[%s] %sS.C.R. %s" % (
                m.group(1), "Supp. " if m.group(2) else (m.group(3) + " "),
                m.group(4)))(escr) if escr else "",
            "ncn": citation_tag,
            "coram": coram.group(1).strip() if coram else "",
            "court": court_str,
            "date": date.group(1) if date else "",
            "case_no": case_no_m.group(1).strip() if case_no_m else "",
            "val": args.group(1),
            "year": args.group(2),
            "path": args.group(3),
            "nc_display": args.group(4),
            "html": cell,
        })
    return rows


def search(session, query_type, query_val, limit=None, mode="PHRASE", year=None):
    """Captcha-gate, then pull the result rows. Returns (rows, captcha, want_year)."""
    case_info = None
    if query_type == "citation":
        fields = parse_citation(query_val)
        if not fields:
            sys.exit(f"could not read citation: {query_val}")
        search_text = ""
        search_opt = "PHRASE"
        want_year = fields["neu_cit_year"] or fields["citation_year"]
        desc = describe_citation(fields)
    elif query_type == "case":
        case_info = parse_case(query_val)
        if not case_info:
            sys.exit(f"could not read case number: {query_val}")
        fields = {
            "neu_cit_year": "", "neu_no": "", "ncn": "",
            "citation_year": "", "citation_vol": "", "citation_supl": "", "citation_page": "",
            "case_no": case_info["case_no"],
            "case_year": case_info["case_year"],
            "fulltext_case_type": case_info["fulltext_case_type"],
            "case_no1": case_info["case_no"],
            "case_year1": case_info["case_year"],
            "fulltext_case_type1": case_info["fulltext_case_type"],
        }
        search_text = ""
        search_opt = "PHRASE"
        want_year = str(year) if year else case_info["case_year"]
        desc = describe_case(case_info)
    else:
        fields = {
            "neu_cit_year": "", "neu_no": "", "ncn": "",
            "citation_year": str(year) if year else "",
            "citation_vol": "", "citation_supl": "", "citation_page": "",
        }
        search_text = query_val
        search_opt = mode.upper()
        want_year = str(year) if year else ""
        desc = f'"{search_text}" (mode: {search_opt})' + (f" for year {year}" if year else "")

    print(f"searching {session.portal['name']}: {desc}")
    for _ in range(6):
        session.open_home()
        cap = ask_captcha(session)

        captcha_payload = {
            "captcha": cap,
            "search_text": search_text,
            "search_txt1": search_text,
            "search_opt": search_opt,
            "fcourt_type": session.fcourt_type,
            "escr_flag": "",
            "proximity": "",
            "sel_lang": "",
            **fields,
        }
        body = session.post("pdf_search/checkCaptcha", captcha_payload)
        if '"captcha_status":"Y"' in body:
            break
        print("  rejected — try the next one.")
    else:
        sys.exit("captcha failed repeatedly")

    batch_size = 50
    first_fetch = batch_size if limit is None else min(batch_size, limit)

    params = dict(ROW_PARAMS)
    params.update({
        "iDisplayStart": "0",
        "iDisplayLength": str(first_fetch),
        "captcha": cap,
        "fcourt_type": session.fcourt_type,
        "search_opt": search_opt,
        "search_txt1": search_text,
        "search_text": search_text,
        "text": search_text,
        "citation_yr": fields.get("citation_year", ""),   # results call wants *_yr
        "year_val": fields.get("citation_year", ""),
        **fields,
    })
    body = session.post("pdf_search/home", params)
    if '"session_expire":"Y"' in body:
        print("session timed out before the results came back; new captcha.")
        return search(session, query_type, query_val, limit=limit, mode=mode, year=year)

    j = find_json(body)["reportrow"]
    raw_data = j.get("aaData", [])
    rows = parse_rows(raw_data)

    # If case query yielded 0 results with specific case_type, retry without case_type filter
    if query_type == "case" and not rows and fields.get("fulltext_case_type"):
        params["fulltext_case_type"] = ""
        params["fulltext_case_type1"] = ""
        body = session.post("pdf_search/home", params)
        if '"session_expire":"Y"' not in body:
            j = find_json(body).get("reportrow", {})
            raw_data = j.get("aaData", [])
            rows = parse_rows(raw_data)

    # If still 0 results for case query, fallback to text search by case number / year
    if query_type == "case" and not rows:
        c_num = fields.get("case_no", "")
        c_yr = fields.get("case_year", "")
        fallback_q = f"{c_num}/{c_yr}"
        params["case_no"] = ""
        params["case_no1"] = ""
        params["case_year"] = ""
        params["case_year1"] = ""
        params["fulltext_case_type"] = ""
        params["fulltext_case_type1"] = ""
        params["search_opt"] = "PHRASE"
        params["search_txt1"] = fallback_q
        params["search_text"] = fallback_q
        params["text"] = fallback_q
        params["citation_yr"] = c_yr
        params["year_val"] = c_yr
        body = session.post("pdf_search/home", params)
        if '"session_expire":"Y"' not in body:
            j = find_json(body).get("reportrow", {})
            raw_data = j.get("aaData", [])
            rows = parse_rows(raw_data)

    try:
        total = int(j.get("iTotalDisplayRecords") or len(raw_data))
    except (ValueError, TypeError):
        total = len(raw_data)

    target_count = total if limit is None else min(total, limit)
    offset = len(raw_data)

    if total > len(rows) and target_count > len(rows):
        print(f"found {total} results; loading all...")

    while len(rows) < target_count and offset < total:
        fetch_len = min(batch_size, target_count - len(rows))
        params["iDisplayStart"] = str(offset)
        params["iDisplayLength"] = str(fetch_len)
        body = session.post("pdf_search/home", params)
        if '"session_expire":"Y"' in body:
            print("session timed out while loading additional pages.")
            break
        resp_row = find_json(body).get("reportrow", {})
        page_raw = resp_row.get("aaData", [])
        if not page_raw:
            break
        offset += len(page_raw)
        new_rows = parse_rows(page_raw)
        if not new_rows:
            break
        rows.extend(new_rows)

    if limit is not None:
        rows = rows[:limit]

    # Rank results: for case queries, prioritize exact case number & type; for others, year match
    if query_type == "case" and rows and case_info:
        c_num = case_info["case_no"]
        c_yr = case_info["case_year"]
        c_type = (case_info.get("fulltext_case_type") or "").upper()

        def case_rank(r):
            score = 0
            rc = (r.get("case_no") or "").upper()
            title = (r.get("title") or "").upper()
            if c_num and c_yr and f"{c_num}/{c_yr}" in rc.replace(" ", ""):
                score -= 20
            elif c_num and c_num in rc:
                score -= 10
            if c_type and (c_type in rc or c_type in title):
                score -= 10
            if r.get("year") == want_year:
                score -= 2
            return score

        rows.sort(key=case_rank)
    elif want_year:
        rows.sort(key=lambda r: r["year"] != want_year)

    return rows, cap, want_year


# --------------------------------------------------------------------------- #
# download
# --------------------------------------------------------------------------- #
def fetch_pdf(session, row, cap, asked=None):
    """openpdfcaptcha -> outputfile -> fetch bytes. Re-asks captcha if needed."""
    asked = asked if asked is not None else [0]
    params = {
        "val": row["val"], "lang_flg": "undefined", "path": row["path"],
        "citation_year": row["year"], "fcourt_type": session.fcourt_type,
        "nc_display": row["nc_display"],
    }
    body = session.post("pdf_search/openpdfcaptcha", params)
    try:
        j = find_json(body)
    except RuntimeError:
        raise SystemExit("unexpected response:\n" + body[:500])

    if j.get("session_expire") == "Y" or "captcha_image" in body:
        if asked[0] >= 2:
            raise SystemExit("captcha refused; giving up")
        asked[0] += 1
        cap = ask_captcha(session, "PDF captcha")
        body = session.post("pdf_search/openpdf",
                            {**params, "captcha1": cap})
        j = find_json(body)
        if j.get("message"):
            raise SystemExit("server said: " + str(j["message"]))

    out = j.get("outputfile")
    if not out:
        raise SystemExit("no PDF path returned:\n" + body[:500])

    for _ in range(2):                      # the tmp path can be reaped; retry once
        blob = session.get(session.domain + out)
        if blob.startswith(b"%PDF"):
            return blob
        body = session.post("pdf_search/openpdfcaptcha", params)
        out = find_json(body).get("outputfile")
        if not out:
            break
    raise SystemExit(f"could not pull a valid PDF ({len(blob)} bytes)")


def verify(path):
    """Echo the citation line printed on page 1, so you can eyeball the match."""
    try:
        txt = subprocess.run(["pdftotext", "-f", "1", "-l", "2", path, "-"],
                             capture_output=True, text=True, timeout=90).stdout
    except (OSError, subprocess.SubprocessError):
        return
    m = re.search(r"\[\d{4}\]\s*(?:\d+|Supp\.?)\s*S\.C\.R\.[^\n]*", txt, re.I)
    if m:
        print("cites as: " + " ".join(m.group(0).split()))
        return
    m_hc = re.search(r"\b\d{4}:[A-Za-z0-9_-]+:\d+\b", txt)
    if m_hc:
        print("neutral citation: " + m_hc.group(0))


def safe_name(row):
    base = re.sub(r"[^A-Za-z0-9]+", " ", row["title"]).strip()
    base = re.sub(r"\s+", "-", base)[:70].strip("-")
    tag = (row.get("ncn") or row.get("escr") or row.get("case_no") or row.get("court") or row.get("year") or "").replace(" ", "-").replace(":", "-")
    return f"{tag}_{base}" if (tag and base) else (tag or base or "judgment")


# --------------------------------------------------------------------------- #
# display and paging
# --------------------------------------------------------------------------- #
def format_results(rows, want_year=None):
    """Format the list of hits for terminal or pager display."""
    lines = [""]
    for i, r in enumerate(rows, 1):
        flag = "   (other year)" if (want_year and r.get("year") and r["year"] != want_year) else ""
        cites = [c for c in [r.get("ncn"), r.get("escr")] if c]
        cite_str = "  ".join(cites) or "—"
        date_str = r.get("date") or ""
        lines.append(f"{i}. {cite_str:<36} {date_str}{flag}")
        lines.append(f"   {r['title']}")
        if r.get("case_no"):
            lines.append(f"   Case:  {r['case_no']}")
        if r.get("court"):
            lines.append(f"   Court: {r['court']}")
        if r.get("coram"):
            lines.append(f"   Coram: {r['coram']}")
        lines.append("")
    return "\n".join(lines)


def page_output(text, disable_pager=False):
    """Display text using less or pager when output exceeds screen height."""
    if disable_pager or not (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()):
        print(text)
        return

    term_lines = shutil.get_terminal_size((80, 24)).lines
    text_lines = text.count("\n") + 1

    # If it fits within the terminal window, print directly
    if text_lines < term_lines - 2:
        print(text)
        return

    # Use less with:
    # -F (quit if one screen)
    # -R (raw control characters / formatting)
    # -X (leave contents on screen upon exit)
    pager = os.environ.get("PAGER") or "less -FRX"
    try:
        proc = subprocess.Popen(pager, shell=True, stdin=subprocess.PIPE, text=True)
        proc.communicate(input=text)
    except Exception:
        print(text)


# --------------------------------------------------------------------------- #
def main():
    prog = os.path.basename(sys.argv[0])
    is_hc_default = "hc" in prog.lower()
    default_portal_name = "High Courts" if is_hc_default else "Supreme Court"

    ap = argparse.ArgumentParser(
        description=f"Download judgment PDFs from {default_portal_name} (Supreme Court / High Courts).",
        epilog="examples:\n"
               "  scr '2026 INSC 5'                 # Supreme Court Neutral Citation\n"
               "  scr 'WP (C) 123/2021'             # Supreme Court Case Number (WP, SLP, CA, etc.)\n"
               "  scr 'SLP 1234/2022'               # Supreme Court Special Leave Petition\n"
               "  scr 'CA 36/2026'                  # Supreme Court Civil Appeal\n"
               "  scr '[1978] 2 S.C.R. 621'         # SCR volume/page\n"
               "  scr 'Kesavananda Bharati'         # Supreme Court keyword search\n"
               "  scr --hc 'patent infringement'    # High Court search (judgments.ecourts.gov.in)\n"
               "  hc '2024:DHC:1234'                # High Court neutral citation\n"
               "  hc 'arbitration' -y 2023          # High Court keyword search with year filter\n"
               "  hc --sc '2026 INSC 5'             # Search Supreme Court from hc\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default=None,
                    help="citation (e.g. '2026 INSC 5'), case number (e.g. 'WP 123/2021', 'SLP 1234/2022', 'CA 36/2026'), or search string")
    ap.add_argument("--hc", "--high-court", dest="high_court", action="store_true",
                    help="search High Court judgments (https://judgments.ecourts.gov.in/pdfsearch/)")
    ap.add_argument("--sc", "--supreme-court", dest="supreme_court", action="store_true",
                    help="search Supreme Court judgments (https://scr.sci.gov.in/scrsearch/)")
    ap.add_argument("-s", "--string", dest="string_query", default=None,
                    help="search by string/keyword (explicitly treated as text query)")
    ap.add_argument("-c", "--citation", dest="citation_query", default=None,
                    help="search by citation (explicitly treated as citation query)")
    ap.add_argument("-C", "--case", dest="case_query", default=None,
                    help="search by case number (e.g. 'WP 123/2021', 'SLP 1234/2022', 'CA 36/2026') [Supreme Court only]")
    ap.add_argument("-m", "--mode", choices=["phrase", "any", "all"], default="phrase",
                    help="search mode for string queries: phrase (default), any, all")
    ap.add_argument("-y", "--year", default=None,
                    help="filter results by year (e.g. '2024')")
    ap.add_argument("-n", "--results", default=None,
                    help="how many hits to list (default: all matching results, or specify a number like 10)")
    ap.add_argument("-a", "--all", action="store_true",
                    help="list all matching results (same as default without -n)")
    ap.add_argument("--no-pager", action="store_true",
                    help="disable pager (less) and print directly to terminal")
    ap.add_argument("-o", "--outdir", default="/Users/Shared/CASES",
                    help="directory to save downloaded PDF (default: /Users/Shared/CASES)")
    ap.add_argument("-i", "--index", type=int, default=None,
                    help="download this hit non-interactively (1-based)")
    ap.add_argument("--list", action="store_true", help="list only, no download")
    a = ap.parse_args()

    # Determine result limit
    if a.all or a.results is None or str(a.results).lower() == "all":
        limit = None
    else:
        try:
            limit = int(a.results)
        except ValueError:
            sys.exit(f"invalid value for --results: '{a.results}'. Must be a number or 'all'.")

    # Determine target portal (Supreme Court 'sc' vs High Court 'hc')
    if a.high_court and a.supreme_court:
        sys.exit("cannot specify both --hc and --sc simultaneously.")
    elif a.high_court:
        target = "hc"
    elif a.supreme_court:
        target = "sc"
    elif is_hc_default:
        target = "hc"
    else:
        # Check if query matches High Court neutral citation (e.g. 2024:DHC:1234)
        raw_q = a.query or a.citation_query or a.case_query or a.string_query or ""
        if re.search(r"^\s*\[?\s*\d{4}\s*:\s*[A-Za-z0-9_-]+\s*:\s*\d+\s*\]?\s*$", raw_q):
            target = "hc"
        else:
            target = "sc"

    # Enforce High Court restriction on case queries
    if a.case_query and (target == "hc" or a.high_court):
        sys.exit("case number search is only supported for Supreme Court, not High Court.")

    # Determine query type and parameters
    year_filter = a.year
    if a.string_query:
        query_type = "string"
        query_val = a.string_query
    elif a.citation_query:
        if target == "hc":
            query_type = "string"
            query_val = a.citation_query
        else:
            query_type = "citation"
            query_val = a.citation_query
            if not parse_citation(query_val):
                sys.exit(
                    f"could not read Supreme Court citation: '{query_val}'.\n"
                    "  Expected '2026 INSC 5', '2026 1 SCR 1', '[1978] 2 S.C.R. 621'\n"
                    "  or '1973 Supp SCR 1'.\n"
                    "  (To search as free text/string instead, use: scr -s \"" + query_val + "\")")
    elif a.case_query:
        query_type = "case"
        query_val = a.case_query
        parsed_c = parse_case(query_val)
        if not parsed_c:
            sys.exit(
                f"could not read Supreme Court case number: '{query_val}'.\n"
                "  Expected 'WP 123/2021', 'WP (C) 123/2021', 'SLP 1234/2022', 'SLP (Crl) 567/2023',\n"
                "  'Civil Appeal 36/2026', 'Diary No. 12345/2023', etc.\n"
                "  (To search as free text/string instead, use: scr -s \"" + query_val + "\")")
        if not year_filter and parsed_c.get("case_year"):
            year_filter = parsed_c["case_year"]
    elif a.query:
        if target == "hc":
            query_type = "string"
            query_val = a.query
            m_hc = re.match(r"^\s*\[?(\d{4})\s*:\s*[A-Za-z0-9_-]+\s*:\s*\d+\]?\s*$", a.query)
            if m_hc and not year_filter:
                year_filter = m_hc.group(1)
        else:
            parsed = parse_citation(a.query)
            if parsed:
                query_type = "citation"
                query_val = a.query
            else:
                parsed_c = parse_case(a.query)
                if parsed_c:
                    query_type = "case"
                    query_val = a.query
                    if not year_filter and parsed_c.get("case_year"):
                        year_filter = parsed_c["case_year"]
                else:
                    query_type = "string"
                    query_val = a.query
    else:
        ap.print_help()
        sys.exit(1)

    session = CourtSession(target)
    rows, cap, want_year = search(session, query_type, query_val, limit=limit,
                                  mode=a.mode, year=year_filter)

    if not rows:
        print("no results.")
        return

    if query_type == "citation" and len(rows) > 1:
        cit_fields = parse_citation(query_val)
        if cit_fields and cit_fields.get("citation_page"):
            print("note: the portal matches SCR citations on year + page only; the "
                  "volume is ignored, so check the labels below before downloading.")

    formatted = format_results(rows, want_year)
    page_output(formatted, disable_pager=a.no_pager)

    if a.list:
        return

    pick = a.index
    if pick is None:
        while True:
            try:
                prompt_msg = f"download which? [1-{len(rows)}, enter = 1, 'l' to re-list, 'q' to quit]: "
                raw = input(prompt_msg).strip().lower()
            except EOFError:
                sys.exit("\naborted")

            if raw == "" or raw == "1":
                pick = 1
                break
            elif raw in ("q", "quit", "exit"):
                print("aborted.")
                return
            elif raw in ("l", "list", "p", "page"):
                page_output(formatted, disable_pager=a.no_pager)
                continue
            elif raw.isdigit():
                val = int(raw)
                if 1 <= val <= len(rows):
                    pick = val
                    break
                else:
                    print(f"please enter a number between 1 and {len(rows)}.")
            else:
                print(f"invalid selection '{raw}'. Enter a number (1-{len(rows)}), 'l' to re-list, or 'q' to quit.")

    row = rows[max(0, min(pick, len(rows)) - 1)]

    blob = fetch_pdf(session, row, cap)
    outdir = os.path.expanduser(a.outdir)
    os.makedirs(outdir, exist_ok=True)
    dest = os.path.join(outdir, safe_name(row) + ".pdf")
    with open(dest, "wb") as f:
        f.write(blob)
    print(f"saved {dest}  ({len(blob)//1024} KB)")
    verify(dest)


if __name__ == "__main__":
    main()
