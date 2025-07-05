from datetime import datetime
from datetime import timedelta
from dotenv import load_dotenv
import pypdf
import os
import json
import requests
import re
from atproto import Client

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
day = 29

#BlueSky
client = Client()
user_name = os.getenv('BLUESKY_NAME')
password = os.getenv('BLUESKY_PASS')

def post_to_blueSky(message):
    client.login(user_name, password)
    client.send_post(text=message)

def check_DIS():
    #check if date exists in days-in-session calendar
    day_in_session_flag = False

    dis_month = month
    dis_day = day

    #convert to same day, month format as json file
    if int(dis_month) > 0 and int(dis_month) < 10:
        dis_month = "0" + str(dis_month)

    if int(dis_day) > 0 and int(dis_day) < 10:
        dis_day = "0" + str(dis_day)

    #reformat date to double digit month, day always ex: 06, 09, etc
    json_format_current_day = f"{year}-{dis_month}-{dis_day}"

    with open('session_days_2025.json', 'r') as f:
        data = json.load(f)

        dates_in_session = data["DiS_2025"]

        if json_format_current_day in dates_in_session:
            day_in_session_flag = True
            print("Yesterday was a day in session in congress")
        else:
            print("Yesterday was not a day in congress")

    return day_in_session_flag

def build_url_daily_digest():
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

        senate_text = cleaned_text[start_index:min_end_index].strip()

        # === Extract House Section ===
        house_text = ""
        house_start = cleaned_text.find("House of Representatives")
        if house_start != -1:
            house_end = cleaned_text.find("Extensions of Remarks", house_start)
            house_text = cleaned_text[house_start:house_end].strip() if house_end != -1 else cleaned_text[house_start:]

        formatted_house_text = splice_house_text_paragraphs(house_text)
        print(formatted_house_text)

        combined_text += "------Senate------"
        combined_text += f"{senate_text}\n"
        combined_text += "------House------"
        combined_text += f"{formatted_house_text}\n"

        return combined_text

    except Exception as e:
        return f"❌ Error reading PDF: {e}"

def fix_hyphenation(text):
    fixed_text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
    return fixed_text

def format_bills_paragraphs(text):
    # Step 1: Remove the "Measures Passed:" header and fix hyphenation artifacts
    text = re.sub(r'^Measures Passed:\s*', '', text.strip(), flags=re.IGNORECASE)
    text = fix_hyphenation(text)

    # Step 2: Define known end flags that terminate the section
    end_flags = [
        "Measures Considered:",
        "Nominations",
        "Appointments",
        "Nomination--Agreement",
        "Nomination--Cloture",
        "Additional Cosponsors",
        "Additional Statements"
    ]

    # Step 3: Truncate text after the first end flag (inclusive)
    for flag in end_flags:
        idx = text.find(flag)
        if idx != -1:
            text = text[:idx + len(flag)].strip()
            break

    # Step 4: Match both single and range-style page tags
    pattern_range = r'Pages S\d{4}–(?:S?\d{2,4})'
    pattern_single = r'Page S\d{4}'
    matches = sorted(
        [*re.finditer(pattern_range, text), *re.finditer(pattern_single, text)],
        key=lambda m: m.start()
    )

    if not matches:
        return [text.strip()]

    bills = []

    # First bill: from start to first page tag end
    bills.append(text[:matches[0].end()].strip())

    # Intermediate bills: between previous and current page tag
    for i in range(1, len(matches)):
        prev_end = matches[i - 1].end()
        curr_end = matches[i].end()
        bills.append(text[prev_end:curr_end].strip())

    # Step 5: Handle any extra content after the last page tag
    last_match = matches[-1]
    after_last_tag = text[last_match.end():].strip()

    if after_last_tag and not any(flag in after_last_tag for flag in end_flags):
        # Only append if it's legitimate content (not headings or garbage)
        bills[-1] += " " + after_last_tag
    elif after_last_tag and not re.search(r'\w{4,}', after_last_tag):
        # It's just short or meaningless trailing junk (like "Kies") — ignore it
        pass
    elif not after_last_tag:
        # Nothing more to add
        pass
    else:
        # If the final text is something unrelated, drop the last bill altogether
        bills = bills[:-1]

    return bills

def make_final_tweet(billArray):
        final_tweet = f"BILLS THAT WERE PASSED TODAY IN CONGRESS: {month}-{day}-{year}\n"
        fix_hyphenation_bills = []
        for bill in billArray:
            hyphen_bill = fix_hyphenation(bill)
            fix_hyphenation_bills.append(hyphen_bill)
    
        # Regex pattern to extract bill name (covers House and Senate bill/resolution formats)
        # bill_pattern = re.compile(r'\b(H(?:\.|ouse)?\.?\s*(?:R|Res|J\.?\s*Res)\.?\s*\d+|S(?:\.|enate)?\.?\s*(?:J\.?\s*Res|Res)?\.?\s*\d+)')
        bill_pattern = re.compile(
            r'\b(?P<prefix>H(?:\.|ouse)?\.?\s*(?:R|Res|J\.?\s*Res)|S(?:\.|enate)?\.?\s*(?:J\.?\s*Res|Res)?)\.?\s*(?P<number>\d+)\b',
            re.IGNORECASE
        )

        for fBills in fix_hyphenation_bills:
            match = bill_pattern.search(fBills)
            bill_type = match.group("prefix")
            bill_number = match.group("number")


            final_tweet += f"\n==== {bill_type + " " + bill_number} ===="
            final_tweet += f"\n{fBills}\n"

            #todo: slice off everything in bill after page number, 
            # save page number as variable to input into build_URL_bill
            #needs to match the numbers and Letter of H or S exactly 
            if match:
                houseOrSenate = bill_type[0:1]
                billURL = build_URL_bill(houseOrSenate, bill_number)
                print(bill_type)
                print(bill_number)
                print(houseOrSenate)
                final_tweet += f"\nLink to full bill: {billURL}\n"

        return final_tweet
    
def build_URL_bill(houseOrSenate, bill_number):
    #URL will need to be adjusted with future congresses to function after 2025
    houseBaseURL = f"https://www.congress.gov/bill/119th-congress/house-bill/{bill_number}"
    senateBaseURL = f"https://www.congress.gov/bill/119th-congress/senate-bill/{bill_number}"

    if(houseOrSenate[0:1] == "H"):
        return houseBaseURL
    elif(houseOrSenate[0:1] == "S"):
        return senateBaseURL
    else:
        return ""

def splice_house_text_paragraphs(text):
    """
    Extracts structured info for passed/agreed-to House bills or rules that enable bill consideration.
    Only includes the main bill mentioned, storing only the numeric part as 'bill_num'.
    """

    # === 1. End flags to stop parsing ===
    end_flags = [
        "Extensions of Remarks",
        "Committee Meetings",
        "Next Meeting",
        "Senate Referrals",
        "Committee Ranking",
        "Quorum Calls",
        "Adjournment",
    ]

    # === 2. Truncate text at the first end flag ===
    lower_text = text.lower()
    min_index = len(text)
    for flag in end_flags:
        idx = lower_text.find(flag.lower())
        if idx != -1 and idx < min_index:
            min_index = idx

    house_text = text[:min_index].strip()

    # === 3. Match each bill-related action block ===
    block_pattern = re.compile(
        r'(?P<title>.*?[.:])\s*'
        r'(?P<action_block>'
        r'(?:The House|House)\s+'
        r'(agreed to|passed|approved)\s+'
        r'(?:the\s+)?(?:resolution|bill)?\s*'
        r'(?P<res_bill>(H\.R\.|H\.Res\.|H\.J\. Res\.)\s*\d+)[\s\S]*?)'
        r'(?=(?:The House|House)\s+(?:agreed to|passed|approved)|' + '|'.join(end_flags) + r'|$)',
        re.IGNORECASE
    )

    results = []

    for match in block_pattern.finditer(house_text):
        title = match.group("title").strip()
        action_block = match.group("action_block").strip()

        # Extract the first full bill ID and its number
        bill_match = re.search(r'\b(H\.R\.|H\.Res\.|H\.J\. Res\.)\s*(\d+)\b', action_block)
        if not bill_match:
            continue

        bill_num = bill_match.group(2)  # only the number (e.g., '3944')

        # Only include relevant legislative actions
        if (
            'providing for consideration of the bill' in action_block.lower()
            or 'impeaching' in title.lower()
        ):
            results.append({
                "bill_num": bill_num,
                "title": title,
                "text": action_block
            })

    formatted_text = format_house_text(results)
    return formatted_text

def format_house_text(resultsObj):
    final_text = ""
    for results in resultsObj:
        final_text += f"====={results.title}=====\n"
        final_text += f"{results.text}\n"
        final_text += build_URL_bill(results.title, results.bill_num)
    
    return final_text


# ==== Main Program ====

pdf_path = os.path.join(folder_path, f"daily_digest_{day}.{month}.{year}.pdf")

#if yesterday was an active day in session
DIS_flag = check_DIS()

if(DIS_flag):
    #if PDF file already exists for the requested day, 
    # do not download the file again and instead return the formatted Measures Passed section:
    if os.path.isfile(pdf_path):
        print("PDF already exists")

        extracted_text = extract_text_from_pdf(pdf_path)
        #format and separate bills into array
        bills = format_bills_paragraphs(extracted_text)

        final_tweet = make_final_tweet(bills)
        print(final_tweet)
        
    else:
        print("PDF does not exist")
        url = build_url_daily_digest()
        response = requests.get(url)

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

        if download_pdf(digest_pdf_url, pdf_path):
            extracted_text = extract_text_from_pdf(pdf_path)
            print("\n📝 Extracted Text Snippet:\n", extracted_text[:1000])
            #format and separate bills into array
            bills = format_bills_paragraphs(extracted_text)

            final_tweet = make_final_tweet(bills)
            print(final_tweet)

