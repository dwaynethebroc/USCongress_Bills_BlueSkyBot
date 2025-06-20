from datetime import datetime
from datetime import timedelta
from dotenv import load_dotenv
import pypdf
import os
import json
import requests

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
day = 12

def extract_text_from_pdf(pdf_file: str) -> [str]:
    with open(pdf_file, 'rb') as pdf:
        reader = pypdf.PdfReader(pdf, strict=False)
        pdf_text = ""

        for page in reader.pages[:5]:
            content = page.extract_text()
            if pdf_text:
                pdf_text += "\n" + content


        starting_flag = "Measures Passed:"
        start_index = pdf_text.find(starting_flag)

        if start_index == -1:
            return "X 'Measures Passed:' section not found"

        return pdf_text

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

url = build_url()

response = requests.get(url)

if response.status_code == 200:
    x = response.json()
    print(x)

    digest_pdf_url = x["Results"]["Issues"][0]["Links"]["Digest"]["PDF"][0]["Url"]
    print(digest_pdf_url)   
else:
    print(f"Request failed with status code {response.status_code}")
    print(response.text)  # Print response for debugging


response = requests.get(digest_pdf_url)

if response.status_code == 200:
    # Delete all existing PDFs in the folder
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
            print(filename, "is removed")

    with open(f"pdf/daily_digest_{day}.{month}.{year}.pdf", "wb") as f:
        f.write(response.content)
    print("PDF downloaded sucessfully")

else:
    print("Failed to download PDF")

try:
    with open(f"{folder_path}/daily_digest_{day}.{month}.{year}.pdf", "rb") as file:
        reader = pypdf.PdfReader(file)

        first_page = reader.pages[0]
        text = first_page.extract_text()
        print("first page")
        print(reader.pages[0])
except FileNotFoundError:
        print(f"Error: The file '{pdf_path}' was not found.")
except Exception as e:
    print(f"An error occured: {e}")