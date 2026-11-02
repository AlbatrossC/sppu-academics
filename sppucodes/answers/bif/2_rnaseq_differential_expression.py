import pandas as pd
import numpy as np

data = {
    "Gene": ["G1", "G2", "G3", "G4"],
    "Control": [10, 20, 30, 40],
    "Treated": [30, 10, 20, 80]
}

df = pd.DataFrame(data)

df["Change"] = df["Treated"] - df["Control"]
df["Fold Change"] = df["Treated"] / df["Control"]
df["Log2 Fold Change"] = np.log2(df["Fold Change"])

print("Gene Expression Data:")
print(df)

print("\nUpregulated Genes:")
print(df[df["Change"] > 0]["Gene"])

print("\nDownregulated Genes:")
print(df[df["Change"] < 0]["Gene"])

