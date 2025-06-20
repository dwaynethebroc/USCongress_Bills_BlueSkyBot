from datetime import datetime
from datetime import timedelta
from dotenv import load_dotenv
import os
import json
import requests

#load env variables
load_dotenv()
GOV_KEY = os.getenv('GOV_API_KEY')

#build the URL
template = 'https://api.congress.gov/v3/congressional-record/?y=2022&m=6&d=28&api_key=[INSERT_KEY]'

#get the current day
today = datetime.now()
yesterday = today - timedelta(days = 1)
year = yesterday.year
month = yesterday.month
#day = yesterday.day
day = 17
print(day, month, year)


#build the URL
begURL = 'https://api.congress.gov/v3/congressional-record?format=json'
date_string = f'&y={year}&m={month}&d={day}&'
API_STRING = f'api_key={GOV_KEY}'

url = begURL + date_string + API_STRING

response = requests.get(url)

if response.status_code == 200:
    x = response.json()
    print(x)

    pdf_url = x["Results"]["Issues"][0]["Links"]["Digest"]["PDF"][0]["Url"]
    print(pdf_url)   
else:
    print(f"Request failed with status code {response.status_code}")
    print(response.text)  # Print response for debugging


