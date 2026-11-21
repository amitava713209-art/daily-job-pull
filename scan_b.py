"""Second daily job pull. Runs on GitHub Actions after scan.py, writes jobs/latest_b.json."""
import json, time, datetime, os
import pandas as pd
from jobspy import scrape_jobs

# Naukri accepts several cities in one search. LinkedIn and Indeed search all of India;
# the city filter is applied later, when the results are read.
CITIES = "Bengaluru, Pune, Mumbai, Hyderabad, Delhi"

TERMS = [
    "food R&D manager",
    "new product development food",
    "beverage product development",
    "nutraceutical R&D",
    "regulatory affairs food",
    "scientific affairs nutrition",
    "claims substantiation",
    "fermentation scientist",
]
HOURS = 168        # 7 days
PER_SEARCH = 40
DESC_CHARS = 8000

searches = []
for t in TERMS:
    searches.append(dict(sites=["linkedin"], term=t, location="India"))
    searches.append(dict(sites=["naukri"], term=t, location=CITIES))
    searches.append(dict(sites=["indeed"], term=t, location="India"))

frames, log = [], []
for s in searches:
    try:
        df = scrape_jobs(site_name=s["sites"], search_term=s["term"], location=s["location"],
                         results_wanted=PER_SEARCH, hours_old=HOURS, country_indeed="india",
                         linkedin_fetch_description=True, fetch_description=True, verbose=0)
        n = 0 if df is None else len(df)
        if n:
            df["search_term"] = s["term"]
            frames.append(df)
        log.append({**s, "count": n, "ok": True})
    except Exception as e:
        log.append({**s, "count": 0, "ok": False, "error": str(e)[:300]})
    time.sleep(4)

keep = ["site", "search_term", "title", "company", "location", "date_posted",
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
        jobs.append(r)

now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
out = {"generated_utc": now, "hours": HOURS, "job_count": len(jobs), "source_status": log, "jobs": jobs}
os.makedirs("jobs", exist_ok=True)
with open("jobs/latest_b.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(f"{len(jobs)} jobs; failed searches: {sum(not l['ok'] for l in log)} of {len(log)}")
