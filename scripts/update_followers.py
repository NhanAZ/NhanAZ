#!/usr/bin/env python3
"""Update follower records and render the current and former follower sections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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
HISTORY_PATH = os.path.join(ROOT_DIR, "data", "followers-history.json")
MARKERS_START = "<!-- FOLLOWERS-START -->"
MARKERS_END = "<!-- FOLLOWERS-END -->"
PER_PAGE = 100
VIETNAM_TIMEZONE = timezone(timedelta(hours=7))


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


def fetch_following_logins(username: str, token: str | None = None) -> set[str]:
    """Fetch the accounts this user follows for mutual-follow detection."""
    following = set()
    page = 1

    while True:
        data = github_json(
            f"https://api.github.com/users/{quote(username)}/following"
            f"?per_page={PER_PAGE}&page={page}",
            token,
        )
        if not isinstance(data, list):
            raise RuntimeError("GitHub returned an invalid following response")

        following.update(
            str(person.get("login", "")).casefold()
            for person in data
            if person.get("login")
        )
        if len(data) < PER_PAGE:
            break
        page += 1

    return following


def numeric_github_id(value: object) -> int:
    """Return a stable numeric GitHub ID when the API provides one."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def fallback_profile(follower: dict, following_logins: set[str]) -> dict:
    """Keep useful fields available from the followers endpoint."""
    login = str(follower.get("login", ""))
    return {
        "github_id": numeric_github_id(follower.get("id")),
        "login": login,
        "name": login,
        "avatar_url": str(follower.get("avatar_url", "")),
        "html_url": str(follower.get("html_url", f"https://github.com/{login}")),
        "is_mutual": login.casefold() in following_logins,
    }


def fetch_profile(follower: dict, token: str | None, following_logins: set[str]) -> dict:
    """Add the person's public display name when an API token is available."""
    profile = fallback_profile(follower, following_logins)
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

    profile["github_id"] = numeric_github_id(data.get("id") or profile["github_id"])
    profile["name"] = str(data.get("name") or profile["login"])
    profile["avatar_url"] = str(data.get("avatar_url") or profile["avatar_url"])
    profile["html_url"] = str(data.get("html_url") or profile["html_url"])
    return profile


def enrich_followers(
    followers: list[dict], token: str | None, following_logins: set[str]
) -> list[dict]:
    """Fetch display names in parallel while keeping API failures non-fatal."""
    if not token:
        return [fallback_profile(follower, following_logins) for follower in followers]

    with ThreadPoolExecutor(max_workers=8) as executor:
        return list(
            executor.map(
                lambda item: fetch_profile(item, token, following_logins),
                followers,
            )
        )


def person_key(person: dict) -> str:
    """Identify a person by GitHub ID, with login as a safe fallback."""
    github_id = numeric_github_id(person.get("github_id"))
    if github_id:
        return f"id:{github_id}"
    return f"login:{str(person.get('login', '')).casefold()}"


def load_history() -> dict:
    """Load the append-only follower history, or start a new archive."""
    if not os.path.exists(HISTORY_PATH):
        return {
            "schema_version": 1,
            "updated_at": None,
            "snapshots": [],
            "people": [],
        }

    with open(HISTORY_PATH, "r", encoding="utf-8") as file:
        history = json.load(file)

    if not isinstance(history, dict):
        raise RuntimeError("Follower history must be a JSON object")

    history.setdefault("schema_version", 1)
    history.setdefault("updated_at", None)
    history.setdefault("snapshots", [])
    history.setdefault("people", [])
    return history


def save_history(history: dict) -> bool:
    """Persist the follower archive without removing historical people."""
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    new_content = json.dumps(history, ensure_ascii=False, indent=2) + "\n"
    old_content = ""

    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as file:
            old_content = file.read()

    if new_content == old_content:
        return False

    with open(HISTORY_PATH, "w", encoding="utf-8") as file:
        file.write(new_content)
    return True


def update_history(history: dict, current_followers: list[dict], snapshot_date: str) -> list[dict]:
    """Merge a changed follower snapshot while keeping former followers."""
    people = history.get("people", [])
    people_by_key = {person_key(person): person for person in people}
    is_initial_snapshot = not people_by_key
    current_by_key = {person_key(person): person for person in current_followers}
    snapshots = history.get("snapshots", [])
    latest_snapshot = snapshots[-1] if snapshots else None
    previous_ids = {
        numeric_github_id(github_id)
        for github_id in (latest_snapshot or {}).get("github_ids", [])
        if numeric_github_id(github_id)
    }
    current_ids = {
        numeric_github_id(follower.get("github_id"))
        for follower in current_followers
        if numeric_github_id(follower.get("github_id"))
    }
    membership_changed = latest_snapshot is None or current_ids != previous_ids

    for follower in current_followers:
        key = person_key(follower)
        person = people_by_key.get(key)
        if person is None:
            person = {
                "github_id": numeric_github_id(follower.get("github_id")),
                "login": follower["login"],
                "name": follower["name"],
                "avatar_url": follower["avatar_url"],
                "html_url": follower["html_url"],
                "first_seen_at": None if is_initial_snapshot else snapshot_date,
                "last_seen_at": snapshot_date,
            }
            people.append(person)
            people_by_key[key] = person
        else:
            person.update(
                {
                    "github_id": numeric_github_id(follower.get("github_id")),
                    "login": follower["login"],
                    "name": follower["name"],
                    "avatar_url": follower["avatar_url"],
                    "html_url": follower["html_url"],
                }
            )
            if membership_changed:
                person["last_seen_at"] = snapshot_date

    if membership_changed:
        snapshot = {
            "date": snapshot_date,
            "github_ids": sorted(current_ids),
        }
        history["snapshots"] = [
            item for item in snapshots if item.get("date") != snapshot_date
        ]
        history["snapshots"].append(snapshot)
        history["updated_at"] = snapshot_date
    history["people"] = people

    rendered_people = []
    for person in people:
        current = current_by_key.get(person_key(person))
        rendered_person = dict(person)
        rendered_person["is_current"] = current is not None
        rendered_person["is_mutual"] = bool(current and current.get("is_mutual", False))
        rendered_people.append(rendered_person)

    return rendered_people


def render_person_card(person: dict, index: int, is_former: bool = False) -> str:
    """Render one person card with stable ID and first-recorded date."""
    name = escape(person["name"] or person["login"])
    login = escape(person["login"])
    avatar_url = escape(person["avatar_url"], quote=True)
    profile_url = escape(person["html_url"], quote=True)
    is_mutual = person.get("is_mutual", False) and not is_former
    classes = ["person-card"]
    attributes = []

    if is_mutual:
        classes.append("is-mutual")
        attributes.extend(['data-mutual="true"', 'title="Follows you back"'])
    if is_former:
        classes.append("is-former")
        attributes.extend(['data-former="true"', 'title="Once followed this journey"'])

    attribute_text = " " + " ".join(attributes) if attributes else ""
    return (
        "  <div class=\"{classes}\"{attributes} data-profile-url=\"{profile_url}\" style=\"--index: {index}\">\n"
        "    <img src=\"{avatar_url}\" alt=\"{name} (@{login})\" "
        "width=\"56\" height=\"56\" loading=\"lazy\" />\n"
        "    <span class=\"person-meta\">\n"
        "      <strong>{name}</strong>\n"
        "      <a class=\"person-username\" href=\"{profile_url}\" "
        "target=\"_blank\" rel=\"noreferrer\">@{login}</a>\n"
        "    </span>\n"
        "  </div>".format(
            classes=" ".join(classes),
            attributes=attribute_text,
            profile_url=profile_url,
            index=index,
            avatar_url=avatar_url,
            name=name,
            login=login,
        )
    )


def generate_people_section(people: list[dict]) -> str:
    """Render current and former followers without discarding history."""
    current_people = [person for person in people if person.get("is_current", False)]
    former_people = [person for person in people if not person.get("is_current", False)]
    mutual_people = [person for person in current_people if person.get("is_mutual", False)]
    other_people = [person for person in current_people if not person.get("is_mutual", False)]
    current_cards = "\n".join(
        render_person_card(person, index)
        for index, person in enumerate(mutual_people + other_people)
    )
    former_cards = "\n".join(
        render_person_card(person, index, is_former=True)
        for index, person in enumerate(former_people)
    )
    former_section = ""

    if former_people:
        former_section = (
            "\n\n"
            "<section class=\"people-section former-people-section\" aria-labelledby=\"former-people-title\">\n"
            "  <div class=\"section-heading\" data-reveal>\n"
            "    <p class=\"eyebrow\">Those who were here</p>\n"
            "    <h2 id=\"former-people-title\">Some paths meet briefly, yet still leave a mark.</h2>\n"
            "    <p>These are the people who once followed this journey. Even when a path changes direction, I remain sincerely grateful for the time it shared with mine.</p>\n"
            "  </div>\n"
            "  <p class=\"people-count\" data-reveal><strong>"
            + str(len(former_people))
            + "</strong> people were once part of this journey.</p>\n"
            "  <div class=\"people-grid former-people-grid\">\n"
            f"{former_cards}\n"
            "  </div>\n"
            "</section>"
        )

    current_count = len(current_people)
    return (
        f"{MARKERS_START}\n"
        "<section class=\"quiet-stat\" aria-label=\"Follower count\" data-reveal>\n"
        "  <span class=\"stat-label\">At this point</span>\n"
        "  <span class=\"stat-number\">" + str(current_count) + "</span>\n"
        "  <span class=\"stat-description\">people have chosen to follow this journey, and each one gives me reason to continue.</span>\n"
        "</section>\n\n"
        "<section class=\"people-section\" aria-labelledby=\"people-title\">\n"
        "  <div class=\"section-heading\" data-reveal>\n"
        "    <p class=\"eyebrow\">The people</p>\n"
        "    <h2 id=\"people-title\">Every name here marks a moment when this journey reached another person.</h2>\n"
        "    <p>Some of you have been here for a while. Some have only just arrived. To every one of you, thank you for making room for this journey in your day.</p>\n"
        "  </div>\n"
        "  <p class=\"people-count\" data-reveal><strong>" + str(current_count) + "</strong> people have given this journey a place in their day.</p>\n"
        "  <div class=\"people-grid current-people-grid\">\n"
        f"{current_cards}\n"
        "  </div>\n"
        "</section>"
        f"{former_section}\n"
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
    snapshot_date = datetime.now(VIETNAM_TIMEZONE).date().isoformat()
    raw_followers = fetch_all_followers(GITHUB_USER, token)
    try:
        following_logins = fetch_following_logins(GITHUB_USER, token)
    except RuntimeError:
        following_logins = set()
    followers = enrich_followers(raw_followers, token, following_logins)
    history = load_history()
    people = update_history(history, followers, snapshot_date)
    changed_history = save_history(history)
    count = len(followers)

    readme_block = (
        f"{MARKERS_START}\n"
        f"**{count} followers.** Thank you for choosing to follow the journey. [A note of gratitude →](https://nhanaz.github.io/NhanAZ/)\n"
        f"{MARKERS_END}"
    )
    changed_readme = update_file(README_PATH, readme_block)
    changed_page = update_file(PAGE_PATH, generate_people_section(people))

    if changed_readme or changed_page or changed_history:
        print(f"Updated the follower archive and thank-you page with {count} current followers.")
    else:
        print("Follower data is already up to date.")


if __name__ == "__main__":
    main()
