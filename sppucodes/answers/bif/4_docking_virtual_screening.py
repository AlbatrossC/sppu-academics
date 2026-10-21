"""Rank sample ligands by docking score."""

import pandas as pd


data = {
    "Ligand": ["Ligand_A", "Ligand_B", "Ligand_C", "Ligand_D", "Ligand_E", "Ligand_F"],
    "Hydrogen_Bonds": [3, 2, 4, 1, 3, 2],
    "Hydrophobic_Contacts": [5, 4, 6, 3, 7, 5],
    "Molecular_Weight": [310, 285, 340, 250, 360, 300],
    "Binding_Score": [-7.8, -6.4, -8.5, -5.2, -9.1, -7.0],
}

ligands = pd.DataFrame(data)
ranked = ligands.sort_values("Binding_Score")
print(ranked.to_string(index=False))
best = ranked.iloc[0]
print("\nBest candidate:", best["Ligand"])
print("Docking score:", best["Binding_Score"], "kcal/mol")
print("Docking scores are predictions and require experimental validation.")
