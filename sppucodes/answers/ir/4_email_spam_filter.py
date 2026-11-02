import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report

df = pd.read_csv("spam_ham_dataset.csv")

X_train, X_test, y_train, y_test = train_test_split(
    df["text"],
    df["label"],
    test_size=0.2,
    random_state=42,
    stratify=df["label"]
)

vectorizer = TfidfVectorizer()

X_train = vectorizer.fit_transform(X_train)
X_test = vectorizer.transform(X_test)

model = MultinomialNB()

model.fit(X_train, y_train)

prediction = model.predict(X_test)


print("Accuracy:", accuracy_score(y_test, prediction))

print("Confusion Matrix:")
print(confusion_matrix(y_test, prediction))

print("Classification Report:")
print(classification_report(y_test, prediction))

email = input("Enter an email message: ")

result = model.predict(vectorizer.transform([email]))[0]

print("Result:", result.upper())
