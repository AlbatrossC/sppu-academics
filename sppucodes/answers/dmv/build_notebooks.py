"""Rebuild the self-contained DMV demonstration datasets and executed notebooks."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook, new_output


HERE = Path(__file__).resolve().parent


def make_datasets() -> None:
    rng = np.random.default_rng(42)

    # Assignment 7: the same schema spread across three real file formats.
    products = [
        ("Laptop", "Electronics", 52000),
        ("Headphones", "Electronics", 1800),
        ("Desk Chair", "Furniture", 6500),
        ("Notebook", "Stationery", 180),
        ("Water Bottle", "Home", 450),
    ]
    sales = []
    for i in range(72):
        product, category, price = products[i % len(products)]
        sales.append({
            "OrderID": 1001 + i,
            "Date": (pd.Timestamp("2025-01-01") + pd.Timedelta(days=i * 2)).strftime("%Y-%m-%d"),
            "Region": ["North", "South", "East", "West"][i % 4],
            "CustomerID": f"C{rng.integers(1, 31):03d}",
            "Product": product,
            "Category": category,
            "Quantity": int(rng.integers(1, 6)),
            "UnitPrice": round(price * rng.uniform(0.9, 1.1), 2),
        })
    sales[12]["Quantity"] = None
    sales[28]["Region"] = " west "
    sales.append(sales[5].copy())
    pd.DataFrame(sales[:25]).to_csv(HERE / "sales_data.csv", index=False)
    pd.DataFrame(sales[25:49]).to_excel(HERE / "sales_data.xlsx", index=False)
    (HERE / "sales_data.json").write_text(json.dumps(sales[49:], indent=2) + "\n", encoding="utf-8")

    # Assignment 8: a sample response with the structure of the 5-day forecast API.
    forecast = []
    for i in range(40):
        when = pd.Timestamp("2025-04-01", tz="UTC") + pd.Timedelta(hours=3 * i)
        daily_cycle = np.sin(2 * np.pi * (i % 8) / 8)
        temperature = round(25 + 5 * daily_cycle + rng.normal(0, 1), 1)
        humidity = int(np.clip(65 - 12 * daily_cycle + rng.normal(0, 5), 30, 95))
        forecast.append({
            "dt": int(when.timestamp()),
            "main": {"temp": temperature, "humidity": humidity},
            "wind": {"speed": round(float(rng.uniform(0.5, 6.0)), 1)},
            "rain": {"3h": round(float(rng.uniform(0.2, 4)), 1)} if i % 7 == 0 else {},
        })
    (HERE / "OpenWeatherMap_sample.json").write_text(
        json.dumps({"city": {"name": "Pune", "coord": {"lat": 18.5204, "lon": 73.8567}}, "list": forecast}, indent=2) + "\n",
        encoding="utf-8",
    )

    # Assignment 9: customer records include deliberate cleaning examples.
    churn = []
    for i in range(240):
        tenure = int(rng.integers(1, 73))
        contract = rng.choice(["Month-to-month", "One year", "Two year"], p=[0.48, 0.32, 0.20])
        monthly = round(float(rng.uniform(25, 115)), 2)
        probability = 0.12 + (0.35 if contract == "Month-to-month" else 0) + (0.10 if tenure < 12 else 0)
        churn.append({
            "CustomerID": f"TC{i + 1:04d}",
            "Gender": rng.choice(["Female", "Male"]),
            "SeniorCitizen": int(rng.random() < 0.18),
            "Tenure": tenure,
            "Contract": contract,
            "MonthlyCharges": monthly,
            "TotalCharges": round(monthly * tenure * rng.uniform(0.95, 1.05), 2),
            "Churn": "Yes" if rng.random() < probability else "No",
        })
    churn[6]["Gender"] = " female "
    churn[13]["TotalCharges"] = None
    churn[20]["MonthlyCharges"] = None
    churn.append(churn[4].copy())
    pd.DataFrame(churn).to_csv(HERE / "Telecom_Customer_Churn.csv", index=False)

    # Assignment 10: prices vary by size, property type and neighborhood.
    neighborhoods = pd.DataFrame({
        "Neighborhood": ["Central", "North", "South", "West"],
        "NearbyAmenities": [8, 5, 4, 7],
        "MedianIncome": [125000, 85000, 72000, 110000],
    })
    neighborhoods.to_csv(HERE / "RealEstate_Neighborhoods.csv", index=False)
    homes = []
    premiums = {"Central": 170000, "North": 45000, "South": 0, "West": 120000}
    for i in range(240):
        neighborhood = rng.choice(list(premiums))
        area = int(rng.integers(650, 2900))
        bedrooms = int(np.clip(round(area / 550), 1, 5))
        property_type = rng.choice(["Apartment", "House", "Townhouse"])
        price = max(80000, 90000 + area * 145 + premiums[neighborhood] + rng.normal(0, 35000))
        homes.append({
            "Property ID": f"RE{i + 1:04d}",
            "Sale Date": (pd.Timestamp("2023-01-01") + pd.Timedelta(days=int(rng.integers(0, 900)))).strftime("%Y-%m-%d"),
            "Neighborhood": neighborhood,
            "Property Type": property_type,
            "Area SqFt": area,
            "Bedrooms": bedrooms,
            "Year Built": int(rng.integers(1980, 2025)),
            "Sale Price": round(float(price), 2),
        })
    homes[5]["Area SqFt"] = None
    homes[15]["Sale Price"] *= 5
    homes[25]["Neighborhood"] = " west "
    pd.DataFrame(homes).to_csv(HERE / "RealEstate_Prices.csv", index=False)

    # Assignment 11: daily AQI with correlated pollutant measurements.
    air = []
    for i in range(150):
        date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        pm25 = max(5, 35 + 12 * np.sin(i / 18) + rng.normal(0, 7))
        pm10 = max(12, pm25 * 1.7 + rng.normal(0, 10))
        co = max(0.1, 0.6 + pm25 / 90 + rng.normal(0, 0.15))
        aqi = int(max(10, 20 + pm25 * 1.7 + pm10 * 0.3 + rng.normal(0, 7)))
        air.append({"Date": date.strftime("%Y-%m-%d"), "PM2.5": round(pm25, 1), "PM10": round(pm10, 1), "CO": round(co, 2), "AQI": aqi})
    pd.DataFrame(air).to_csv(HERE / "City_Air_Quality.csv", index=False)

    # Assignment 12: transaction-level retail sales.
    retail = []
    prices = {"Electronics": 14000, "Furniture": 6800, "Clothing": 1900, "Groceries": 480}
    for i in range(320):
        category = rng.choice(list(prices))
        quantity = int(rng.integers(1, 6))
        unit_price = round(float(prices[category] * rng.uniform(0.75, 1.25)), 2)
        retail.append({
            "TransactionID": f"RS{i + 1:04d}",
            "TransactionDate": (pd.Timestamp("2025-01-01") + pd.Timedelta(days=int(rng.integers(0, 180)))).strftime("%Y-%m-%d"),
            "Region": rng.choice(["North", "South", "East", "West"]),
            "ProductCategory": category,
            "QuantitySold": quantity,
            "UnitPrice": unit_price,
            "SalesAmount": round(quantity * unit_price, 2),
        })
    pd.DataFrame(retail).to_csv(HERE / "Retail_Sales_Data.csv", index=False)

    # Assignment 13: a coherent business-day price series and market benchmark.
    stock = []
    for i, date in enumerate(pd.bdate_range("2024-01-01", periods=260)):
        market = 18000 + i * 4 + 140 * np.sin(i / 17) + rng.normal(0, 55)
        close = 105 + i * 0.16 + 4 * np.sin(i / 12) + 0.003 * (market - 18000) + rng.normal(0, 1.4)
        stock.append({"Date": date.strftime("%Y-%m-%d"), "Close": round(float(close), 2), "Volume": int(rng.integers(90000, 400000)), "MarketIndex": round(float(market), 2)})
    pd.DataFrame(stock).to_csv(HERE / "Stock_Prices.csv", index=False)


def notebook(title: str, problem_statement: str, cells: list[str], filename: str) -> None:
    book = new_notebook(
        cells=[new_markdown_cell(f"# {title}\n\n**Problem Statement:** {problem_statement}")] + [new_code_cell(cell.strip() + "\n") for cell in cells],
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "file_extension": ".py"},
        },
    )
    outputs: list = []
    original_show = plt.show

    def capture_show(*_args, **_kwargs):
        for number in plt.get_fignums():
            buffer = io.BytesIO()
            plt.figure(number).savefig(buffer, format="png", dpi=95, bbox_inches="tight")
            outputs.append(new_output("display_data", data={"image/png": base64.b64encode(buffer.getvalue()).decode("ascii")}, metadata={}))
        plt.close("all")

    plt.show = capture_show
    namespace = {"__name__": "__main__"}
    old_cwd = Path.cwd()
    os.chdir(HERE)
    try:
        for number, cell in enumerate(book.cells[1:], 1):
            outputs = []
            stdout = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout):
                    exec(compile(cell.source, f"{filename}:cell{number}", "exec"), namespace)
            except Exception as exc:
                raise RuntimeError(f"{filename}, cell {number}: {exc}") from exc
            if stdout.getvalue():
                cell.outputs.append(new_output("stream", name="stdout", text=stdout.getvalue()))
            cell.outputs.extend(outputs)
            cell.execution_count = number
        nbformat.validate(book)
        nbformat.write(book, HERE / filename)
    finally:
        os.chdir(old_cwd)
        plt.show = original_show
        plt.close("all")


def build_notebooks() -> None:
    notebook(
        "Q7: Data Loading, Storage and File Formats",
        "Analyzing Sales Data from Multiple File Formats",
        [
            r"""
# Load each file format separately.
import pandas as pd
import matplotlib.pyplot as plt

csv_sales = pd.read_csv("sales_data.csv")
excel_sales = pd.read_excel("sales_data.xlsx")
json_sales = pd.read_json("sales_data.json")
for name, frame in [("CSV", csv_sales), ("Excel", excel_sales), ("JSON", json_sales)]:
    print(name, frame.shape, frame.columns.tolist())
    print(frame.head(2).to_string(index=False), "\n")
""",
            r"""
# Inspect missing data and repeated order IDs before cleaning.
sales = pd.concat([csv_sales, excel_sales, json_sales], ignore_index=True)
print("Rows before cleaning:", len(sales))
print("Missing values:\n", sales.isna().sum().to_string())
print("Repeated order IDs:", sales.duplicated(subset="OrderID").sum())
""",
            r"""
# Standardize fields, remove duplicate orders, and fill a missing quantity.
sales["Region"] = sales["Region"].astype(str).str.strip().str.title()
sales["Date"] = pd.to_datetime(sales["Date"], errors="coerce")
sales["Quantity"] = pd.to_numeric(sales["Quantity"], errors="coerce")
sales["UnitPrice"] = pd.to_numeric(sales["UnitPrice"], errors="coerce")
sales = sales.drop_duplicates(subset="OrderID")
sales["Quantity"] = sales["Quantity"].fillna(sales["Quantity"].median())
sales = sales.dropna(subset=["Date", "UnitPrice"])
print("Clean rows:", len(sales))
print("Remaining missing values:", int(sales.isna().sum().sum()))
""",
            r"""
# Derive sales metrics and a month for aggregation.
sales["TotalSales"] = sales["Quantity"] * sales["UnitPrice"]
sales["Month"] = sales["Date"].dt.to_period("M").astype(str)
print("Total sales:", round(sales["TotalSales"].sum(), 2))
print("Average order value:", round(sales["TotalSales"].mean(), 2))
print("By category:\n", sales.groupby("Category")["TotalSales"].agg(["count", "sum", "mean"]).round(2).to_string())
""",
            r"""
# Compare regions, categories and monthly trends visually.
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
sales.groupby("Region")["TotalSales"].sum().plot.bar(ax=axes[0], title="Sales by region")
sales.groupby("Category")["TotalSales"].sum().plot.pie(ax=axes[1], title="Category share", autopct="%1.0f%%")
axes[1].set_ylabel("")
sales.groupby("Month")["TotalSales"].sum().plot(ax=axes[2], marker="o", title="Monthly sales")
axes[0].set_ylabel("Sales amount")
axes[2].tick_params(axis="x", rotation=45)
plt.tight_layout()
plt.show()
""",
        ],
        "7_sales_file_formats.ipynb",
    )

    notebook(
        "Q8: Interacting with Web APIs",
        "Analyzing Weather Data from OpenWeatherMap API",
        [
            r"""
# Request the API when a key is available; otherwise use the offline sample.
import json
import os
import requests
import pandas as pd
import matplotlib.pyplot as plt

api_key = os.getenv("OPENWEATHER_API_KEY")
if api_key:
    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"q": "Pune,IN", "appid": api_key, "units": "metric"},
            timeout=20,
        )
        response.raise_for_status()
        weather_json = response.json()
        print("Live OpenWeatherMap forecast loaded.")
    except requests.RequestException as error:
        print("Live request failed; using local sample:", error)
        weather_json = json.loads(open("OpenWeatherMap_sample.json", encoding="utf-8").read())
else:
    print("No OPENWEATHER_API_KEY set; using synthetic local sample.")
    weather_json = json.loads(open("OpenWeatherMap_sample.json", encoding="utf-8").read())
print("Location:", weather_json["city"]["name"], "records:", len(weather_json["list"]))
""",
            r"""
# Extract temperature, humidity, wind and precipitation from each response item.
rows = []
for item in weather_json["list"]:
    rows.append({
        "time": pd.to_datetime(item["dt"], unit="s", utc=True),
        "temperature_c": item.get("main", {}).get("temp"),
        "humidity_pct": item.get("main", {}).get("humidity"),
        "wind_m_s": item.get("wind", {}).get("speed"),
        "rain_mm": item.get("rain", {}).get("3h", 0),
    })
weather = pd.DataFrame(rows).sort_values("time")
numeric = ["temperature_c", "humidity_pct", "wind_m_s", "rain_mm"]
weather[numeric] = weather[numeric].apply(pd.to_numeric, errors="coerce")
weather[numeric] = weather[numeric].interpolate(limit_direction="both").fillna(0)
print(weather.head().to_string(index=False))
print("Missing measurements:", int(weather[numeric].isna().sum().sum()))
""",
            r"""
# Model daily summaries and inspect changes over the forecast period.
daily = weather.set_index("time").resample("D").agg({
    "temperature_c": ["mean", "min", "max"],
    "humidity_pct": "mean",
    "wind_m_s": "mean",
    "rain_mm": "sum",
})
daily.columns = ["temp_mean", "temp_min", "temp_max", "humidity_mean", "wind_mean", "rain_total"]
print(daily.round(2).to_string())
print("Overall temperature range:", weather["temperature_c"].min(), "to", weather["temperature_c"].max(), "°C")
""",
            r"""
# Plot weather trends and daily rainfall.
fig, axes = plt.subplots(2, 1, figsize=(10, 7))
weather.plot(x="time", y="temperature_c", ax=axes[0], legend=False, color="tomato")
axes[0].set_title("Forecast temperature")
axes[0].set_ylabel("°C")
daily["rain_total"].plot.bar(ax=axes[1], color="steelblue", title="Daily precipitation")
axes[1].set_ylabel("mm")
axes[1].tick_params(axis="x", rotation=45)
plt.tight_layout()
plt.show()
""",
            r"""
# Show the location, then visualize correlations between weather variables.
coords = weather_json["city"]["coord"]
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
axes[0].scatter(coords["lon"], coords["lat"], s=140, color="darkorange")
axes[0].annotate(weather_json["city"]["name"], (coords["lon"], coords["lat"]), xytext=(5, 5), textcoords="offset points")
axes[0].set(xlabel="Longitude", ylabel="Latitude", title="Forecast location")
axes[0].grid(alpha=0.3)
correlation = weather[numeric].corr()
image = axes[1].imshow(correlation, vmin=-1, vmax=1, cmap="coolwarm")
axes[1].set_xticks(range(len(numeric)), numeric, rotation=35, ha="right")
axes[1].set_yticks(range(len(numeric)), numeric)
axes[1].set_title("Weather correlations")
fig.colorbar(image, ax=axes[1], shrink=0.8)
plt.tight_layout()
plt.show()
""",
        ],
        "8_openweathermap_api.ipynb",
    )

    notebook(
        "Q9: Data Cleaning and Preparation",
        "Analyzing Customer Churn in a Telecommunications Company",
        [
            r"""
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

customers = pd.read_csv("Telecom_Customer_Churn.csv")
print("Original shape:", customers.shape)
print(customers.head().to_string(index=False))
print("Missing values:\n", customers.isna().sum().to_string())
""",
            r"""
# Remove duplicate customers and standardize inconsistent categorical values.
customers = customers.drop_duplicates(subset="CustomerID").copy()
customers["Gender"] = customers["Gender"].astype("string").str.strip().str.title()
customers["Contract"] = customers["Contract"].astype("string").str.strip().str.title()
customers["Churn"] = customers["Churn"].astype("string").str.strip().str.title()
for column in ["Tenure", "MonthlyCharges", "TotalCharges"]:
    customers[column] = pd.to_numeric(customers[column], errors="coerce")
    customers[column] = customers[column].fillna(customers[column].median())
for column in ["Gender", "Contract"]:
    customers[column] = customers[column].fillna(customers[column].mode().iloc[0])
print("After cleaning:", customers.shape)
print("Remaining missing values:", int(customers.isna().sum().sum()))
""",
            r"""
# Cap extreme numeric values using IQR bounds.
for column in ["MonthlyCharges", "TotalCharges"]:
    q1, q3 = customers[column].quantile([0.25, 0.75])
    iqr = q3 - q1
    customers[column] = customers[column].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
customers["AverageCharge"] = customers["TotalCharges"] / customers["Tenure"].clip(lower=1)
customers["TenureGroup"] = pd.cut(customers["Tenure"], bins=[0, 12, 24, 48, 100], labels=["New", "Growing", "Established", "Long-term"])
print(customers[["Tenure", "TenureGroup", "AverageCharge", "Churn"]].head().to_string(index=False))
""",
            r"""
# Export the cleaned records before encoding or scaling them for modeling.
customers.to_csv("Telecom_Customer_Churn_Cleaned.csv", index=False)
X = pd.get_dummies(customers.drop(columns=["CustomerID", "Churn"]), drop_first=True, dtype=int)
y = customers["Churn"].eq("Yes").astype(int)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
numeric_columns = ["Tenure", "MonthlyCharges", "TotalCharges", "AverageCharge"]
scaler = StandardScaler()
X_train[numeric_columns] = scaler.fit_transform(X_train[numeric_columns])
X_test[numeric_columns] = scaler.transform(X_test[numeric_columns])
print("Train/test rows:", len(X_train), len(X_test))
print("Churn rate in train/test:", round(y_train.mean(), 3), round(y_test.mean(), 3))
print("Saved Telecom_Customer_Churn_Cleaned.csv")
""",
        ],
        "9_telecom_churn_cleaning.ipynb",
    )

    notebook(
        "Q10: Data Wrangling",
        "Data Wrangling on Real Estate Market",
        [
            r"""
import re
import pandas as pd
import matplotlib.pyplot as plt

homes = pd.read_csv("RealEstate_Prices.csv")
amenities = pd.read_csv("RealEstate_Neighborhoods.csv")
print("Raw shape:", homes.shape)
print(homes.head().to_string(index=False))
print("Missing values:\n", homes.isna().sum().to_string())
""",
            r"""
# Clean column names and types; fill the missing area with the median.
homes.columns = [re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") for name in homes.columns]
homes["sale_date"] = pd.to_datetime(homes["sale_date"], errors="coerce")
homes["neighborhood"] = homes["neighborhood"].astype(str).str.strip().str.title()
homes["area_sqft"] = homes["area_sqft"].fillna(homes["area_sqft"].median())
homes = homes.dropna(subset=["sale_date", "sale_price"])
print("Clean columns:", homes.columns.tolist())
""",
            r"""
# Merge neighborhood amenities and select a recent subset.
homes = homes.merge(amenities, left_on="neighborhood", right_on="Neighborhood", how="left", validate="many_to_one")
homes = homes.drop(columns="Neighborhood")
recent = homes.loc[homes["sale_date"] >= "2024-01-01"].copy()
print("Recent properties:", len(recent))
print(recent[["neighborhood", "NearbyAmenities"]].head().to_string(index=False))
""",
            r"""
# Cap unusually high prices and derive price per square foot.
q1, q3 = recent["sale_price"].quantile([0.25, 0.75])
upper = q3 + 1.5 * (q3 - q1)
print("Prices above IQR upper bound:", int((recent["sale_price"] > upper).sum()))
recent["sale_price_capped"] = recent["sale_price"].clip(upper=upper)
recent["price_per_sqft"] = recent["sale_price_capped"] / recent["area_sqft"]
print(recent.groupby("neighborhood")["sale_price_capped"].agg(["count", "mean", "median"]).round(2).to_string())
""",
            r"""
# Encode categorical columns for later modeling and compare neighborhoods.
model_features = pd.get_dummies(recent[["neighborhood", "property_type", "area_sqft", "bedrooms", "year_built", "NearbyAmenities"]], drop_first=True, dtype=int)
print("Encoded feature columns:", model_features.columns.tolist())
recent.groupby("neighborhood")["sale_price_capped"].mean().sort_values().plot.barh(title="Average sale price by neighborhood")
plt.xlabel("Sale price")
plt.tight_layout()
plt.show()
""",
        ],
        "10_real_estate_wrangling.ipynb",
    )

    notebook(
        "Q11: Data Visualization using matplotlib",
        "Analyzing Air Quality Index (AQI) Trends in a City",
        [
            r"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

air = pd.read_csv("City_Air_Quality.csv", parse_dates=["Date"])
print("Shape:", air.shape)
print(air.head().to_string(index=False))
print(air[["PM2.5", "PM10", "CO", "AQI"]].describe().round(2).to_string())
""",
            r"""
# Overall AQI time series and individual pollutant trends.
fig, axes = plt.subplots(3, 1, figsize=(11, 9))
air.plot(x="Date", y="AQI", ax=axes[0], legend=False, color="firebrick", title="AQI over time")
air.plot(x="Date", y=["PM2.5", "PM10"], ax=axes[1], title="Particulate matter over time")
air.plot(x="Date", y="CO", ax=axes[2], legend=False, color="teal", title="CO over time")
axes[0].set_ylabel("AQI")
axes[1].set_ylabel("µg/m³")
axes[2].set_ylabel("CO")
plt.tight_layout()
plt.show()
""",
            r"""
# Compare monthly AQI and AQI distributions across PM2.5 categories.
air["Month"] = air["Date"].dt.to_period("M").astype(str)
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
air.groupby("Month")["AQI"].mean().plot.bar(ax=axes[0], color="slateblue", title="Mean AQI by month")
axes[0].set_ylabel("Mean AQI")
axes[0].tick_params(axis="x", rotation=45)
air["PM25Band"] = pd.cut(air["PM2.5"], bins=[0, 25, 40, 60, np.inf], labels=["Low", "Moderate", "High", "Very high"])
bands = [(label, air.loc[air["PM25Band"] == label, "AQI"]) for label in air["PM25Band"].cat.categories]
bands = [(label, values) for label, values in bands if not values.empty]
axes[1].boxplot([values for _, values in bands], tick_labels=[label for label, _ in bands])
axes[1].set_title("AQI by PM2.5 category")
axes[1].set_ylabel("AQI")
plt.tight_layout()
plt.show()
""",
            r"""
# Explore the relationship between particulate matter and AQI.
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
axes[0].scatter(air["PM2.5"], air["AQI"], c=air["CO"], cmap="viridis", alpha=0.7)
axes[0].set(xlabel="PM2.5", ylabel="AQI", title="AQI versus PM2.5 (color = CO)")
correlation = air[["PM2.5", "PM10", "CO", "AQI"]].corr()
image = axes[1].imshow(correlation, cmap="coolwarm", vmin=-1, vmax=1)
axes[1].set_xticks(range(4), correlation.columns, rotation=35)
axes[1].set_yticks(range(4), correlation.columns)
axes[1].set_title("Measurement correlations")
fig.colorbar(image, ax=axes[1], shrink=0.8)
plt.tight_layout()
plt.show()
""",
        ],
        "11_air_quality_visualization.ipynb",
    )

    notebook(
        "Q12: Data Aggregation",
        "Analyzing Sales Performance by Region in a Retail Company",
        [
            r"""
import pandas as pd
import matplotlib.pyplot as plt

retail = pd.read_csv("Retail_Sales_Data.csv", parse_dates=["TransactionDate"])
print("Transactions:", len(retail))
print(retail.head().to_string(index=False))
print("Regions:", sorted(retail["Region"].unique()))
""",
            r"""
# Total sales and transaction counts by region.
by_region = retail.groupby("Region").agg(TotalSales=("SalesAmount", "sum"), Transactions=("TransactionID", "count"))
by_region = by_region.sort_values("TotalSales", ascending=False)
print(by_region.round(2).to_string())
print("Top-performing region:", by_region.index[0])
""",
            r"""
# Compare the regional distribution as both bars and shares.
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
by_region["TotalSales"].plot.bar(ax=axes[0], title="Sales by region", color="steelblue")
axes[0].set_ylabel("Total sales")
by_region["TotalSales"].plot.pie(ax=axes[1], title="Regional sales share", autopct="%1.0f%%")
axes[1].set_ylabel("")
plt.tight_layout()
plt.show()
""",
            r"""
# Group by both region and product category to expose the sales mix.
regional_category = retail.pivot_table(index="Region", columns="ProductCategory", values="SalesAmount", aggfunc="sum", fill_value=0)
print(regional_category.round(2).to_string())
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
regional_category.plot.bar(stacked=True, ax=axes[0], title="Stacked sales mix")
regional_category.plot.bar(ax=axes[1], title="Grouped category comparison")
for axis in axes:
    axis.set_ylabel("Sales amount")
    axis.tick_params(axis="x", rotation=0)
plt.tight_layout()
plt.show()
""",
        ],
        "12_retail_sales_aggregation.ipynb",
    )

    notebook(
        "Q13: Time Series Data Analysis",
        "Analysis and Visualization of Stock Market Data",
        [
            r"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

stocks = pd.read_csv("Stock_Prices.csv", parse_dates=["Date"]).sort_values("Date").set_index("Date")
print("Rows and columns:", stocks.shape)
print(stocks.head().to_string())
print("Date span:", stocks.index.min().date(), "to", stocks.index.max().date())
""",
            r"""
# Plot historical prices and 20/50-day rolling averages.
stocks["MA20"] = stocks["Close"].rolling(20).mean()
stocks["MA50"] = stocks["Close"].rolling(50).mean()
stocks[["Close", "MA20", "MA50"]].plot(figsize=(11, 4), title="Closing price and moving averages")
plt.ylabel("Price")
plt.tight_layout()
plt.show()
""",
            r"""
# Inspect possible weekday/monthly patterns and correlation with the market.
weekday_change = stocks["Close"].pct_change().groupby(stocks.index.day_name()).mean().reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
monthly_close = stocks["Close"].resample("MS").mean()
print("Mean daily return by weekday:\n", (weekday_change * 100).round(3).to_string(), "%")
print("Close/volume/market correlations:\n", stocks[["Close", "Volume", "MarketIndex"]].corr().round(3).to_string())
monthly_close.plot.bar(figsize=(10, 3), title="Mean closing price by month")
plt.ylabel("Price")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
""",
            r"""
# Holt's linear exponential smoothing: fit only on the training period.
train = stocks["Close"].iloc[:-30]
test = stocks["Close"].iloc[-30:]
alpha, beta = 0.35, 0.08
level = float(train.iloc[0])
trend = float(train.iloc[1] - train.iloc[0])
for value in train.iloc[1:]:
    old_level = level
    level = alpha * float(value) + (1 - alpha) * (level + trend)
    trend = beta * (level - old_level) + (1 - beta) * trend
forecast = pd.Series(level + np.arange(1, len(test) + 1) * trend, index=test.index, name="Forecast")
mae = (forecast - test).abs().mean()
print("Held-out mean absolute error:", round(mae, 2))
print(pd.DataFrame({"Actual": test, "Forecast": forecast}).head().round(2).to_string())
""",
            r"""
# Compare the held-out prices with the exponential-smoothing forecast.
ax = train.iloc[-60:].plot(figsize=(10, 4), label="Training close")
test.plot(ax=ax, label="Actual close")
forecast.plot(ax=ax, label="Holt forecast", linestyle="--")
ax.set(title="Held-out stock price forecast", ylabel="Price")
ax.legend()
plt.tight_layout()
plt.show()
""",
        ],
        "13_stock_time_series.ipynb",
    )


if __name__ == "__main__":
    make_datasets()
    build_notebooks()
