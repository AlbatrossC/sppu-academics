"""Classify e-mail as spam or ham using Naive Bayes."""

import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB


data = pd.read_csv(Path(__file__).with_name("spam_ham_dataset.csv"))
X_train, X_test, y_train, y_test = train_test_split(
    data["text"], data["label"], test_size=0.2, random_state=42
)

vectorizer = TfidfVectorizer()
X_train = vectorizer.fit_transform(X_train)
X_test = vectorizer.transform(X_test)
model = MultinomialNB()
model.fit(X_train, y_train)
prediction = model.predict(X_test)

print("Accuracy:", accuracy_score(y_test, prediction))
print("Confusion matrix:\n", confusion_matrix(y_test, prediction))
print(classification_report(y_test, prediction))
email = input("Enter an e-mail message: ")
result = model.predict(vectorizer.transform([email]))[0]
print("Result:", result.upper())
