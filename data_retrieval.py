import easyocr
import pandas as pd
import numpy as np
from collections import defaultdict
import psycopg2

def create_dataframe(pdf):

    # ---------- OCR ----------
    reader = easyocr.Reader(['en'])

    ocr = ocr_result


    # ---------- Extract OCR ----------
    words = []

    for bbox, text, confidence in ocr:
        x = bbox[0][0]
        y = bbox[0][1]

        words.append({
            "text": text,
            "x": x,
            "y": y,
            "confidence": confidence
        })


    # ---------- Only keep result table ----------
    # Header starts around y=1180
    table_words = [
        w for w in words
        if 1180 < w["y"] < 2450
    ]


    # ---------- Group rows by Y position ----------
    rows = defaultdict(list)

    for w in table_words:
        # 40 px tolerance
        row_key = round(w["y"] / 40) * 40
        rows[row_key].append(w)



    # ---------- Column mapping ----------
    def get_column(x):

        if x < 220:
            return "class"

        elif x < 500:
            return "driver"

        elif x < 1300:
            return "team"

        elif x < 1650:
            return "lap"

        elif x < 1850:
            return "best_time"

        elif x < 2050:
            return "diff"

        elif x < 2180:
            return "kph"

        else:
            return "time"



    # ---------- Build table ----------
    results = []

    for y, row in sorted(rows.items()):

        data = {
            "class":"",
            "driver":"",
            "team":"",
            "lap":"",
            "best_time":"",
            "diff":"",
            "kph":"",
            "time":"",
        }

        for item in sorted(row, key=lambda x:x["x"]):

            col = get_column(item["x"])

            if data[col]:
                data[col] += " " + item["text"]
            else:
                data[col] = item["text"]


        # only keep driver rows
        if data["driver"] and not "Drivers" in data["driver"]:
            results.append(data)
    


    df = pd.DataFrame(results)


    import re


    def clean_driver(value):
        if not isinstance(value, str):
            return ""

        value = value.strip()

        # Remove OCR-added car model
        value = re.sub(
            r"\s*Tatuus\s*T326.*$",
            "",
            value,
            flags=re.IGNORECASE
        ).strip()

        return value


    def is_driver_row(value):
        if not isinstance(value, str):
            return False

        value = clean_driver(value)

    # Driver rows start with car number + text
    # Examples:
    # 51 KMakamura-Berta
    # 2 ANinovic
    # 88 SHanna
        return bool(
            re.match(
                r"^\d+\s+[A-Za-z]",
                value
            )
        )


    # Clean driver column first
    df["driver"] = df["driver"].apply(clean_driver)


    # Keep only real drivers
    df = df[
        df["driver"].apply(is_driver_row)
    ]


    df = df.reset_index(drop=True)
    df['events'] = pdf
    df["pos"] = df.groupby("events").cumcount() + 1
    return df

from io import BytesIO
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import easyocr
import pdfplumber
import os
from urllib.parse import urlparse

url = "https://fiafrec.com/races-results/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")


pdfs = []

for link in soup.find_all("a", href=True):
    href = link["href"]

    if "upload" in href.lower() and href.lower().endswith(".pdf"):
        full_url = urljoin(url, href)
        pdfs.append(full_url)


def pdf_url_to_image(url, output="page.png", page_number=0):

    response = requests.get(url)
    response.raise_for_status()

    pdf_file = BytesIO(response.content)

    with pdfplumber.open(pdf_file) as pdf:
        page = pdf.pages[page_number]

        img = page.to_image(resolution=300)
        img.save(output)

    return output

for pdf in pdfs:
    try:
        print(f"Processing: {pdf}")

        image_file = pdf_url_to_image(pdf)

        reader = easyocr.Reader(['en'])

        ocr_result = reader.readtext(
            image_file,
            detail=1
        )

        for item in ocr_result:
            print(item[1], item[2])

        df = create_dataframe(pdf)

        pdf_name = os.path.basename(urlparse(pdf).path).lower()
        csv_name = pdf_name.replace(".pdf", ".csv")

        if 'qualifying' in pdf_name:

            conn = psycopg2.connect(
                host="ep-long-glitter-at9v26w9-pooler.c-9.us-east-1.aws.neon.tech",
                database="neondb",
                user="neondb_owner",
                password="npg_P6OimSTt9ngC",
                port=5432,
                sslmode="require"
            )

            cur = conn.cursor()

            cur.execute("""
            CREATE TABLE IF NOT EXISTS frec_qualifying (
                class TEXT,
                driver TEXT,
                team TEXT,
                lap TEXT,
                best_time TEXT,
                diff TEXT,
                kph TEXT,
                time TEXT,
                pos TEXT,
                events TEXT,
            )
            """)
            conn.commit()

            insert_query = """
            INSERT INTO frec_qualifying (
                class, driver, team,
                lap, best_time, diff,
                kph, time, pos, events
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """

            if not df.empty:
                cur.executemany(insert_query, df.values.tolist())
                conn.commit()
                print(f"Inserted {len(df)} rows.")
            else:
                print("No rows found in OCR.")

            cur.close()
            conn.close()

        print("Done importing quali session data for FREC.")
        if 'race' in pdf_name:

            conn = psycopg2.connect(
                host="ep-long-glitter-at9v26w9-pooler.c-9.us-east-1.aws.neon.tech",
                database="neondb",
                user="neondb_owner",
                password="npg_P6OimSTt9ngC",
                port=5432,
                sslmode="require"
            )

            cur = conn.cursor()

            cur.execute("""
            CREATE TABLE IF NOT EXISTS frec_race (
                class TEXT,
                driver TEXT,
                team TEXT,
                lap TEXT,
                best_time TEXT,
                diff TEXT,
                kph TEXT,
                time TEXT,
                pos TEXT,
                events TEXT
            )
            """)
            conn.commit()

            insert_query = """
            INSERT INTO frec_race (
                class, driver, team,
                lap, best_time, diff,
                kph, time, pos,events
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """

            if not df.empty:
                cur.executemany(insert_query, df.values.tolist())
                conn.commit()
                print(f"Inserted {len(df)} rows.")
            else:
                print("No rows found in OCR.")

            cur.execute("""
DELETE FROM frec_race a
USING frec_race b
WHERE a.ctid < b.ctid
  AND a.class IS NOT DISTINCT FROM b.class
  AND a.driver IS NOT DISTINCT FROM b.driver
  AND a.team IS NOT DISTINCT FROM b.team
  AND a.best_time IS NOT DISTINCT FROM b.best_time
  AND a.diff IS NOT DISTINCT FROM b.diff
  AND a.kph IS NOT DISTINCT FROM b.kph
  AND a.time IS NOT DISTINCT FROM b.time
  AND a.pos IS NOT DISTINCT FROM b.pos
  AND a.events IS NOT DISTINCT FROM b.events;
""")
            conn.commit()
            cur.close()
            conn.close()
            print(f"Deleted {cur.rowcount} duplicate rows.")
        print("Done importing race session data for FREC.")
        if 'practice' in pdf_name:

            conn = psycopg2.connect(
                host="ep-long-glitter-at9v26w9-pooler.c-9.us-east-1.aws.neon.tech",
                database="neondb",
                user="neondb_owner",
                password="npg_P6OimSTt9ngC",
                port=5432,
                sslmode="require"
            )

            cur = conn.cursor()

            cur.execute("""
            CREATE TABLE IF NOT EXISTS frec_practice (
                class TEXT,
                driver TEXT,
                team TEXT,
                lap TEXT,
                best_time TEXT,
                diff TEXT,
                kph TEXT,
                time TEXT,
                pos TEXT,
                events TEXT
            )
            """)
            conn.commit()

            insert_query = """
            INSERT INTO frec_practice (
                class, driver, team,
                lap, best_time, diff,
                kph, time, pos, events
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """

            if not df.empty:
                cur.executemany(insert_query, df.values.tolist())
                conn.commit()
                print(f"Inserted {len(df)} rows.")
            else:
                print("No rows found in OCR.")

            cur.execute("""
DELETE FROM frec_practice a
USING frec_practice b
WHERE a.ctid < b.ctid
  AND a.class IS NOT DISTINCT FROM b.class
  AND a.driver IS NOT DISTINCT FROM b.driver
  AND a.team IS NOT DISTINCT FROM b.team
  AND a.best_time IS NOT DISTINCT FROM b.best_time
  AND a.diff IS NOT DISTINCT FROM b.diff
  AND a.kph IS NOT DISTINCT FROM b.kph
  AND a.time IS NOT DISTINCT FROM b.time
  AND a.pos IS NOT DISTINCT FROM b.pos
  AND a.events IS NOT DISTINCT FROM b.events;
""")
            conn.commit()
            print(f"Deleted {cur.rowcount} duplicate rows.")
            cur.close()
            conn.close()

    except Exception as e:
        print(f"Failed to process {pdf}")
        print(f"Error: {e}")

        # Close the database connection if it was opened
        try:
            cur.close()
            conn.close()
        except:
            pass

        continue
