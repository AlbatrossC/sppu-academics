import pandas as pd

data = {
    "Ligand": ["A", "B", "C", "D", "E"],
    "Binding Score": [-8.2, -7.5, -9.0, -6.8, -8.5],
    "Hydrogen Bonds": [5, 4, 6, 2, 4],
    "Hydrophobic Contacts": [7, 9, 6, 4, 8]
}

df = pd.DataFrame(data)

df["Binding Rank"] = df["Binding Score"].rank(ascending=True)
df["H-Bond Rank"] = df["Hydrogen Bonds"].rank(ascending=False)
df["Hydrophobic Rank"] = df["Hydrophobic Contacts"].rank(ascending=False)

df["Average Rank"] = df[
    ["Binding Rank", "H-Bond Rank", "Hydrophobic Rank"]
].mean(axis=1)

df = df.sort_values("Average Rank")
df["Overall Rank"] = range(1, len(df) + 1)

print("Ligand Ranking:")
print(df.to_string(index=False))

print("\nBest Ligand:", df.iloc[0]["Ligand"])
