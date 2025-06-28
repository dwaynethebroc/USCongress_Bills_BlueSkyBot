from datetime import datetime
from datetime import timedelta
from dotenv import load_dotenv
import pypdf
import os
import json
import requests
import re

#load env variables
load_dotenv()
GOV_KEY = os.getenv('GOV_API_KEY')

#load pdf folder
folder_path = "/Users/brocjohnson/repos/USCongress_Bills_BlueSkyBot/pdf"


#get the current day
today = datetime.now()
yesterday = today - timedelta(days = 1)
year = yesterday.year
month = yesterday.month
#day = yesterday.day
day = 25

def build_url():
    #build the URL
    template = 'https://api.congress.gov/v3/congressional-record/?y=2022&m=6&d=28&api_key=[INSERT_KEY]'

    print(day, month, year)


    #build the URL
    begURL = 'https://api.congress.gov/v3/congressional-record?format=json'
    date_string = f'&y={year}&m={month}&d={day}&'
    API_STRING = f'api_key={GOV_KEY}'

    url = begURL + date_string + API_STRING
    return url

def download_pdf(url: str, path: str):
    try:
        with requests.get(url, stream=True, timeout=20) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print("PDF downloaded successfully")
            return True
    except requests.RequestException as e:
        print("Failed to download PDF: ", e)
        return False

def extract_text_from_pdf(pdf_file: str) -> str:
    try:
        with open(pdf_file, 'rb') as pdf:
            reader = pypdf.PdfReader(pdf, strict=False)
            pdf_text = ""

            for page in reader.pages[:5]:
                content = page.extract_text()
                if content:
                    pdf_text += "\n" + content

        # Normalize whitespace
        cleaned_text = re.sub(r'\s+', ' ', pdf_text)

        # Find start
        start_flag = "Measures Passed:"
        start_index = cleaned_text.find(start_flag)
        if start_index == -1:
            return "⚠️ 'Measures Passed:' section not found"

        # Search for the closest *valid* end flag after start
        end_flags = [
            "Measures Considered:",
            "Nominations",
            "Appointments",
            "Nomination—Agreement:",
            "Nomination—Cloture",
            "Nomination Confirmed:"
        ]

        # Track minimum ending index
        min_end_index = len(cleaned_text)
        for flag in end_flags:
            idx = cleaned_text.find(flag, start_index)
            if idx != -1 and idx < min_end_index:
                min_end_index = idx

        section = cleaned_text[start_index:min_end_index].strip()
        return section

    except Exception as e:
        return f"❌ Error reading PDF: {e}"
url = build_url()
response = requests.get(url)

def format_bills_paragraphs(text):
    # Step 1: Clean text
    text = re.sub(r'^Measures Passed:\s*', '', text.strip(), flags=re.IGNORECASE)
    text = fix_hyphenation(text)

    # Step 2: Separate patterns
    pattern_range = r'Pages S\d{4}–(?:S?\d{2,4})'
    pattern_single = r'Page S\d{4}'

    # Find matches for both
    matches = [
        *re.finditer(pattern_range, text),
        *re.finditer(pattern_single, text)
    ]

    # Sort matches by position in text
    matches = sorted(matches, key=lambda m: m.start())

    if not matches:
        return [text.strip()]

    bills = []

    # First bill: from start to end of first match
    first_start = 0
    first_end = matches[0].end()
    bills.append(text[first_start:first_end].strip())

    # Remaining bills: between page tags
    for i in range(1, len(matches)):
        start = matches[i - 1].end()
        end = matches[i].end()
        bill = text[start:end].strip()
        if bill:
            bills.append(bill)

    # Last chunk: from end of last match to end of text
    last = matches[-1]
    final_chunk = text[last.end():].strip()
    if final_chunk:
        bills.append(f"{last.group()} {final_chunk}".strip())

    return bills

def fix_hyphenation(text):
    fixed_text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
    return fixed_text

if response.status_code != 200:
    print(f"API Request failed: {response.status_code}")
    print(response.text)
    exit()

try:
    digest_pdf_url = response.json()["Results"]["Issues"][0]["Links"]["Digest"]["PDF"][0]["Url"]
    print("PDF URL:", digest_pdf_url)
except (KeyError, IndexError) as e:
    print("❌ Error parsing API response:", e)
    exit()

# Clean up old PDFs
for f in os.listdir(folder_path):
    try:
        os.remove(os.path.join(folder_path, f))
        print(f"Removed old PDF: {f}")
    except Exception as e:
        print(f"❌ Could not delete file {f}: {e}")


# Download new PDF
pdf_path = os.path.join(folder_path, f"daily_digest_{day}.{month}.{year}.pdf")
extracted_text = ""

if download_pdf(digest_pdf_url, pdf_path):
    extracted_text = extract_text_from_pdf(pdf_path)
    print("\n📝 Extracted Text Snippet:\n", extracted_text[:1000])
    #format and separate bills into array
    bills = format_bills_paragraphs(extracted_text)
    
    fix_hyphenation_bills = []
    for bill in bills:
        hyphen_bill = fix_hyphenation(bill)
        fix_hyphenation_bills.append(hyphen_bill)
    
    for fBills in fix_hyphenation_bills:
        print("==== Bill ====")
        print(f"\n{fBills}\n")
