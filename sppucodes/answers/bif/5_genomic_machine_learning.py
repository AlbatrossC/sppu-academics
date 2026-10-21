"""Classify sample genomic data with a random forest."""

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split


data = pd.DataFrame({
    "TP53": [8.2, 7.9, 8.5, 8.0, 7.6, 3.2, 3.5, 2.9, 3.7, 3.1, 3.8, 3.3],
    "BRCA1": [7.8, 8.1, 7.5, 8.3, 7.9, 4.1, 4.4, 3.8, 4.5, 4.0, 4.3, 4.2],
    "EGFR": [3.1, 3.5, 3.2, 3.8, 4.0, 9.1, 8.7, 9.4, 8.9, 9.2, 8.5, 9.0],
    "MYC": [4.2, 4.5, 4.0, 4.7, 4.3, 8.5, 8.9, 9.1, 8.2, 8.7, 8.4, 8.8],
    "PTEN": [8.5, 8.2, 8.8, 8.0, 8.4, 2.8, 3.1, 2.5, 3.4, 2.7, 3.0, 2.9],
    "Class": ["Normal"] * 5 + ["Cancer"] * 7,
})

X = data.drop(columns="Class")
y = data["Class"]
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42, stratify=y
)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
prediction = model.predict(X_test)

print("Accuracy:", accuracy_score(y_test, prediction))
print("Confusion matrix:\n", confusion_matrix(y_test, prediction))
print(classification_report(y_test, prediction))
print("Feature importance:\n", pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False))
