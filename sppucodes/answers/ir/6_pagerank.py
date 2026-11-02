# Q6: Implement the PageRank algorithm using Python or Beautiful Soup. Demonstrate the ranking on a directed web graph. View

graph = {
    "A": ["B", "C"],
    "B": ["C"],
    "C": ["A"],
    "D": ["C"]
}

damping = 0.85
pages = list(graph)

rank = {}

for page in pages:
    rank[page] = 1 / len(pages)


for i in range(100):
    new_rank = {}

    for page in pages:
        incoming = 0

        for source in pages:
            if page in graph[source]:
                incoming += rank[source] / len(graph[source])

        new_rank[page] = (1 - damping) / len(pages) + damping * incoming

    rank = new_rank


ranked = sorted(rank, key=rank.get, reverse=True)

for page in ranked:
    print("Page", page, ":", round(rank[page], 4))
    