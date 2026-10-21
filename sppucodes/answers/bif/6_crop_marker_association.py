"""Compare crop yield with simple genetic marker values."""

import pandas as pd


data = pd.DataFrame({
    "Marker_1": [0, 1, 2, 0, 1, 2, 0, 1],
    "Marker_2": [1, 1, 0, 2, 2, 1, 0, 2],
    "Yield": [2.1, 2.8, 3.4, 2.0, 2.9, 3.7, 1.9, 3.0],
})

print(data)
print("\nMarker correlation with yield:")
print(data.corr(numeric_only=True)["Yield"].drop("Yield").sort_values(ascending=False))
print("\nTest promising markers with a larger dataset and account for population structure.")
