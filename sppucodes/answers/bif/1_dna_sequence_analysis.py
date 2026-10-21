"""Basic DNA sequence analysis."""

dna = input("Enter DNA sequence: ").upper()
if not dna or not all(base in "ATGC" for base in dna):
    print("Invalid DNA sequence")
    raise SystemExit

print("Length:", len(dna))
print("GC Content: {:.2f}%".format((dna.count("G") + dna.count("C")) / len(dna) * 100))

motif = input("Enter motif to search: ").upper()
positions = [i + 1 for i in range(len(dna) - len(motif) + 1) if dna[i:i + len(motif)] == motif]
print("Motif positions:", positions)

complement = {"A": "T", "T": "A", "G": "C", "C": "G"}
print("Reverse complement:", "".join(complement[base] for base in reversed(dna)))

start = dna.find("ATG")
orf = None
if start != -1:
    for i in range(start + 3, len(dna) - 2, 3):
        if dna[i:i + 3] in {"TAA", "TAG", "TGA"}:
            orf = dna[start:i + 3]
            break
print("Coding region:", orf if orf else "No complete ORF found")
