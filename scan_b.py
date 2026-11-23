"""Second daily job pull. Runs on GitHub Actions after scan.py, writes jobs/latest_b.json."""
import json, time, datetime, os, unicodedata
import pandas as pd
from jobspy import scrape_jobs

START = time.time()
TIME_BUDGET = 25 * 60   # stop starting new searches after 25 minutes; the file is still written

# Search words. Bengaluru gets every term; other places get the core terms.
TERMS = [
    "food R&D manager",
    "nutraceutical formulation",
    "health supplements R&D",
    "regulatory affairs food",
    "food scientific affairs",
    "FSSAI regulatory",
    "new product development food",
    "beverage product development",
    "fermentation scientist",
]
CORE = TERMS[:5]
OTHER_CITIES = "Pune, Mumbai, Hyderabad, Delhi"   # Naukri accepts several cities in one search
UAE = "United Arab Emirates"

# Target employers. Google Jobs is searched by company name, and their jobs are flagged "watch".
WATCH = ["Nestle", "PepsiCo", "Mondelez", "Unilever", "Hindustan Unilever", "ITC", "Britannia",
         "Marico", "Dabur", "Himalaya", "Abbott", "dsm-firmenich", "DSM", "IFF", "Givaudan", "Kerry",
         "Cargill", "ADM", "Griffith", "Amway", "Herbalife", "Danone", "Mars", "Kellanova", "Haleon"]
WATCH_QUERIES = [
    "food R&D OR regulatory OR nutrition scientist jobs at Nestle OR PepsiCo OR Mondelez OR Unilever OR ITC OR Britannia in India",
    "R&D OR regulatory OR scientific affairs jobs at Marico OR Dabur OR Himalaya OR Abbott Nutrition OR Amway OR Herbalife in India",
    "food scientist OR regulatory OR application jobs at dsm-firmenich OR IFF OR Givaudan OR Kerry OR Cargill OR ADM in India",
]

HOURS = 168        # 7 days (India)
HOURS_UAE = 336    # 14 days (UAE)
DESC_CHARS = 8000

# Searches in priority order: Bengaluru first, so it is never cut by the time budget.
searches = []
for t in TERMS:
    searches.append(dict(sites=["linkedin"], term=t, location="Bengaluru, Karnataka, India", n=30, city="bengaluru"))
    searches.append(dict(sites=["naukri"], term=t, location="Bengaluru", n=30, city="bengaluru"))
for t in TERMS:
    searches.append(dict(sites=["google"], term=t, google=f"{t} jobs in Bengaluru since last week", n=20, city="bengaluru"))
    searches.append(dict(sites=["glassdoor"], term=t, location="Bengaluru", n=20, city="bengaluru"))
for q in WATCH_QUERIES:
    searches.append(dict(sites=["google"], term="watch list", google=q, n=30))
for t in TERMS:
    searches.append(dict(sites=["linkedin"], term=t, location="India", n=25))
    searches.append(dict(sites=["naukri"], term=t, location=OTHER_CITIES, n=25))
    searches.append(dict(sites=["indeed"], term=t, location="India", n=25))
for t in CORE:
    searches.append(dict(sites=["linkedin"], term=t, location=UAE, n=25, hours=HOURS_UAE, region="uae"))
    searches.append(dict(sites=["indeed"], term=t, location=UAE, n=25, hours=HOURS_UAE, region="uae",
                         country="united arab emirates"))
    searches.append(dict(sites=["bayt"], term=t, location=UAE, n=25, hours=HOURS_UAE, region="uae"))

# Remember when each job was first seen, so the daily list can show only new ones.
# The map is kept inside latest_b.json itself (key "first_seen"), so no extra file is needed.
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
first_seen = {}
try:
    with open("jobs/latest_b.json") as f:
        old = json.load(f)
    first_seen = old.get("first_seen") or {}
    if not first_seen:  # first run after this change: treat last run's jobs as already seen
        seed = old.get("generated_utc") or now
        first_seen = {j["job_url"]: seed for j in old.get("jobs", []) if j.get("job_url")}
except Exception:
    pass

frames, log = [], []
for s in searches:
    entry = {k: v for k, v in s.items() if k != "n"}
    if time.time() - START > TIME_BUDGET:
        log.append({**entry, "count": 0, "ok": False, "error": "skipped: time budget reached"})
        continue
    try:
        df = scrape_jobs(site_name=s["sites"], search_term=s["term"], google_search_term=s.get("google"),
                         location=s.get("location"), results_wanted=s["n"], hours_old=s.get("hours", HOURS),
                         country_indeed=s.get("country", "india"),
                         linkedin_fetch_description=True, fetch_description=True, verbose=0)
        n = 0 if df is None else len(df)
        if n:
            df["search_term"], df["region"] = s["term"], s.get("region", "india")
            frames.append(df)
        log.append({**entry, "count": n, "ok": True})
    except Exception as e:
        log.append({**entry, "count": 0, "ok": False, "error": str(e)[:300]})
    time.sleep(3)

EXACT = {"itc", "itc limited", "adm", "iff", "dsm", "mars", "mars inc", "mars wrigley"}

def on_watch(company):
    c = unicodedata.normalize("NFKD", company or "").encode("ascii", "ignore").decode().lower().strip()
    return c in EXACT or any(w.lower() in c for w in WATCH if len(w) > 4)

keep = ["site", "region", "search_term", "title", "company", "location", "date_posted",
        "job_url", "job_url_direct", "job_level", "is_remote", "description"]
jobs = []
if frames:
    all_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["job_url"])
    for c in keep:
        if c not in all_df.columns:
            all_df[c] = None
    all_df = all_df[keep].astype(object).where(pd.notna(all_df[keep]), None)
    for r in all_df.to_dict("records"):
        r["date_posted"] = str(r["date_posted"]) if r["date_posted"] else None
        if r["description"]:
            r["description"] = str(r["description"])[:DESC_CHARS]
        r["watch"] = on_watch(r["company"])
        r["first_seen"] = first_seen.setdefault(r["job_url"], now)
        jobs.append(r)

cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=45)).strftime("%Y-%m-%dT%H:%MZ")
first_seen = {u: d for u, d in first_seen.items() if d >= cutoff}
out = {"generated_utc": now, "hours": HOURS, "hours_uae": HOURS_UAE, "job_count": len(jobs),
       "new_this_run": sum(j["first_seen"] == now for j in jobs),
       "minutes": round((time.time() - START) / 60, 1),
       "source_status": log, "jobs": jobs, "first_seen": first_seen}
os.makedirs("jobs", exist_ok=True)
with open("jobs/latest_b.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(f"{len(jobs)} jobs ({out['new_this_run']} new this run) in {out['minutes']} min; "
      f"failed or skipped searches: {sum(not l['ok'] for l in log)} of {len(log)}")
