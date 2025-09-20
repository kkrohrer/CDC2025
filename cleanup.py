import os
import json
import time
from pathlib import Path

import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# Config 
MODEL_NAME = "gpt-4o-mini"
TEMPERATURE = 0.3
SYSTEM_PROMPT = Path("md.md").read_text(encoding="utf-8")

# Load env
load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Missing OPENAI_API_KEY. Put it in .env.")

client = OpenAI()

# Data load & filter
df = pd.read_csv("SpaceData.csv", comment="#")
df = df[df["default_flag"] == 1].copy()

base_cols = [
    "pl_name","hostname","sy_snum","sy_pnum","disc_year",
    "pl_orbper","st_teff","pl_orbeccen","ra","dec","sy_gaiamag"
]
cols = list(base_cols)
if "pl_bmasse" in df.columns:
    cols.append("pl_bmasse")

required = ["pl_name","hostname","disc_year","st_teff","pl_orbper","ra","dec","sy_gaiamag"]
df = df[cols].dropna(subset=required).copy()

print(f"Dataset shape after filters: {df.shape}")
print(df.head(3))

# Helpers for the LLM 
def ask_openai(model: str, system_prompt: str, user_payload: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload.strip() + "\n\nRespond ONLY with JSON."},
        ],
        temperature=TEMPERATURE,
        response_format={"type": "json_object"},  # force valid JSON
    )
    return resp.choices[0].message.content

def host_bundle_to_prompt(hostname: str, g: pd.DataFrame) -> str:
    first = g.iloc[0]
    has_mass = "pl_bmasse" in g.columns
    planets = []
    for _, r in g.iterrows():
        planets.append({
            "pl_name": r["pl_name"],
            "pl_orbper": float(r["pl_orbper"]),
            "pl_orbeccen": max(0.0, float(r["pl_orbeccen"])) if pd.notna(r["pl_orbeccen"]) else None,
            "pl_bmasse": float(r["pl_bmasse"]) if has_mass and pd.notna(r.get("pl_bmasse")) else None,
        })
    payload = {
        "hostname": hostname,
        "disc_years": sorted(set(int(y) for y in g["disc_year"].dropna().astype(int))),
        "st_teff": float(first["st_teff"]),
        "sy_snum": int(first["sy_snum"]),
        "sy_pnum": int(g.shape[0]),
        "ra": float(first["ra"]),
        "dec": float(first["dec"]),
        "sy_gaiamag": float(first["sy_gaiamag"]),
        "planets": planets,
        "notes": "Multiple planets included for one artist persona."
    }
    return json.dumps(payload, ensure_ascii=False)

def safe_filename(name: str) -> str:
    # keep it simple and cross-platform safe
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)

# Run per host 
out_jsonl_path = Path("cosmic_dj_results.jsonl")
per_host_dir = Path("outputs/cosmic_dj")
per_host_dir.mkdir(parents=True, exist_ok=True)

summary_rows = []

with out_jsonl_path.open("w", encoding="utf-8") as all_out:
    grouped = df.groupby("hostname", sort=False)
    print(f"Unique host stars: {len(grouped)}")

    for host, g in grouped:
        user_payload = host_bundle_to_prompt(host, g)

        try:
            raw = ask_openai(MODEL_NAME, SYSTEM_PROMPT, user_payload)
            try:
                obj = json.loads(raw)
                has_json = True
            except Exception:
                obj = {"_raw": raw, "_host_payload": json.loads(user_payload)}
                has_json = False

            # Write to master JSONL
            all_out.write(json.dumps({"hostname": host, "result": obj}, ensure_ascii=False) + "\n")

            # Also write ONE-LINE JSONL per host
            host_file = per_host_dir / f"{safe_filename(host)}.jsonl"
            with host_file.open("w", encoding="utf-8") as hf:
                hf.write(json.dumps({"hostname": host, "result": obj}, ensure_ascii=False) + "\n")

            # Small summary row
            persona = None
            if isinstance(obj, dict):
                ap = obj.get("Artist Persona") or obj.get("artist_persona") or {}
                if isinstance(ap, dict):
                    persona = ap.get("Name") or ap.get("name")

            summary_rows.append({
                "hostname": host,
                "n_planets": g.shape[0],
                "artist_name": persona,
                "has_json": has_json,
            })

        except Exception as e:
            summary_rows.append({
                "hostname": host, "n_planets": g.shape[0],
                "artist_name": None, "has_json": False
            })
            print(f"[WARN] Host {host} failed: {e}")

        time.sleep(0.25)  # gentle pacing for rate limits

pd.DataFrame(summary_rows).to_csv("cosmic_dj_summary.csv", index=False)
print("Done. Wrote:")
print(" - cosmic_dj_results.jsonl")
print(" - outputs/cosmic_dj/<host>.jsonl  (one line per host)")
print(" - cosmic_dj_summary.csv")
