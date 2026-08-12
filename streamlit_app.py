from bs4 import BeautifulSoup
import pandas as pd
import requests
import streamlit as st


@st.cache_data(ttl=3600)
def load_u14_rankings():
  """Fetches and processes the U14 master ranking excel file from GitHub."""
  excel_url = (
      "https://raw.githubusercontent.com/bosanac-exe/ota-gu14/main/master.xlsx"
  )
  try:
    # Read all sheets from the Excel file
    excel_file = pd.ExcelFile(excel_url)
    sheet_names = excel_file.sheet_names

    if not sheet_names:
      return None, "No sheets found in the ranking file."

    # Assume the sheets are named or can be sorted to find the most recent weekly sheet
    # Sorting sheet names chronologically or taking the last sheet as the most recent week
    latest_sheet = sorted(sheet_names)[-1]

    # Load the latest sheet. Adjust column names below based on your actual Excel file layout
    df_rankings = pd.read_excel(excel_file, sheet_name=latest_sheet)
    return df_rankings, latest_sheet
  except Exception as e:
    return None, str(e)


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

    # 1. Extract Tournament Title
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

    # 4. Extract Age Group
    h3_elements = soup.find_all("h3")
    age_group_text = "Age group not found"
    for h3 in h3_elements:
      text = h3.get_text(strip=True)
      if text and text.lower() != "get link":
        age_group_text = text
        break
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
          players.append(
              {"Player Name": player_name, "Registration Status": status}
          )

    data["players"] = players

  except Exception as e:
    data["error"] = str(e)

  return data


# --- Styling function for Pandas DataFrame ---
def style_player_status(row):
  """Applies background colors based on registration status."""
  status = str(row["Registration Status"]).lower()
  if "maindraw" in status:
    return ["background-color: #d4edda; color: #155724"] * len(row)
  elif "reserve" in status:
    return ["background-color: #fff3cd; color: #856404"] * len(row)
  return [""] * len(row)


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
    # Load U14 Rankings beforehand
    rankings_df, sheet_info = load_u14_rankings()

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
    if rankings_df is not None:
      st.info(
          f"Successfully matched rankings from U14 latest weekly sheet:"
          f" **{sheet_info}**"
      )
    else:
      st.warning(
          f"Could not load U14 ranking file: {sheet_info}. Displaying players"
          " without rankings."
      )

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

        st.subheader("Registered Players & Rankings")

        players = data.get("players", [])
        if not players:
          st.info(
              "No player data could be parsed from this page. Please check the"
              " URL format."
          )
        else:
          df = pd.DataFrame(players)

          # Merge rankings if the rankings sheet loaded successfully
          if rankings_df is not None:
            # Assuming columns in master.xlsx are named 'Player Name' and 'Ranking'.
            # Adjust these string keys if your excel columns differ (e.g., 'Name', 'Rank')
            if (
                "Player Name" in rankings_df.columns
                and "Ranking" in rankings_df.columns
            ):
              df = pd.merge(df, rankings_df, on="Player Name", how="left")
              df["Ranking"] = df["Ranking"].fillna(
                  "N/A"
              )  # Fallback if player not found in weekly list
            else:
              df["Ranking"] = "Col mismatch"
          else:
            df["Ranking"] = "Unavailable"

          # Reorder columns to look clean: Player Name, Ranking, Registration Status
          if "Ranking" in df.columns:
            df = df[["Player Name", "Ranking", "Registration Status"]]

          # Apply Pandas styling for main draw (green) vs reserves (yellow)
          styled_df = df.style.apply(style_player_status, axis=1)

          table_height = (len(df) + 1) * 35 + 10

          st.dataframe(
              styled_df,
              use_container_width=True,
              hide_index=True,
              height=table_height,
          )
