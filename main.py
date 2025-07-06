from datetime import datetime, timezone
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
month = 6
# month = yesterday.month
#day = yesterday.day
day = 5

#BlueSky
client = Client()


def post_to_blueSky(message):
    user_name = os.getenv('BLUESKY_NAME')
    password = os.getenv('BLUESKY_PASS')

    client.login(user_name, password)

    session_resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": user_name, "password": password},
    )

    session_resp.raise_for_status()
    session = session_resp.json()
    access_token = session["accessJwt"]
    did = session["did"]

    print("Logged in to Bluesky")

    posts = make_sub_tweets(message)
    thread_root = None
    thread_parent = None

    for i, post_text in enumerate(posts):
        segment = f"{i + 1}/{len(posts)}\n{post_text}".strip()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if len(segment.encode("utf-8")) > 300:
            raise ValueError("Post segment exceeds 300-byte Bluesky limit.")


        record = {
            "$type": "app.bsky.feed.post",
            "text": segment,
            "createdAt": now,
            "facets": parse_facets(segment)
        }
        
        if thread_root and thread_parent:
            record["reply"] = {
                "root": {
                    "uri": thread_root["uri"],
                    "cid": thread_root["cid"]
                },
                "parent": {
                    "uri": thread_parent["uri"],
                    "cid": thread_parent["cid"]
                }
            }
        
        post_resp = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": record,
            },
        )

        post_resp.raise_for_status()
        post_data = post_resp.json()
        print(segment)
        
        if i == 0:
            thread_root = post_data
        thread_parent = post_data

#BLUESKY API FUNCTIONS
def parse_mentions(text: str) -> list[dict]:
    spans = []
    # regex based on: https://atproto.com/specs/handle#handle-identifier-syntax
    mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(mention_regex, text_bytes):
        spans.append({
            "start": m.start(1),
            "end": m.end(1),
            "handle": m.group(1)[1:].decode("UTF-8")
        })
    return spans

def parse_urls(text: str) -> list[dict]:
    spans = []
    # partial/naive URL regex based on: https://stackoverflow.com/a/3809435
    # tweaked to disallow some training punctuation
    url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(url_regex, text_bytes):
        spans.append({
            "start": m.start(1),
            "end": m.end(1),
            "url": m.group(1).decode("UTF-8"),
        })
    return spans

def parse_facets(text: str) -> list[dict]:
    facets = []

    for m in parse_mentions(text):
        resp = requests.get(
            "https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": m["handle"]},
        )
        if resp.status_code == 400:
            continue
        did = resp.json()["did"]
        facets.append({
            "index": {
                "byteStart": m["start"],
                "byteEnd": m["end"],
            },
            "features": [{
                "$type": "app.bsky.richtext.facet#mention",
                "did": did
            }]
        })

    for u in parse_urls(text):
        facets.append({
            "index": {
                "byteStart": u["start"],
                "byteEnd": u["end"],
            },
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": u["url"]
            }]
        })

    return facets

#CONGRESS API FUNCTIONS
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

        return senate_text, formatted_house_text

    except Exception as e:
        return f"❌ Error reading PDF: {e}"

def fix_hyphenation(text):
    fixed_text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
    return fixed_text

def make_senate_bills_array(text):
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
    house_text = re.sub(r'\s+', ' ', house_text)  # normalize whitespace

    # === 3. Match each action block mentioning a bill ===
    block_pattern = re.compile(
        r'(?P<action_block>'
            r'(?:The House|House)\s+'
            r'(?:agreed to|passed|approved)\s+.*?'
            r'(?:H\.R\.|H\.Res\.|H\.J\. Res\.)\s*\d+.*?(?=[.?!])'
        r')',
        re.IGNORECASE | re.DOTALL
    )

    results = []

    for match in block_pattern.finditer(house_text):
        action_block = fix_hyphenation(match.group("action_block").strip())

        # Extract bill identifier and number
        bill_match = re.search(r'\b(H\.R\.|H\.Res\.|H\.J\. Res\.)\s*(\d+)\b', action_block)
        if not bill_match:
            continue

        bill_prefix = bill_match.group(1)
        bill_num = bill_match.group(2)

        results.append({
            "bill_num": bill_num,
            "title": f"{bill_prefix} {bill_num}",
            "text": action_block
        })

    formatted_text = format_house_text(results)
    return formatted_text

def format_house_text(houseBillArray):
    final_text = ""

    if houseBillArray == []:
        final_text = "\nNo measures were passed in the house today\n"
    else:
        for results in houseBillArray:
            final_text += f"\n== {results['title']} ==\n"
            final_text += f"{results['text']}\n"
            final_text += "\n" + build_URL_bill("H", results["bill_num"]) + "\n"
    
    #credit line for where to source daily digest and "created by Broc - github link"
    return final_text

def make_final_tweet(billArray, house_text):
        final_tweet = f"BILLS THAT WERE PASSED IN CONGRESS: {month}-{day}-{year}\n"
        final_tweet += "\n------Senate------\n"
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


            final_tweet += f"\n== {bill_type} {bill_number} =="
            final_tweet += f"\n{fBills}\n"

            #todo: slice off everything in bill after page number, 
            # save page number as variable to input into build_URL_bill
            #needs to match the numbers and Letter of H or S exactly 
            if match:
                houseOrSenate = bill_type[0:1]
                billURL = build_URL_bill(houseOrSenate, bill_number)
                final_tweet += f"\n{billURL}\n"

        final_tweet += "\n------House------\n"
        final_tweet += f"\n{house_text}\n"

        #CREDITS BLOCK
        githubProjectLink = "https://github.com/dwaynethebroc/USCongress_Bills_BlueSkyBot"
        sourceURL = "https://www.congress.gov/congressional-record"
        final_tweet += f"\nTo read the full source of all bills: {sourceURL}\n"
        final_tweet += f"\nProject created and maintained here: {githubProjectLink}\n"
        return final_tweet
   
def make_sub_tweets(finalTweet: str):
    lines = finalTweet.splitlines()
    tweet_length = len(finalTweet.encode("utf-8"))
    print(f"Full byte length: {tweet_length}")

    if tweet_length > 300:
        print("Message over 300 bytes, splitting into multiple posts")
    else:
        print("Message length: ", tweet_length)

    posts = []
    current_tweet = ""
    max_bytes = 290  # Reserve 10 bytes for "1/40" etc.

    for line in lines:
        # Try to add this line to the current tweet
        candidate = f"{current_tweet.strip()}\n{line}".strip()
        byte_len = len(candidate.encode("utf-8"))

        if byte_len > max_bytes:
            if current_tweet:
                posts.append(current_tweet.strip())
            current_tweet = line  # Start new tweet with this line
        else:
            current_tweet = candidate  # Safe to add this line

    if current_tweet:
        posts.append(current_tweet.strip())

    return posts
def main():
    pdf_path = os.path.join(folder_path, f"daily_digest_{day}.{month}.{year}.pdf")

    #if yesterday was an active day in session
    DIS_flag = check_DIS()

    if(DIS_flag):
        #if PDF file already exists for the requested day, 
        # do not download the file again and instead return the formatted Measures Passed section:
        if os.path.isfile(pdf_path):
            print("PDF already exists")

            senate_text, house_text = extract_text_from_pdf(pdf_path)
            bills_senate = make_senate_bills_array(senate_text)
            final_tweet = make_final_tweet(bills_senate, house_text)

            post_to_blueSky(final_tweet)
            
        else:
            print("PDF does not exist")

            url = build_url_daily_digest()
            print(url)
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
                senate_text, house_text = extract_text_from_pdf(pdf_path)
                bills_senate = make_senate_bills_array(senate_text)
                final_tweet = make_final_tweet(bills_senate, house_text)

                post_to_blueSky(final_tweet)

# ==== Main Program ====
if __name__ == "__main__":
    main()

