# Q2: Implement retrieval of documents using an inverted file (inverted index). Build postings from a collection of documents and rank documents matching a user query.

documents = {
    "D1": "Machine Learning is useful",
    "D2": "Machine Learning uses data",
    "D3": "Data Science is useful"
}

# Build inverted index
inverted_index = {}

for doc_id, text in documents.items():
    words = text.lower().split()

    for word in words:
        if word not in inverted_index:
            inverted_index[word] = []

        inverted_index[word].append(doc_id)

print("Inverted index:")
print(inverted_index)

# Search query
query = input("Enter search query: ").lower().split()

scores = {}
for word in query:
    if word in inverted_index:
        for doc_id in inverted_index[word]:
            if doc_id not in scores:
                scores[doc_id] = 0

            scores[doc_id] += 1

# Rank documents
ranked = sorted(scores, key=scores.get, reverse=True)
print("Matching documents:")

for doc_id in ranked:
    print(doc_id, "Score:", scores[doc_id])

if not scores:
    print("No documents found")
    