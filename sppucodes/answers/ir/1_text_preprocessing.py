"""Remove stop words and stem words in a text document."""

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize


nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

document = "Machine learning cannot be mastered in two months; it needs years of practice and study."
tokens = word_tokenize(document.lower())
filtered = [word for word in tokens if word.isalpha() and word not in set(stopwords.words("english"))]
stemmer = PorterStemmer()
stemmed = [stemmer.stem(word) for word in filtered]

print("Tokens:", tokens)
print("After stop-word removal:", filtered)
print("After stemming:", stemmed)
