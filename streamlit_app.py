from bs4 import BeautifulSoup
import requests
import streamlit as st


def scrape_tournament_data(url):
  """Scrapes tournament details and player lists using requests and BeautifulSoup."""
  data = {}
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # 1. Extract Tournament Title (Checks h2 with media__title or span with nav-link__value)
    title_elem = soup.find("h2", class_="media__title")
    if title_elem and title_elem.has_attr("title"):
      data["title"] = title_elem["title"]
    else:
      inner_title = soup.find("span", class_="nav-link__value")
      data["title"] = (
          inner_title.get_text(strip=True)
          if inner_title
          else "Unknown Tournament"
      )

    # 2. Extract Tournament Dates
    time_elems = soup.find_all("time")
    if len(time_elems) >= 2:
      start_date = time_elems[0].get_text(strip=True)
      end_date = time_elems[1].get_text(strip=True)
      data["date"] = f"{start_date} to {end_date}"
    else:
      data["date"] = "Date not found"

    # 3. Extract Star Level
    star_elem = soup.find("span", class_="tag-duo__title")
    data["star_level"] = (
        star_elem.get_text(strip=True) if star_elem else "Star level not found"
    )

    # 4. Extract Age Group (Find all h3 elements, skip utility texts like 'Get link', and pick the correct one)
    h3_elements = soup.find_all("h3")
    age_group_text = "Age group not found"
    for h3 in h3_elements:
      text = h3.get_text(strip=True)
      if text and text.lower() != "get link":
        age_group_text = text
        break  # Typically the target tournament event category comes up right after utility headers
    data["age_group"] = age_group_text

    # 5. Extract Registered Players Table
    players = []
    rows = soup.select("tbody tr") or soup.find_all("tr")
    for row in rows:
      cols = row.find_all("td")
      if len(cols) >= 2:
        status = cols[0].get_text(strip=True)
        player_name_elem = cols[1].find("a")
        player_name = (
            player_name_elem.get_text(strip=True)
            if player_name_elem
            else cols[1].get_text(strip=True)
        )

        if status and player_name and "player.aspx" in str(cols[1]):
          players.append({"name": player_name, "status": status})

    data["players"] = players

  except Exception as e:
    data["error"] = str(e)

  return data


# --- Streamlit UI Setup ---
st.set_page_config(
    page_title="Tournament Draw Scraper", page_icon="🎾", layout="wide"
)

st.title("🎾 Tournament Draw & Player Status Scraper")
st.markdown(
    "Paste your tournament URLs below (maximum **10 URLs**, each on a new line)"
    " and click **Retrieve Data**."
)

urls_input = st.text_area(
    "Tournament URLs",
    placeholder=(
        "https://ota.tournamentsoftware.com/sport/event.aspx?id=...&event=...\nhttps://ota.tournamentsoftware.com/sport/event.aspx?id=...&event=..."
    ),
    height=150,
)

if st.button("Retrieve Data", type="primary"):
  urls = [
      line.strip() for line in urls_input.split("\n") if line.strip()
  ]

  if not urls:
    st.warning("Please enter at least one URL.")
  elif len(urls) > 10:
    st.error("Please limit your input to a maximum of 10 URLs.")
  else:
    tournament_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, url in enumerate(urls):
      status_text.text(
          f"Scraping tournament {i+1} of {len(urls)}... Please wait."
      )
      result = scrape_tournament_data(url)
      tournament_results.append((url, result))
      progress_bar.progress((i + 1) / len(urls))

    status_text.empty()
    progress_bar.empty()

    st.success("Data retrieval complete!")
    st.divider()

    # --- Display Results in Tabs ---
    tab_titles = [
        res.get("title", f"Tournament {i+1}")[:25]
        for _, res in tournament_results
    ]
    tabs = st.tabs(tab_titles)

    for tab, (url, data) in zip(tabs, tournament_results):
      with tab:
        if "error" in data:
          st.error(f"Failed to retrieve data from URL: {url}")
          st.code(data["error"])
          continue

        st.header(data["title"])
        col1, col2, col3 = st.columns(3)
        with col1:
          st.metric("📅 Dates", data["date"])
        with col2:
          st.metric("⭐ Star Level", data["star_level"])
        with col3:
          st.metric("🏆 Age Group", data["age_group"])

        st.subheader("Registered Players")

        players = data.get("players", [])
        if not players:
          st.info(
              "No player data could be parsed from this page. Please check the"
              " URL format."
          )
        else:
          for p in players:
            status_lower = p["status"].lower()
            if "maindraw" in status_lower:
              badge_color = "#d4edda"
              text_color = "#155724"
              border_color = "#c3e6cb"
            elif "reserve" in status_lower:
              badge_color = "#fff3cd"
              text_color = "#856404"
              border_color = "#ffeeba"
            else:
              badge_color = "#e2e3e5"
              text_color = "#383d41"
              border_color = "#d6d8db"

            st.markdown(
                f"""
                        <div style="
                            padding: 8px 12px; 
                            margin-bottom: 6px; 
                            border-radius: 6px; 
                            background-color: {badge_color}; 
                            color: {text_color}; 
                            border: 1px solid {border_color};
                            display: flex; 
                            justify-content: space-between;
                            align-items: center;
                        ">
                            <strong>{p['name']}</strong>
                            <span style="font-size: 0.85em; font-weight: bold; text-transform: uppercase;">{p['status']}</span>
                        </div>
                        """,
                unsafe_allow_html=True,
            )
