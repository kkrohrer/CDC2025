import streamlit as st
import pandas as pd
import json
from pathlib import Path
import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Cosmic DJ - Planet Explorer",
    page_icon="🎵",
    layout="wide"
)

@st.cache_data
def load_data():
    """Load JSONL results and create summary data"""
    try:
        # Load detailed results from JSONL
        results = []
        if Path("cosmic_dj_results_per_line.jsonl").exists():
            with open("cosmic_dj_results_per_line.jsonl", "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        results.append(json.loads(line))

        # Create summary data from JSONL
        summary_data = []
        for result in results:
            artist_name = result.get("result", {}).get("Artist Name", "")
            song_blueprint = result.get("result", {}).get("Song Blueprint", [])
            has_json = bool(artist_name and song_blueprint)

            summary_data.append({
                "hostname": result.get("hostname", ""),
                "pl_name": result.get("pl_name", ""),
                "artist_name": artist_name,
                "song_blueprint_items": len(song_blueprint) if isinstance(song_blueprint, list) else 0,
                "has_json": has_json
            })

        summary_df = pd.DataFrame(summary_data)
        return summary_df, results
    except FileNotFoundError:
        st.error("Data files not found. Please run cleanup.py first to generate cosmic_dj_results_per_line.jsonl")
        return None, None

@st.cache_data
def get_spotify_token():
    """Get Spotify API access token"""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    auth_url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {"grant_type": "client_credentials"}

    try:
        response = requests.post(auth_url, headers=headers, data=data)
        if response.status_code == 200:
            return response.json()["access_token"]
    except:
        pass

    return None

@st.cache_data
def search_spotify_artist(artist_name, token):
    """Search for artist on Spotify and return image URL"""
    if not token or not artist_name:
        return None

    search_url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q": artist_name,
        "type": "artist",
        "limit": 1
    }

    try:
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if data["artists"]["items"]:
                artist = data["artists"]["items"][0]
                if artist["images"]:
                    return artist["images"][0]["url"]
    except:
        pass

    return None

@st.cache_data
def search_spotify_track(artist_name, track_name, token):
    """Search for track on Spotify and return album image URL"""
    if not token or not artist_name or not track_name:
        return None

    search_url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q": f"artist:{artist_name} track:{track_name}",
        "type": "track",
        "limit": 1
    }

    try:
        response = requests.get(search_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if data["tracks"]["items"]:
                track = data["tracks"]["items"][0]
                if track["album"]["images"]:
                    return track["album"]["images"][0]["url"]
    except:
        pass

    return None

def display_planet_details(planet_data, token):
    """Display detailed planet information"""
    result = planet_data["result"]

    st.header(f"🪐 {planet_data['pl_name']}")
    st.subheader(f"System: {planet_data['hostname']}")

    # Get artist and song info
    artist_name = result.get("Artist Name", "")
    song_blueprint = result.get("Song Blueprint", [])
    trait_snapshot = result.get("Trait Snapshot", [])
    data_confidence = result.get("Data Confidence", [])
    kid_summary = result.get("Kid Summary", "")

    if artist_name:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("🎤 Artist")
            st.write(f"**{artist_name}**")

            # Get artist image from Spotify
            artist_image = search_spotify_artist(artist_name, token)
            if artist_image:
                st.image(artist_image, width=200)
            else:
                st.info("Artist image not available")

        with col2:
            st.subheader("🎵 Song Blueprint")
            if song_blueprint:
                for i, song in enumerate(song_blueprint, 1):
                    st.write(f"**{i}.** {song}")

                    # Try to get album art for first song
                    if i == 1 and isinstance(song, str):
                        album_image = search_spotify_track(artist_name, song, token)
                        if album_image:
                            st.image(album_image, width=150)
            else:
                st.write("No song blueprint available")

    # Justification section
    st.subheader("🔬 Scientific Justification")
    if trait_snapshot:
        for trait in trait_snapshot:
            st.write(f"• {trait}")
    else:
        st.write("No trait snapshot available")

    # Kid-friendly explanation
    if kid_summary:
        st.subheader("🧒 For Kids")
        st.info(kid_summary)

def main():
    st.title("🎵 Cosmic DJ - Planet Explorer")
    st.markdown("*Converting exoplanets into musical experiences*")

    # Load data
    summary_df, results = load_data()
    if summary_df is None or not results:
        return

    # Get Spotify token
    token = get_spotify_token()
    if not token:
        st.warning("Spotify API credentials not found. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to your .env file for artist/album images.")

    # Planet selector
    st.sidebar.header("Select a Planet")

    # Filter options
    hostnames = ["All"] + sorted(summary_df["hostname"].unique().tolist())
    selected_hostname = st.sidebar.selectbox("Filter by System", hostnames)

    # Filter results
    filtered_results = results
    if selected_hostname != "All":
        filtered_results = [r for r in results if r["hostname"] == selected_hostname]

    if not filtered_results:
        st.error("No planets found with the selected filters.")
        return

    # Create planet options for selectbox
    planet_options = []
    for result in filtered_results:
        label = f"{result['pl_name']} ({result['hostname']})"
        planet_options.append((label, result))

    selected_planet_label = st.sidebar.selectbox(
        "Choose Planet",
        options=[option[0] for option in planet_options]
    )

    # Find selected planet data
    selected_planet = None
    for label, data in planet_options:
        if label == selected_planet_label:
            selected_planet = data
            break

    if selected_planet:
        display_planet_details(selected_planet, token)

    # Show summary stats
    st.sidebar.markdown("---")
    st.sidebar.subheader("📈 Summary Stats")
    st.sidebar.metric("Total Planets", len(summary_df))
    success_rate = (summary_df["has_json"].sum() / len(summary_df)) * 100
    st.sidebar.metric("Success Rate", f"{success_rate:.1f}%")

    unique_artists = summary_df[summary_df["artist_name"] != ""]["artist_name"].nunique()
    st.sidebar.metric("Unique Artists", unique_artists)

if __name__ == "__main__":
    main()