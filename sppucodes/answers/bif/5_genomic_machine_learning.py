from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

X = [[1, 2], [2, 3], [3, 1], [6, 7], [7, 8], [8, 6]]
y = [0, 0, 0, 1, 1, 1]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=1
)

model = RandomForestClassifier(random_state=1)
model.fit(X_train, y_train)

pred = model.predict(X_test)

print("Predictions:", pred)
print("Accuracy:", accuracy_score(y_test, pred))

print("Feature Importance:", model.feature_importances_)
