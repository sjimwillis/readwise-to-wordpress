#!/usr/bin/env python3

import requests
import datetime
import html
from dateutil.parser import parse
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import base64
import re
import os
import pathlib

# Set your Readwise API token and WordPress credentials here
API_TOKEN = "yourtoken"
WP_USER = "username"  # Replace with your username
WP_APP_PASSWORD = "go to users in wp admin and create an app password" #removed d
WP_ENDPOINT = "https://www.yourblog/wp-json/wp/v2/posts"
CATEGORY_ID = 52  # Replace with your category ID

from datetime import datetime, timedelta, timezone

def get_last_run_date():
    home_dir = os.path.expanduser('~')
    config_dir = os.path.join(home_dir, '.readwisepy')
    config_file = os.path.join(config_dir, 'config.txt')

    if not os.path.exists(config_file):
        return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    with open(config_file, 'r') as file:
        last_run_date = file.readline().strip()  # Read as string
    return last_run_date


def update_last_run_date():
    home_dir = pathlib.Path.home()
    config_dir = home_dir / '.readwisepy'
    config_file = config_dir / 'config.txt'

    # Get the current time in UTC and convert it to the local time zone
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()

    # Write the local time to the config file
    with open(config_file, 'w') as file:
        file.write(now_local.isoformat())

def get_start_date_for_highlights(last_run_date=None):
    if last_run_date:
        start_date = last_run_date + timedelta(days=1)
        start_date = start_date.replace(hour=0, minute=1, second=0, microsecond=0, tzinfo=timezone.utc)
    else:
        start_date = datetime.now(timezone.utc).replace(hour=0, minute=1, second=0, microsecond=0)

    print(f"Start Date for Highlights: {start_date}")
    return start_date



# Function to get the start of the current week (Monday at 00:01 AM) as an offset-aware datetime
def get_start_of_week():
    today = datetime.now(timezone.utc)
    start_of_week = today - timedelta(days=today.weekday(), hours=today.hour, minutes=today.minute, seconds=today.second, microseconds=today.microsecond) + timedelta(minutes=1)
    return start_of_week

# Function to check if the date is within the current week
def is_date_within_current_week(date_str):
    highlight_date = parse(date_str)
    start_of_week = get_start_of_week()
    return highlight_date >= start_of_week

# Function to fetch book details (title, source URL, author, and category) using book_id
def fetch_book_details(api_token, book_id):
    url = f"https://readwise.io/api/v2/books/{book_id}/"
    headers = {"Authorization": f"Token {api_token}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        book_data = response.json()
        author = book_data.get("author", "Unknown Author")
        return book_data["title"], book_data.get("source_url", "#"), author, book_data.get("category", "Unknown")
    else:
        print(f"Error fetching book details: {response.status_code}")
        return "Unknown Book", "#", "Unknown Author", "Unknown"


def fetch_highlights(api_token, updated_after):
    url = "https://readwise.io/api/v2/highlights/"
    headers = {"Authorization": f"Token {api_token}"}
    params = {"updated_after": updated_after.isoformat()}

    print(f"API Request for Highlights after: {updated_after.isoformat()}")

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"Error fetching highlights: {response.status_code}")
        return None, None

    highlights_data = response.json()
    all_highlights = highlights_data["results"]
    book_highlights = defaultdict(list)
    book_details = {}

    for highlight in all_highlights:
        highlighted_at = highlight.get('highlighted_at')
        if highlighted_at:  # Check if 'highlighted_at' is not None
            highlight_date = parse(highlighted_at)
            if highlight_date > updated_after:  # Filtering by date
                book_id = highlight["book_id"]
                if book_id not in book_details:
                    # Fetch book details if not already fetched
                    title, source_url, author, category = fetch_book_details(api_token, book_id)
                    book_details[book_id] = (title, source_url, author, category)

                # Add highlight to the respective book's list
                book_highlights[book_id].append(highlight)

    # Sort highlights in each book by 'highlighted_at' in reverse chronological order
    for book_id in book_highlights:
        book_highlights[book_id].sort(key=lambda x: parse(x['highlighted_at']), reverse=True)

    return book_highlights, book_details

def convert_markdown_to_html(text):
    # Convert Markdown links to HTML links
    markdown_link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    text = re.sub(markdown_link_pattern, r'<a href="\2">\1</a>', text)

    # Convert Markdown bold (**text**) to HTML bold
    markdown_bold_pattern = r"\*\*(.*?)\*\*"
    text = re.sub(markdown_bold_pattern, r'<b>\1</b>', text)

    return text

def create_wordpress_post(book_title, content):
    credentials = base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode('utf-8')).decode('utf-8')
    headers = {
        'Authorization': f'Basic {credentials}',
        'Content-Type': 'application/json'
    }
    data = {
        "title": f"Read: {book_title}",  # Using book title instead of date
        "content": content,
        "status": "draft",
        "categories": [CATEGORY_ID]
    }

    response = requests.post(WP_ENDPOINT, headers=headers, json=data)

    if response.status_code != 201:
        print(f"Error creating post for {book_title}: HTTP {response.status_code}")
        print(f"Response Body: {response.text}")
    else:
        print(f"Post created successfully for {book_title}. Post ID: {response.json().get('id')}")

    return response.status_code

def main():
    last_run_date_str = get_last_run_date()
    last_run_datetime = datetime.fromisoformat(last_run_date_str)
    updated_after = get_start_date_for_highlights(last_run_datetime)

    print(f"Running script for highlights updated after: {updated_after.isoformat()}")

    book_highlights, book_details = fetch_highlights(API_TOKEN, updated_after)  # Ensure correct assignment

    if book_highlights:
            for book_id, highlights in book_highlights.items():
                post_content = ""
                # Process each highlight and add to post content
                for highlight in highlights:
                    text = html.unescape(highlight["text"])
                    text = convert_markdown_to_html(text)
                    note = highlight.get('note', '').strip()
                    post_content += f"<!-- wp:quote --><blockquote class=\"wp-block-quote\"><!-- wp:paragraph -->{text}<!-- /wp:paragraph --></blockquote><!-- /wp:quote -->"
                    if note:
                        note_html = convert_markdown_to_html(html.unescape(note))
                        post_content += f"<!-- wp:paragraph --><p>Note: {note_html}</p><!-- /wp:paragraph -->"

                # Add book information at the end
                title, source_url, author, _ = book_details[book_id]
                title_author = f"{title} - {author}" if author != "Unknown Author" else title
                if "mailto" in source_url:
                    search_query = f"{title} {author} newsletter -site:www.jimwillis.org".replace(' ', '+')
                    source_url = f"https://duckduckgo.com/?q={search_query}"
                post_content += f"<!-- wp:heading {{\"level\":4}} --><h4>Source: <a href=\"{source_url}\">{title_author}</a></h4><!-- /wp:heading -->"

                # Create WordPress post
                if post_content:
                    status = create_wordpress_post(title, post_content)
                    if status != 201:
                        print(f"Error creating post for book {title}: HTTP {status}")
    
    update_last_run_date()

if __name__ == "__main__":
    main()
