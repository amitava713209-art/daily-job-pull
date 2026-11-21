"""Daily job pull for the morning scan. Runs on GitHub Actions, writes jobs/latest.json."""
import json, time, datetime, os, traceback
import pandas as pd
from jobspy import scrape_jobs

INDIA = ["Bengaluru, Karnataka, India", "Pune, Maharashtra, India", "Hyderabad, Telangana, India"]
UAE = "United Arab Emirates"

TERMS = {
    "product": ["digital banking product", "head of product banking", "retail banking product director",
                "vice president product management bank", "head digital lending"],
    "consulting": ["banking practice head", "banking transformation director", "BFS client partner",
                   "core banking transformation", "BFSI delivery head", "banking consulting director"],
}
HOURS_INDIA = 168   # 7 days
HOURS_UAE = 336     # 14 days
PER_SEARCH = 25
DESC_CHARS = 8000

searches = []
for track, terms in TERMS.items():
    for t in terms:
        for loc in INDIA:
            searches.append(dict(track=track, sites=["linkedin"], term=t, location=loc))
            searches.append(dict(track=track, sites=["naukri"], term=t, location=loc.split(",")[0]))
        searches.append(dict(track=track, sites=["indeed"], term=t, location="India", country="india"))
        searches.append(dict(track=track, sites=["linkedin"], term=t, location=UAE, hours=HOURS_UAE))
        searches.append(dict(track=track, sites=["indeed"], term=t, location=UAE, country="united arab emirates", hours=HOURS_UAE))
        searches.append(dict(track=track, sites=["bayt"], term=t, location=UAE, hours=HOURS_UAE))

frames, log = [], []
for s in searches:
    try:
        df = scrape_jobs(site_name=s["sites"], search_term=s["term"], location=s["location"],
                         results_wanted=PER_SEARCH, hours_old=s.get("hours", HOURS_INDIA),
                         country_indeed=s.get("country", "india"),
                         linkedin_fetch_description=True, fetch_description=True, verbose=0)
        n = 0 if df is None else len(df)
        if n:
            df["track"], df["search_term"] = s["track"], s["term"]
            frames.append(df)
        log.append({**s, "count": n, "ok": True})
    except Exception as e:
        log.append({**s, "count": 0, "ok": False, "error": str(e)[:300]})
    time.sleep(4)

keep = ["site", "track", "search_term", "title", "company", "location", "date_posted",
        "job_url", "job_url_direct", "job_level", "description"]
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
out = {"generated_utc": now, "hours_india": HOURS_INDIA, "hours_uae": HOURS_UAE, "job_count": len(jobs),
       "source_status": log, "jobs": jobs}
os.makedirs("jobs", exist_ok=True)
with open("jobs/latest.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(f"{len(jobs)} jobs; failed searches: {sum(not l['ok'] for l in log)} of {len(log)}")
