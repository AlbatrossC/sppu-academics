"""Calculate PageRank scores for a small web graph."""

graph = {
    "A": ["B", "C"],
    "B": ["C"],
    "C": ["A"],
    "D": ["C"],
}

damping = 0.85
pages = list(graph)
rank = {page: 1 / len(pages) for page in pages}

for _ in range(100):
    new_rank = {}
    for page in pages:
        incoming = sum(rank[source] / len(graph[source]) for source in pages
                       if page in graph[source] and graph[source])
        new_rank[page] = (1 - damping) / len(pages) + damping * incoming
    rank = new_rank

for page, score in sorted(rank.items(), key=lambda item: item[1], reverse=True):
    print(f"Page {page}: {score:.4f}")
