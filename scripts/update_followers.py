#!/usr/bin/env python3
"""Update the README note and the follower section on the thank-you page."""

from concurrent.futures import ThreadPoolExecutor
from html import escape
import json
import os
import re
from urllib.parse import quote
import urllib.error
import urllib.request


GITHUB_USER = "NhanAZ"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(ROOT_DIR, "README.md")
PAGE_PATH = os.path.join(ROOT_DIR, "docs", "index.html")
MARKERS_START = "<!-- FOLLOWERS-START -->"
MARKERS_END = "<!-- FOLLOWERS-END -->"
PER_PAGE = 100


def github_json(url: str, token: str | None = None) -> dict | list:
    """Fetch JSON from GitHub's public API."""
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", f"{GITHUB_USER}-readme-updater")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GitHub API request failed with HTTP {error.code}") from error
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError("Could not read follower data from GitHub") from error


def fetch_all_followers(username: str, token: str | None = None) -> list[dict]:
    """Fetch every follower without relying on the API's display order."""
    followers = []
    page = 1

    while True:
        data = github_json(
            f"https://api.github.com/users/{quote(username)}/followers"
            f"?per_page={PER_PAGE}&page={page}",
            token,
        )
        if not isinstance(data, list):
            raise RuntimeError("GitHub returned an invalid followers response")

        followers.extend(data)
        if len(data) < PER_PAGE:
            break
        page += 1

    return followers


def fallback_profile(follower: dict) -> dict:
    """Keep the useful fields available from the followers endpoint."""
    login = str(follower.get("login", ""))
    return {
        "login": login,
        "name": login,
        "avatar_url": str(follower.get("avatar_url", "")),
        "html_url": str(follower.get("html_url", f"https://github.com/{login}")),
    }


def fetch_profile(follower: dict, token: str | None) -> dict:
    """Add the person's public display name when an API token is available."""
    profile = fallback_profile(follower)
    if not token or not profile["login"]:
        return profile

    try:
        data = github_json(
            f"https://api.github.com/users/{quote(profile['login'])}",
            token,
        )
    except RuntimeError:
        return profile

    if not isinstance(data, dict):
        return profile

    profile["name"] = str(data.get("name") or profile["login"])
    profile["avatar_url"] = str(data.get("avatar_url") or profile["avatar_url"])
    profile["html_url"] = str(data.get("html_url") or profile["html_url"])
    return profile


def enrich_followers(followers: list[dict], token: str | None) -> list[dict]:
    """Fetch display names in parallel while keeping API failures non-fatal."""
    if not token:
        return [fallback_profile(follower) for follower in followers]

    with ThreadPoolExecutor(max_workers=8) as executor:
        return list(executor.map(lambda item: fetch_profile(item, token), followers))


def generate_people_section(followers: list[dict]) -> str:
    """Render a calm, responsive grid of follower names, usernames, and avatars."""
    people = sorted(
        followers,
        key=lambda person: (person["name"].casefold(), person["login"].casefold()),
    )
    cards = []

    for index, person in enumerate(people):
        name = escape(person["name"] or person["login"])
        login = escape(person["login"])
        avatar_url = escape(person["avatar_url"], quote=True)
        profile_url = escape(person["html_url"], quote=True)
        cards.append(
            "  <a class=\"person-card\" href=\"{profile_url}\" "
            "target=\"_blank\" rel=\"noreferrer\" style=\"--index: {index}\">\n"
            "    <img src=\"{avatar_url}\" alt=\"{name} (@{login})\" "
            "width=\"56\" height=\"56\" loading=\"lazy\" />\n"
            "    <span class=\"person-meta\">\n"
            "      <strong>{name}</strong>\n"
            "      <span>@{login}</span>\n"
            "    </span>\n"
            "  </a>".format(
                profile_url=profile_url,
                index=index,
                avatar_url=avatar_url,
                name=name,
                login=login,
            )
        )

    cards_markup = "\n".join(cards)
    return (
        f"{MARKERS_START}\n"
        "<section class=\"quiet-stat\" aria-label=\"Follower count\" data-reveal>\n"
        "  <span class=\"stat-label\">At this point</span>\n"
        "  <span class=\"stat-number\">" + str(len(people)) + "</span>\n"
        "  <span class=\"stat-description\">people have chosen to keep an eye on the work, and I am quietly grateful that these small things found a place in their day.</span>\n"
        "</section>\n\n"
        "<section class=\"people-section\" aria-labelledby=\"people-title\">\n"
        "  <div class=\"section-heading\" data-reveal>\n"
        "    <p class=\"eyebrow\">The people</p>\n"
        "    <h2 id=\"people-title\">Every name here means the work found a little more room in the world.</h2>\n"
        "    <p>There is no ranking and no ceremony. Just the names of people who chose to keep an eye on what I make.</p>\n"
        "  </div>\n"
        "  <p class=\"people-count\" data-reveal><strong>" + str(len(people)) + "</strong> people, each with a place of their own.</p>\n"
        "  <div class=\"people-grid\">\n"
        f"{cards_markup}\n"
        "  </div>\n"
        "</section>\n"
        f"{MARKERS_END}"
    )


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


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    raw_followers = fetch_all_followers(GITHUB_USER, token)
    followers = enrich_followers(raw_followers, token)
    count = len(followers)

    readme_block = (
        f"{MARKERS_START}\n"
        f"**{count} followers.** Thank you for taking the time to follow the work. [A note of thanks →](https://nhanaz.github.io/NhanAZ/)\n"
        f"{MARKERS_END}"
    )
    changed_readme = update_file(README_PATH, readme_block)
    changed_page = update_file(PAGE_PATH, generate_people_section(followers))

    if changed_readme or changed_page:
        print(f"Updated README.md and the thank-you page with {count} followers.")
    else:
        print("Follower data is already up to date.")


if __name__ == "__main__":
    main()
