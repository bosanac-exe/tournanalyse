from bs4 import BeautifulSoup
import google.generativeai as genai
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
    response = requests.get(excel_url, timeout=15)
    response.raise_for_status()
    excel_file = pd.ExcelFile(io.BytesIO(response.content))
    valid_sheets = []
    pattern = re.compile(r"^week\s*(\d+)-(\d{4})$", re.IGNORECASE)

    for sheet in excel_file.sheet_names:
      if sheet.strip().lower() == "trends":
        continue
      match = pattern.match(sheet.strip())
      if match:
        valid_sheets.append((int(match.group(2)), int(match.group(1)), sheet))

    if not valid_sheets:
      return None, "No valid weekly sheets found."
    valid_sheets.sort(key=lambda x: (x[0], x[1]))
    latest_sheet_name = valid_sheets[-1][2]
    return pd.read_excel(excel_file, sheet_name=latest_sheet_name), latest_sheet_name
  except Exception as e:
    return None, str(e)


@st.cache_data(ttl=3600)
def load_u12_rankings():
  """Fetches the private U12 master ranking excel file from GitHub using a PAT."""
  api_url = (
      "https://raw.githubusercontent.com/bosanac-exe/rankdataparse/main/master.xlsx"
  )
  token = st.secrets.get("GITHUB_PAT", "")
  headers = {"Authorization": f"token {token}"} if token else {}

  try:
    response = requests.get(api_url, headers=headers, timeout=15)
    response.raise_for_status()
    excel_file = pd.ExcelFile(io.BytesIO(response.content))
    valid_sheets = []
    pattern = re.compile(r"^week\s*(\d+)-(\d{4})$", re.IGNORECASE)

    for sheet in excel_file.sheet_names:
      if sheet.strip().lower() == "trends":
        continue
      match = pattern.match(sheet.strip())
      if match:
        valid_sheets.append((int(match.group(2)), int(match.group(1)), sheet))

    if not valid_sheets:
      return None, "No valid weekly sheets found."
    valid_sheets.sort(key=lambda x: (x[0], x[1]))
    latest_sheet_name = valid_sheets[-1][2]
    return pd.read_excel(excel_file, sheet_name=latest_sheet_name), latest_sheet_name
  except Exception as e:
    return None, str(e)


@st.cache_data(ttl=3600)
def load_points_table():
  """Loads the points.xlsx file from the repository root."""
  points_url = (
      "https://raw.githubusercontent.com/bosanac-exe/tournanalyse/main/points.xlsx"
  )
  try:
    response = requests.get(points_url, timeout=15)
    response.raise_for_status()
    return pd.read_excel(io.BytesIO(response.content)), None
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
      data["date"] = f"{time_elems[0].get_text(strip=True)} to {time_elems[1].get_text(strip=True)}"
    else:
      data["date"] = "Date not found"

    tag_elems = soup.find_all(
        ["span", "li"], class_=re.compile(r"tag|tag-duo__title")
    )
    valid_tags = [
        tag.get_text(strip=True)
        for tag in tag_elems
        if tag.get_text(strip=True)
        and tag.get_text(strip=True).lower() != "get link"
        and tag.get_text(strip=True).lower() != "provincial"
        and "rising stars" not in tag.get_text(strip=True).lower()
    ]
    data["star_level"] = (
        " / ".join(dict.fromkeys(valid_tags))
        if valid_tags
        else "Star level not found"
    )

    age_group_text = "Age group not found"
    for h3 in soup.find_all("h3"):
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

# Initialize session state for persistent storage
if "tournament_results" not in st.session_state:
  st.session_state.tournament_results = None

if st.button("Retrieve Data", type="primary"):
  urls = [line.strip() for line in urls_input.split("\n") if line.strip()]

  if not urls:
    st.warning("Please enter at least one URL.")
  elif len(urls) > 10:
    st.error("Please limit your input to a maximum of 10 URLs.")
  else:
    u14_df, u14_sheet = load_u14_rankings()
    u12_df, u12_sheet = load_u12_rankings()
    points_df, points_error = load_points_table()

    tournament_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, url in enumerate(urls):
      status_text.text(
          f"Scraping tournament {i+1} of {len(urls)}... Please wait."
      )
      result = scrape_tournament_data(url)

      winner_points = "N/A"
      finalist_points = "N/A"
      players = result.get("players", [])

      if points_df is not None and not points_df.empty and players:
        total_players = len(players)
        age_group_raw = result.get("age_group", "").upper()
        star_level_raw = result.get("star_level", "").lower()
        target_age = "12" if "12" in age_group_raw else "14"

        try:
          df_pts = points_df.copy()
          df_pts["Age_Str"] = df_pts.iloc[:, 0].astype(str)
          df_pts["Draw_Str"] = df_pts.iloc[:, 1].astype(str)
          df_pts["Type_Str"] = df_pts.iloc[:, 2].astype(str)
          df_pts["Finish_Str"] = df_pts.iloc[:, 3].astype(str)

          filtered_pts = df_pts[
              df_pts["Age_Str"].str.contains(target_age, case=False, na=False)
          ]

          if "rising" in star_level_raw:
            filtered_pts = filtered_pts[
                filtered_pts["Type_Str"].str.contains(
                    "rising", case=False, na=False
                )
            ]
          elif "provincial" in star_level_raw:
            filtered_pts = filtered_pts[
                filtered_pts["Type_Str"].str.contains(
                    "provincial", case=False, na=False
                )
            ]
          else:
            star_match = re.search(r"(\d+)", star_level_raw)
            if star_match:
              filtered_pts = filtered_pts[
                  filtered_pts["Type_Str"].str.contains(
                      star_match.group(1), case=False, na=False
                  )
              ]

          def match_draw_size(draw_text, count):
            dt_lower = draw_text.lower()
            if "or more" in dt_lower:
              num_match = re.search(r"(\d+)", dt_lower)
              return num_match and count >= int(num_match.group(1))
            numbers = [int(n) for n in re.findall(r"\d+", dt_lower)]
            if len(numbers) == 1:
              return count == numbers[0]
            elif len(numbers) >= 2:
              return numbers[0] <= count <= numbers[1]
            return False

          filtered_pts = filtered_pts[
              filtered_pts["Draw_Str"].apply(
                  lambda x: match_draw_size(x, total_players)
              )
          ]

          win_row = filtered_pts[
              filtered_pts["Finish_Str"].str.contains(
                  "winner", case=False, na=False
              )
          ]
          fin_row = filtered_pts[
              filtered_pts["Finish_Str"].str.contains(
                  "finalist", case=False, na=False
              )
          ]

          if not win_row.empty:
            winner_points = win_row.iloc[0, 4]
          if not fin_row.empty:
            finalist_points = fin_row.iloc[0, 4]
        except Exception:
          pass

      df = pd.DataFrame(players)
      if not df.empty:
        age_group = result.get("age_group", "").upper()
        active_rankings = u12_df if "12" in age_group else u14_df
        if (
            active_rankings is not None
            and "Player" in active_rankings.columns
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
          df["Rank"] = df["Rank"].fillna("Not Found")
          numeric_ranks = pd.to_numeric(df["Rank"], errors="coerce")
          df["Rank"] = [
              (str(int(x)) if pd.notnull(x) else val)
              for x, val in zip(numeric_ranks, df["Rank"])
          ]
        else:
          df["Rank"] = "Unavailable"

        if "Rank" in df.columns:
          df = df[["Player Name", "Rank", "Registration Status"]]

        df["_is_maindraw"] = (
            df["Registration Status"]
            .astype(str)
            .str.lower()
            .str.contains("maindraw")
        )
        df["_sort_rank"] = pd.to_numeric(df["Rank"], errors="coerce").fillna(
            float("inf")
        )
        df_maindraw = df[df["_is_maindraw"]].sort_values(
            by="_sort_rank", ascending=True
        )
        df_others = df[~df["_is_maindraw"]].sort_values(
            by="Registration Status", ascending=True
        )
        df = pd.concat([df_maindraw, df_others]).drop(
            columns=["_is_maindraw", "_sort_rank"]
        )
      else:
        df = pd.DataFrame(columns=["Player Name", "Rank", "Registration Status"])

      result["winner_points"] = winner_points
      result["finalist_points"] = finalist_points
      result["processed_df"] = df
      tournament_results.append((url, result))
      progress_bar.progress((i + 1) / len(urls))

    status_text.empty()
    progress_bar.empty()
    st.session_state.tournament_results = tournament_results

# Render results if they exist in session state
if st.session_state.tournament_results:
  st.success("Data retrieval complete!")
  st.divider()

  tournament_results = st.session_state.tournament_results
  tab_titles = [
      res.get("title", f"Tournament {i+1}")[:25]
      for i, (_, res) in enumerate(tournament_results)
  ]
  tabs = st.tabs(tab_titles)

  for i, (tab, (url, data)) in enumerate(zip(tabs, tournament_results)):
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

      st.markdown(
          """
            <style>
            [data-testid="stMetricValue"] { text-align: center; }
            [data-testid="stMetricLabel"] { display: flex; justify-content: center; }
            </style>
            """,
          unsafe_allow_html=True,
      )

      col4, col5 = st.columns(2)
      with col4:
        st.metric("🥇 Winner Points Potential", data["winner_points"])
      with col5:
        st.metric("🥈 Finalist Points Potential", data["finalist_points"])

      st.divider()
      st.subheader("Registered Players & Rankings")

      players = data.get("players", [])
      if not players:
        st.info("No player data could be parsed from this page.")
      else:
        df_display = data["processed_df"]
        styled_df = df_display.style.apply(style_player_status, axis=1)
        st.dataframe(
            styled_df,
            use_container_width=False,
            hide_index=True,
            height=(len(df_display) + 1) * 35 + 10,
            column_config={
                "Player Name": st.column_config.TextColumn(
                    "Player Name", width=220
                ),
                "Rank": st.column_config.TextColumn("Rank", width=80),
                "Registration Status": st.column_config.TextColumn(
                    "Registration Status", width=180
                ),
            },
        )

  # --- GLOBAL GEMINI ADVISOR INTEGRATION ---
  st.divider()
  st.markdown("### 🤖 Global AI Tournament Prioritization & Strategy Advisor")
  st.markdown(
      "Analyze **all** retrieved tournaments together to get a comprehensive"
      " recommendation on which event(s) Ela should prioritize, which to"
      " withdraw from, and how to optimize her choices based on field dynamics"
      " and historical withdrawal rates."
  )

  if st.button(
      "Generate Comprehensive Gemini Priority Recommendation",
      type="primary",
      key="global_gemini_btn",
  ):
    with st.spinner(
        "Consulting Google Gemini with all tournament fields, rankings, and"
        " historical patterns..."
    ):
      try:
        policy_text = ""
        try:
          with open("multientrypol.txt", "r", encoding="utf-8") as f:
            policy_text = f.read()
        except Exception:
          policy_text = "Policy text could not be loaded."

        ela_df_context = ""
        try:
          ela_df = pd.read_excel("Ela.xlsx")
          ela_df_context = ela_df.to_string()
        except Exception:
          ela_df_context = "Ela points data unavailable."

        tourn_summary = ""
        try:
          tourn_xls = pd.ExcelFile("tourn.xlsx")
          for s_name in tourn_xls.sheet_names:
            s_df = pd.read_excel(tourn_xls, s_name)
            tourn_summary += (
                f"\nSheet {s_name}:\n"
                f"{s_df.to_string()}\n"
            )
        except Exception:
          tourn_summary = "Historical tournament patterns unavailable."

        players_summary = ""
        try:
          p_xls = pd.ExcelFile("players.xlsx")
          for s_name in p_xls.sheet_names:
            p_df = pd.read_excel(p_xls, s_name)
            players_summary += (
                f"\nPlayers sheet {s_name} sample:\n"
                f"{p_df.head(5).to_string()}\n"
            )
        except Exception:
          players_summary = "Player statistics summary unavailable."

        all_tournaments_context = ""
        for idx, (t_url, t_data) in enumerate(tournament_results):
          if "error" in t_data:
            continue
          all_tournaments_context += f"""
                    --- TOURNAMENT {idx+1} ---
                    Title: {t_data.get('title')}
                    URL: {t_url}
                    Star Level: {t_data.get('star_level')}
                    Age Group: {t_data.get('age_group')}
                    Dates: {t_data.get('date')}
                    Winner Points Potential: {t_data.get('winner_points')}
                    Finalist Points Potential: {t_data.get('finalist_points')}
                    Field & Status:
                    {t_data.get('processed_df').to_string() if not t_data.get('processed_df').empty else 'N/A'}
                    """

        gemini_api_key = st.secrets.get("GEMINI_API_KEY", "")
        if not gemini_api_key:
          st.error("GEMINI_API_KEY is missing from Streamlit secrets.")
        else:
          genai.configure(api_key=gemini_api_key)
          model = genai.GenerativeModel("gemini-2.5-flash")

          prompt = f"""
                    You are an expert AI sports analyst with advanced skills in statistical analysis and competitive tennis strategy. 
                    Your task is to advise junior tennis player Ela Velic on a global strategy across ALL her registered tournaments. 
                    Ela is fully aware of the OTA Multiple Entries Policy and is executing this analysis right before the withdrawal deadline to remain strictly compliant. Therefore, do not spend excessive space outlining or explaining the basic rules of the policy; focus purely on strategic optimization.

                    CONTEXT & INPUT DATA:
                    1. OTA Multiple Entries Policy guidelines (`multientrypol.txt`):
                    {policy_text}

                    2. Ela's Points & Ranking History (`Ela.xlsx` - Junior rankings count best 5 tournaments over 52 weeks):
                    {ela_df_context}

                    3. Historical Concurrent Tournament Drop & Participation Rates (`tourn.xlsx`):
                    Take this historical data into account. Recognize that other top players are similarly multi-registering across overlapping events and will be making strategic withdrawal/drop decisions right before the deadline. Factor in how these peer withdrawals will shift main draw and reserve list dynamics.
                    {tourn_summary}

                    4. Scraped Field Data & Competitor Statistics for ALL Current Tournaments Entered:
                    {all_tournaments_context}
                    
                    {players_summary}

                    OBJECTIVE:
                    Provide a structured, rigorous comparative analysis and recommendation:
                    - Briefly note compliance under the policy while centering the analysis on strategic trade-offs (draw density, seed positioning, match load, and ranking point gains).
                    - Incorporate historical peer withdrawal trends from `tourn.xlsx` to estimate realistic movement on main draws and reserve lists.
                    - Clearly state which specific tournament(s) Ela should commit to and which ones she should drop.
                    - Give clear, actionable instructions.
                    """

          response = model.generate_content(prompt)
          st.markdown("### 📋 Gemini Comprehensive Priority Recommendation")
          st.write(response.text)

      except Exception as api_err:
        st.error(f"Failed to generate Gemini response: {str(api_err)}")
