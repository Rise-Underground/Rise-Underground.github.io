r"""
post_to_x.py -- posts the composed POA tracker image + caption to X.

This version always posts for real. There is no dry run and no
confirmation prompt -- it runs straight through, so it can be scheduled
unattended (e.g. via Task Scheduler) without anything hanging waiting
for input.

Setup (one-time):
1. pip install tweepy
2. Create a file OUTSIDE your GitHub repo folder, e.g.:
     C:\Users\19782\Desktop\RISE_Scripts\.env
   with these four lines (use your real values from API.txt):
     CONSUMER_KEY=...
     CONSUMER_SECRET=...
     ACCESS_TOKEN=...
     ACCESS_TOKEN_SECRET=...
3. Confirm ENV_PATH and IMAGE_PATH below match your actual folder locations.

Usage:
  python post_to_x.py
"""

import os
import sys

# ---- EDIT THESE TWO PATHS FOR YOUR MACHINE ----
ENV_PATH = r"C:\Users\19782\Desktop\RISE_Scripts\.env"
IMAGE_PATH = r"C:\Users\19782\Desktop\Rise-Underground.github.io\NFT_Data\POA_x_post_image.png"
# ------------------------------------------------

CAPTION = """\U0001F624 Tired of pulling Commons and Uncommons every mint?

Rarity odds on RISE NFTs aren't fixed \u2014 they shift with every mint \U0001F504. As Base \u26D3\uFE0F and Cardano \u26D3\uFE0F mint independently, their odds drift apart, and one chain can end up favoring Mythic \U0001F52E pulls way more than the other at any given moment.

\U0001F3AF Scan, target, and pounce \U0001F406 your way to better odds with the POA Tracker.

\U0001F517 https://rise-underground.github.io/poa_tracker.html"""


def load_credentials(env_path):
    if not os.path.exists(env_path):
        print(f"ERROR: credentials file not found at:\n  {env_path}")
        print("Create it first (see the setup instructions at the top of this script).")
        sys.exit(1)

    creds = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            creds[key.strip()] = value.strip()

    required = ["CONSUMER_KEY", "CONSUMER_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"]
    missing = [k for k in required if k not in creds or not creds[k]]
    if missing:
        print(f"ERROR: missing values in {env_path}: {', '.join(missing)}")
        sys.exit(1)

    return creds


def post(image_path, caption, creds):
    if not os.path.exists(image_path):
        print(f"ERROR: image not found at:\n  {image_path}")
        print("Generate it first using item_picker.html, then try again.")
        sys.exit(1)

    try:
        import tweepy
    except ImportError:
        print("ERROR: tweepy is not installed. Run:  pip install tweepy")
        sys.exit(1)

    # media upload requires the v1.1 API
    auth = tweepy.OAuth1UserHandler(
        creds["CONSUMER_KEY"],
        creds["CONSUMER_SECRET"],
        creds["ACCESS_TOKEN"],
        creds["ACCESS_TOKEN_SECRET"],
    )
    api_v1 = tweepy.API(auth)

    # posting the tweet itself uses the v2 API
    client_v2 = tweepy.Client(
        consumer_key=creds["CONSUMER_KEY"],
        consumer_secret=creds["CONSUMER_SECRET"],
        access_token=creds["ACCESS_TOKEN"],
        access_token_secret=creds["ACCESS_TOKEN_SECRET"],
    )

    print("Uploading image...")
    media = api_v1.media_upload(image_path)

    print("Posting tweet...")
    response = client_v2.create_tweet(text=caption, media_ids=[media.media_id])

    print("Posted successfully.")
    print(response)


def main():
    creds = load_credentials(ENV_PATH)
    post(IMAGE_PATH, CAPTION, creds)


if __name__ == "__main__":
    main()
