"""Compare control and treatment gene counts using fold change."""

import csv
import math
from pathlib import Path


with Path(__file__).with_name("rna_counts.csv").open(newline="", encoding="utf-8") as file:
    genes = list(csv.DictReader(file))

print(f"{'Gene':<10}{'Control':<12}{'Treatment':<12}{'Fold change':<14}{'Log2FC':<10}Status")
for gene in genes:
    control = (float(gene["Control1"]) + float(gene["Control2"])) / 2
    treatment = (float(gene["Treatment1"]) + float(gene["Treatment2"])) / 2
    fold_change = treatment / control if control else 0
    log2fc = math.log2(fold_change) if fold_change else 0
    if log2fc >= 1:
        status = "Upregulated"
    elif log2fc <= -1:
        status = "Downregulated"
    else:
        status = "Not significant"
    print(f"{gene['Gene']:<10}{control:<12.2f}{treatment:<12.2f}{fold_change:<14.2f}{log2fc:<10.2f}{status}")

print("A full study should use replicate-aware tools such as DESeq2 or edgeR and adjust for multiple testing.")
