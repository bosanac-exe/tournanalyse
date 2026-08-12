from bs4 import BeautifulSoup
import io
import pandas as pd
import re
import requests
import streamlit as st


@st.cache_data(ttl=3600)
def load_u14_rankings():
  """Fetches the public U14 master ranking excel file from GitHub."""
  excel_url = (
      "https://raw.githubusercontent.com/bosanac-exe/ota-gu14/main/master.xlsx"
  )
  try:
    excel_file = pd.ExcelFile(excel_url)
    sheet_names = excel_file.sheet_names
    if not sheet_names:
      return None, "No sheets found in U14 file."
    latest_sheet = sorted(sheet_names)[-1]
    df_rankings = pd.read_excel(excel_file, sheet_name=latest_sheet)
    return df_rankings, latest_sheet
  except Exception as e:
    return None, str(e)


@st.cache_data(ttl=3600)
def load_u12_rankings():
  """Fetches the private U12 master ranking excel file from GitHub using a PAT,

  ignoring 'trends' sheets and matching weekly formats like 'Week NN-YYYY'.
  """
  api_url = (
      "https://raw.githubusercontent.com/bosanac-exe/rankdataparse/main/master.xlsx"
  )

  token = st.secrets.get("GITHUB_PAT", "")
  headers = {}
  if token:
    headers["Authorization"] = f"token {token}"

  try:
    response = requests.get(api_url, headers=headers, timeout=15)
    response.raise_for_status()

    excel_file = pd.ExcelFile(io.BytesIO(response.content))
    sheet_names = excel_file.sheet_names

    if not sheet_names:
      return None, "No sheets found in U12 file."

    valid_sheets = []
    pattern = re.compile(r"^week\s*(\d+)-(\d{4})$", re.IGNORECASE)

    for sheet in sheet_names:
      if sheet.strip().lower() == "trends":
        continue
      match = pattern.match(sheet.strip())
      if match:
        week_num = int(match.group(1))
        year = int(match.group(2))
        valid_sheets.append((year, week_num, sheet))

    if not valid_sheets:
      return None, "No valid weekly sheets (Week NN-YYYY) found."

    valid_sheets.sort(key=lambda x: (x[0], x[1]))
    latest_sheet_name = valid_sheets[-1][2]

    df_rankings = pd.read_excel(excel_file, sheet_name=latest_sheet_name)
    return df_rankings, latest_sheet_name
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

    time_elems = soup.find_all("time")
    if len(time_elems) >= 2:
      start_date = time_elems[0].get_text(strip=True)
      end_date = time_elems[1].get_text(strip=True)
      data["date"] = f"{start_date} to {end_date}"
    else:
      data["date"] = "Date not found"

    star_elem = soup.find("span", class_="tag-duo__title")
    data["star_level"] = (
        star_elem.get_text(strip=True) if star_elem else "Star level not found"
    )

    h3_elements = soup.find_all("h3")
    age_group_text = "Age group not found"
    for h3 in h3_elements:
      text = h3.get_text(strip=True)
      if text and text.lower() != "get link":
        age_group_text = text
        break
    data["age_group"] = age_group_text

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


def style_player_status(row):
  """Applies background colors based on registration status."""
  status = str(row["Registration Status"]).lower()
  if "maindraw" in status:
    return ["background-color: #d4edda; color: #155724"] * len(row)
  elif "reserve" in status:
    return ["background-color: #fff3cd; color: #856404"] * len(row)
  return [""] * len(row)


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
    u14_df, u14_sheet = load_u14_rankings()
    u12_df, u12_sheet = load_u12_rankings()

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
          age_group = data.get("age_group", "").upper()

          if "12" in age_group:
            active_rankings = u12_df
            sheet_name = u12_sheet
            category_label = "U12"
          else:
            active_rankings = u14_df
            sheet_name = u14_sheet
            category_label = "U14"

          if active_rankings is not None:
            if (
                "Player" in active_rankings.columns
                and "Rank" in active_rankings.columns
            ):
              df = pd.merge(
                  df,
                  active_rankings[["Player", "Rank"]],
                  left_on="Player Name",
                  right_on="Player",
                  how="left",
              )
              if "Player" in df.columns:
                df = df.drop(columns=["Player"])
              df["Rank"] = df["Rank"].fillna("N/A")
              st.caption(
                  f"Matched using {category_label} rankings (Sheet:"
                  f" {sheet_name})"
              )
            else:
              df["Rank"] = "Columns missing"
          else:
            df["Rank"] = "Unavailable"

          if "Rank" in df.columns:
            df = df[["Player Name", "Rank", "Registration Status"]]

          styled_df = df.style.apply(style_player_status, axis=1)
          table_height = (len(df) + 1) * 35 + 10

          # Use a narrower container layout column so the table shrinks to content size
          table_col, _ = st.columns([1, 2])
          with table_col:
            st.dataframe(
                styled_df,
                use_container_width=False,
                hide_index=True,
                height=table_height,
                column_config={
                    "Player Name": st.column_config.TextColumn(
                        "Player Name", width="small"
                    ),
                    "Rank": st.column_config.TextColumn("Rank", width="small"),
                    "Registration Status": st.column_config.TextColumn(
                        "Registration Status", width="small"
                    ),
                },
            )
