# Q1: Write a program to preprocess a text document by tokenizing it, removing stop words, and stemming the remaining words.

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize

# Download required resources
nltk.download("punkt")
nltk.download("punkt_tab")
nltk.download("stopwords")

document = "I am learning Python and machine learning."

# Tokenization
tokens = word_tokenize(document.lower())

# Remove stop words
stop_words = set(stopwords.words("english"))
filtered = []
for word in tokens:
    if word not in stop_words:
        filtered.append(word)

# Stemming
stemmer = PorterStemmer()
stemmed = []
for word in filtered:
    stemmed.append(stemmer.stem(word))

print("Tokens:", tokens)
print("After stop-word removal:", filtered)
print("After stemming:", stemmed)
