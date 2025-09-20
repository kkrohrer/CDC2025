import pandas as pd

# Import SpaceData.csv, skip comment lines starting with #
df = pd.read_csv('SpaceData.csv', comment='#')

print(f"Dataset shape: {df.shape}")
# print(f"Columns: {df.columns.tolist()}")


df = df[df["default_flag"] != 0]
print(len(df))
print(f"Temp Count: {df['st_teff'].head()}")
df = df[["pl_name", "hostname", "sy_snum", "sy_pnum", "disc_year", "pl_orbper", "st_teff", "pl_orbeccen", "ra", "dec", "sy_gaiamag"]]

print(df.head())