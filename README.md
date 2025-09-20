# CDC2025
Carolina Data Challenge 2025
Talking Points
* Personifying planet data (temp/Orbtial Period) into song traits (temp = popularity (top songs of that artist), Orbital Period = tempo/bpm)
* Discovery year (range of songs, E.x. made in 90s range of songs 1990-1999)
* System = Artist, Planet = Song of Artist (idea)
* Eccentricity for consistency of music, smooth tempo or dramatic changes.
* Musical Chaos Index (Chaos = Eccentricity * 10) + log(Mass of Earth Masses)
* Constellation -> Artist Style (RA, DEC)
* Gaia Magnitude -> Artist Fame Level (low magnitude=most famous, high magnitude=least famous)

Pipeline:
Host Name --> Artist
Planet --> Songs by Artist
Discovery Year --> Songs released within a +-5 year range



Data cleanup
* Drop all data points without a default flag of 1 Column (default_flag)
* Keep Discovery year, planet name/stars, Temperature, Mass