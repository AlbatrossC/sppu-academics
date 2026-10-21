"""Read product names and links from the Books to Scrape demo website."""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


url = "https://books.toscrape.com/"
response = requests.get(url, timeout=15)
response.raise_for_status()
soup = BeautifulSoup(response.text, "html.parser")

for product in soup.find_all("article", class_="product_pod"):
    name = product.h3.a["title"]
    price = product.find("p", class_="price_color").get_text(strip=True)
    link = urljoin(url, product.h3.a["href"])
    print("Product:", name)
    print("Price:", price)
    print("Link:", link)
    print("-" * 40)
