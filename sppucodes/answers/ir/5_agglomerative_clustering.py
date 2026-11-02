import pandas as pd
import matplotlib.pyplot as plt

from scipy.cluster.hierarchy import dendrogram, linkage
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import StandardScaler

df = pd.read_csv("Mall_Customers.csv")


features = df[["Age", "Annual Income (k$)", "Spending Score (1-100)"]]
scaled = StandardScaler().fit_transform(features)

tree = linkage(scaled, method="ward")

plt.figure(figsize=(10, 5))
dendrogram(tree)
plt.title("Customer Dendrogram")
plt.xlabel("Customers")
plt.ylabel("Distance")
plt.show()

model = AgglomerativeClustering(n_clusters=5, linkage="ward")

df["Cluster"] = model.fit_predict(scaled)

print("Cluster Assignments:")
print(df[["CustomerID", "Cluster"]].to_string(index=False))

print("\nCluster Counts:")
print(df["Cluster"].value_counts().sort_index())
