from bs4 import BeautifulSoup
import requests

#import json
url = 'https://www.congress.gov/congressional-record'

response = requests.get(url)

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    dailyDigest = soup.find('div', id='daily-digest-content')
    print(measuresPassed)