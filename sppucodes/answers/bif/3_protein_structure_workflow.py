"""Predict and save a protein structure with the ESMFold API."""

import requests


sequence = input("Enter protein sequence: ").strip().upper()
response = requests.post(
    "https://api.esmatlas.com/foldSequence/v1/pdb/",
    data=sequence,
    timeout=120,
)
response.raise_for_status()

with open("predicted_structure.pdb", "w", encoding="utf-8") as file:
    file.write(response.text)

print("Predicted structure saved to predicted_structure.pdb")
print("View and validate the structure in PyMOL or another molecular viewer.")
