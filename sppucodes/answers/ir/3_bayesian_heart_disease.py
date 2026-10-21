"""Small Naive Bayes network example for heart-disease data."""

data = [
    {"chest_pain": "yes", "high_cholesterol": "yes", "disease": "yes"},
    {"chest_pain": "yes", "high_cholesterol": "no", "disease": "yes"},
    {"chest_pain": "no", "high_cholesterol": "yes", "disease": "yes"},
    {"chest_pain": "no", "high_cholesterol": "no", "disease": "no"},
    {"chest_pain": "no", "high_cholesterol": "no", "disease": "no"},
    {"chest_pain": "yes", "high_cholesterol": "no", "disease": "yes"},
]

evidence = {"chest_pain": input("Chest pain (yes/no): ").lower(),
            "high_cholesterol": input("High cholesterol (yes/no): ").lower()}
classes = ["yes", "no"]
scores = {}

for diagnosis in classes:
    class_rows = [row for row in data if row["disease"] == diagnosis]
    probability = len(class_rows) / len(data)
    for feature, value in evidence.items():
        matches = sum(row[feature] == value for row in class_rows)
        probability *= (matches + 1) / (len(class_rows) + 2)
    scores[diagnosis] = probability

prediction = max(scores, key=scores.get)
print("Estimated class:", "Heart disease" if prediction == "yes" else "No heart disease")
print("Class probabilities:", scores)
print("This small example is for coursework only, not medical diagnosis.")
