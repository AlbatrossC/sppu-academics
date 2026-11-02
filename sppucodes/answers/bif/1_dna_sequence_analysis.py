dna = "ATGCGTACGTTAGCGATCGATGCTAGCTAGCGATCGATGCGTAA"

print("DNA:", dna)
print("Length:", len(dna))

for b in "ATGC":
    print(b, dna.count(b))

print("GC%:", round((dna.count("G") + dna.count("C")) / len(dna) * 100, 2))

print("ATG Motif:", dna.count("ATG"))

c = dna.translate(str.maketrans("ATGC", "TACG"))

print("Complement:", c)
print("Reverse Complement:", c[::-1])

for i in range(len(dna) - 2):
    if dna[i:i+3] == "ATG":
        for j in range(i+3, len(dna)-2, 3):
            if dna[j:j+3] in ["TAA", "TAG", "TGA"]:
                print("ORF:", dna[i:j+3])
                break
