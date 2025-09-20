import pandas as pd

# Set pandas to show all columns
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# Import SpaceData.csv, skip comment lines starting with #
df = pd.read_csv('SpaceData.csv', comment='#')

print(f"Dataset shape: {df.shape}")
# print(f"Columns: {df.columns.tolist()}")


df = df[df["default_flag"] != 0]

# Planet Name, Host Name, Number of suns, Number of Planets, Year Discovered, Planet Orbital Period, Sun Temperature, Eccentricity, RA, Dec, Gaia Magnitude
df = df[["pl_name", "hostname", "sy_snum", "sy_pnum", "disc_year", "pl_orbper", "st_teff", "pl_orbeccen", "ra", "dec", "sy_gaiamag"]]



# Fill null eccentricity values with 0.01
df['pl_orbeccen'] = df['pl_orbeccen'].fillna(0.1)
print(df.head())
