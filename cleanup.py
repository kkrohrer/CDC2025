import os, json, time, argparse
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, APIError, RateLimitError, APITimeoutError

# CLI
def parse_args():
    ap = argparse.ArgumentParser(description="Cosmic DJ per-row runner")
    ap.add_argument("--input", default="SpaceData.csv", help="Input CSV (SpaceData.csv)")
    ap.add_argument("--prompt", default="md.md", help="System prompt file (md.md)")
    ap.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    ap.add_argument("--max-rows", type=int, default=10, help="Limit rows processed (None for all)")
    ap.add_argument("--sleep", type=float, default=0.15, help="Delay between requests (s)")
    ap.add_argument("--out-jsonl", default="cosmic_dj_results_per_line.jsonl", help="Output JSONL")
    ap.add_argument("--summary-csv", default="cosmic_dj_summary_per_line.csv", help="Summary CSV")
    return ap.parse_args()

args = parse_args()

# env & client
load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Missing OPENAI_API_KEY in .env")

MODEL_NAME = args.model
client = OpenAI()

SYSTEM_PROMPT = Path(args.prompt).read_text(encoding="utf-8")

# Data loading
df = pd.read_csv(args.input, comment="#")
df = df[df["default_flag"] == 1].copy()

base_cols = [
    "pl_name","hostname","sy_snum","sy_pnum","disc_year",
    "pl_orbper","st_teff","pl_orbeccen","ra","dec","sy_gaiamag"
]
cols = list(base_cols)
if "pl_bmasse" in df.columns:
    cols.append("pl_bmasse")

required = ["pl_name","hostname","disc_year","st_teff","pl_orbper","ra","dec","sy_gaiamag"]
if "pl_bmasse" in df.columns:
    required.append("pl_bmasse")

df = df[cols].dropna(subset=required).copy()

# Add diversity sampling
def sample_diverse_planets(df, max_rows):
    if len(df) <= max_rows:
        return df

    # Sample across different temperature ranges for diversity
    temp_bins = [
        (0, 4000),      # Cool stars
        (4000, 7000),   # Balanced stars
        (7000, 10000),  # Hot stars
        (10000, 30000), # Very hot stars
        (30000, 100000) # Extreme stars
    ]

    samples_per_bin = max_rows // len(temp_bins)
    remainder = max_rows % len(temp_bins)

    sampled_dfs = []
    for i, (min_temp, max_temp) in enumerate(temp_bins):
        bin_df = df[(df['st_teff'] >= min_temp) & (df['st_teff'] < max_temp)]
        if len(bin_df) > 0:
            n_samples = samples_per_bin + (1 if i < remainder else 0)
            if len(bin_df) <= n_samples:
                sampled_dfs.append(bin_df)
            else:
                # Sample with variety in discovery years and orbital periods
                sampled = bin_df.sample(n=min(n_samples, len(bin_df)), random_state=42)
                sampled_dfs.append(sampled)

    result = pd.concat(sampled_dfs, ignore_index=True) if sampled_dfs else df.head(max_rows)
    return result.head(max_rows)  # Ensure we don't exceed max_rows

if args.max_rows is not None and args.max_rows > 0:
    df = sample_diverse_planets(df, args.max_rows)


print(f"Dataset shape after filters (limited to {len(df)} rows): {df.shape}")
print(df.head(3))

# schema normalizer
REQUIRED_KEYS = [
    "Trait Snapshot",
    "Artist Name",
    "Song Blueprint",
    "Data Confidence",
    "Kid Summary",
]

def _pick(d, *alts, default=None):
    for k in alts:
        if k in d:
            return d[k]
    return default

def normalize_result(obj: dict) -> dict:
    """
    Ensure the 5 required sections exist.
    Keep full original under _raw_result for traceability.
    Never fabricate new facts—missing sections become empty containers.
    """
    return {
        "Trait Snapshot": _pick(obj, "Trait Snapshot", "trait_snapshot", default=[]),
        "Artist Name": _pick(obj, "Artist Name", "artist_name", default=""),
        "Song Blueprint": _pick(obj, "Song Blueprint", "song_blueprint", default=[]),
        "Data Confidence": _pick(obj, "Data Confidence", "data_confidence", default=[]),
        "Kid Summary": _pick(obj, "Kid Summary", "kid_summary", default=""),
        "_raw_result": obj
    }

# Helpers
def ask_openai(model: str, system_prompt: str, user_payload: str,
               temperature: float = 0.3,
               max_retries: int = 3,
               backoff_s: float = 1.5,
               excluded_artists: list = None) -> str:
    """Chat Completions with JSON response_format + simple retries."""

    # Add excluded artists to the prompt if any
    modified_prompt = system_prompt
    if excluded_artists:
        artists_list = ", ".join(excluded_artists)
        modified_prompt += f"\n\nIMPORTANT: Do NOT use these overused artists: {artists_list}. Choose different artists that fit the genre instead."

    attempt = 0
    while True:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": modified_prompt},
                    {"role": "user", "content": user_payload.strip() + "\n\nRespond ONLY with JSON."},
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout=120,
            )
            return resp.choices[0].message.content
        except (RateLimitError, APITimeoutError, APIError) as e:
            attempt += 1
            if attempt > max_retries:
                raise
            sleep_for = backoff_s * attempt
            print(f"[Retry {attempt}/{max_retries}] {type(e).__name__}: {e}. Sleeping {sleep_for:.1f}s…")
            time.sleep(sleep_for)

def row_to_prompt(r) -> str:
    payload = {
        "hostname": r.hostname,
        "sy_snum": int(r.sy_snum),
        "sy_pnum": int(r.sy_pnum),
        "disc_year": int(r.disc_year),
        "st_teff": float(r.st_teff),
        "ra": float(r.ra),
        "dec": float(r.dec),
        "sy_gaiamag": float(r.sy_gaiamag),

        "pl_name": r.pl_name,
        "pl_orbper": float(r.pl_orbper),
        "pl_orbeccen": max(0.0, float(r.pl_orbeccen)) if pd.notna(r.pl_orbeccen) else None,
        "pl_bmasse": float(r.pl_bmasse) if ("pl_bmasse" in df.columns and pd.notna(getattr(r, "pl_bmasse", None))) else None,

        "notes": "Single planet entry; one LLM call per dataframe row."
    }
    return json.dumps(payload, ensure_ascii=False)

results_path = Path(args.out_jsonl)
summary_rows = []

# Artist diversity tracking
artist_usage_count = {}
MAX_ARTIST_USAGE = 7

with results_path.open("w", encoding="utf-8") as out:
    for row in df.itertuples(index=False):
        payload = row_to_prompt(row)
        try:
            # Get list of overused artists to exclude
            excluded_artists = [artist for artist, count in artist_usage_count.items() if count >= MAX_ARTIST_USAGE]

            raw = ask_openai(MODEL_NAME, SYSTEM_PROMPT, payload, excluded_artists=excluded_artists)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"_raw_text": raw, "_row_payload": json.loads(payload)}

            normalized = normalize_result(parsed)
            has_json = isinstance(parsed, dict) and all(k in normalized for k in REQUIRED_KEYS)

            # Track artist usage for diversity
            artist_name = normalized.get("Artist Name") or ""
            if artist_name:
                artist_usage_count[artist_name] = artist_usage_count.get(artist_name, 0) + 1

                # Log artist usage for monitoring
                if artist_usage_count[artist_name] == MAX_ARTIST_USAGE:
                    print(f"[INFO] Artist '{artist_name}' reached limit of {MAX_ARTIST_USAGE} uses, adding to exclusion list")
                elif artist_usage_count[artist_name] > MAX_ARTIST_USAGE:
                    print(f"[WARN] Artist '{artist_name}' exceeded limit ({artist_usage_count[artist_name]} uses) - this shouldn't happen!")

            # Write one JSON object per line
            out.write(json.dumps({
                "hostname": row.hostname,
                "pl_name": row.pl_name,
                "result": normalized
            }, ensure_ascii=False) + "\n")

            # Build a compact summary row
            artist_name = normalized.get("Artist Name") or ""
            song_blueprint = normalized.get("Song Blueprint") or []
            summary_rows.append({
                "hostname": row.hostname,
                "pl_name": row.pl_name,
                "artist_name": artist_name,
                "song_blueprint_items": len(song_blueprint) if isinstance(song_blueprint, list) else 0,
                "has_json": bool(has_json),
            })
        except Exception as e:
            summary_rows.append({
                "hostname": row.hostname,
                "pl_name": row.pl_name,
                "artist_name": "",
                "song_blueprint_items": 0,
                "has_json": False
            })
            print(f"[WARN] {row.hostname} / {row.pl_name} failed: {e}")

        time.sleep(args.sleep)

pd.DataFrame(summary_rows).to_csv(args.summary_csv, index=False)
print(f"Wrote {results_path} and {args.summary_csv} (rows processed: {len(df)})")
