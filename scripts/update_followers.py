#!/usr/bin/env python3
"""Update the follower count in README.md and the thank-you page."""

import json
import os
import re
import urllib.error
import urllib.request


GITHUB_USER = "NhanAZ"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(ROOT_DIR, "README.md")
PAGE_PATH = os.path.join(ROOT_DIR, "docs", "index.html")
MARKERS_START = "<!-- FOLLOWERS-START -->"
MARKERS_END = "<!-- FOLLOWERS-END -->"


def fetch_follower_count(username: str, token: str | None = None) -> int:
    """Fetch the public follower count for a GitHub user."""
    request = urllib.request.Request(f"https://api.github.com/users/{username}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", f"{username}-readme-updater")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GitHub API request failed with HTTP {error.code}") from error
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError("Could not read the follower count from GitHub") from error

    try:
        count = int(data["followers"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("GitHub returned an invalid follower count") from error

    if count < 0:
        raise RuntimeError("GitHub returned a negative follower count")

    return count


def update_file(path: str, replacement: str) -> bool:
    """Replace one generated marker block in a UTF-8 text file."""
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()

    pattern = re.compile(
        re.escape(MARKERS_START) + r".*?" + re.escape(MARKERS_END),
        re.DOTALL,
    )
    if not pattern.search(content):
        raise RuntimeError(f"Follower markers were not found in {path}")

    updated_content = pattern.sub(replacement, content, count=1)
    if updated_content == content:
        return False

    with open(path, "w", encoding="utf-8") as file:
        file.write(updated_content)
    return True


def update_follower_count(follower_count: int) -> bool:
    """Update both public copies of the follower count."""
    readme_block = (
        f"{MARKERS_START}\n"
        f"**{follower_count} people** are following along. Thanks for being here.\n"
        f"{MARKERS_END}"
    )
    page_block = (
        f"{MARKERS_START}\n"
        f'<span class="follower-count">{follower_count}</span>\n'
        f"{MARKERS_END}"
    )

    changed = update_file(README_PATH, readme_block)
    changed = update_file(PAGE_PATH, page_block) or changed
    return changed


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    follower_count = fetch_follower_count(GITHUB_USER, token)

    if update_follower_count(follower_count):
        print(f"Updated README.md and the thank-you page with {follower_count} followers.")
    else:
        print("Follower count is already up to date.")


if __name__ == "__main__":
    main()
