from bs4 import BeautifulSoup
import google.generativeai as genai
import io
import pandas as pd
import re
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
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


def generate_pdf_report(tournament_results, advisor_text):
  """Generates an exceptionally polished, readable PDF report using ReportLab."""
  buffer = io.BytesIO()

  class NumberedCanvas(canvas.Canvas):

    def __init__(self, *args, **kwargs):
      super().__init__(*args, **kwargs)
      self._saved_page_states = []

    def showPage(self):
      self._saved_page_states.append(dict(self.__dict__))
      self._startPage()

    def save(self):
      num_pages = len(self._saved_page_states)
      for state in self._saved_page_states:
        self.__dict__.update(state)
        self.draw_header_footer(num_pages)
        super().showPage()
      super().save()

    def draw_header_footer(self, page_count):
      self.saveState()
      self.setFont("Helvetica", 8)
      self.setFillColor(colors.HexColor("#718096"))

      if self._pageNumber > 1:
        self.drawString(
            36, 760, "Ela Velic — Tournament Strategy & Multi-Entry Analysis"
        )
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(36, 752, letter[0] - 36, 752)

      self.setStrokeColor(colors.HexColor("#E2E8F0"))
      self.setLineWidth(0.5)
      self.line(36, 45, letter[0] - 36, 45)

      page_text = f"Page {self._pageNumber} of {page_count}"
      self.drawRightString(letter[0] - 36, 32, page_text)
      self.drawString(36, 32, "Confidential — OTA Junior Competitive Analysis")
      self.restoreState()

  doc = SimpleDocTemplate(
      buffer,
      pagesize=letter,
      rightMargin=36,
      leftMargin=36,
      topMargin=54,
      bottomMargin=54,
  )

  styles = getSampleStyleSheet()

  title_style = ParagraphStyle(
      "DocTitle",
      parent=styles["Heading1"],
      fontSize=18,
      leading=22,
      textColor=colors.HexColor("#1A365D"),
      fontName="Helvetica-Bold",
      spaceAfter=12,
  )

  h1_style = ParagraphStyle(
      "SectionH1",
      parent=styles["Heading2"],
      fontSize=13,
      leading=16,
      textColor=colors.HexColor("#2B6CB0"),
      fontName="Helvetica-Bold",
      spaceBefore=16,
      spaceAfter=6,
      keepWithNext=True,
  )

  h2_style = ParagraphStyle(
      "SectionH2",
      parent=styles["Heading3"],
      fontSize=10.5,
      leading=14,
      textColor=colors.HexColor("#2D3748"),
      fontName="Helvetica-Bold",
      spaceBefore=12,
      spaceAfter=4,
      keepWithNext=True,
  )

  body_style = ParagraphStyle(
      "BodyTextCustom",
      parent=styles["Normal"],
      fontSize=9,
      leading=13,
      textColor=colors.HexColor("#2D3748"),
      spaceAfter=6,
  )

  bullet_style = ParagraphStyle(
      "BulletCustom",
      parent=body_style,
      leftIndent=15,
      firstLineIndent=-10,
      spaceAfter=3,
  )

  quote_style = ParagraphStyle(
      "QuoteCustom",
      parent=body_style,
      fontSize=9,
      leading=13,
      textColor=colors.HexColor("#1A202C"),
      backColor=colors.HexColor("#EDF2F7"),
      borderColor=colors.HexColor("#CBD5E0"),
      borderWidth=1,
      borderPadding=6,
      spaceBefore=6,
      spaceAfter=8,
  )

  table_header_style = ParagraphStyle(
      "TableHeader",
      parent=styles["Normal"],
      fontSize=8.5,
      leading=11,
      textColor=colors.white,
      fontName="Helvetica-Bold",
  )

  table_cell_style = ParagraphStyle(
      "TableCell",
      parent=styles["Normal"],
      fontSize=8,
      leading=10.5,
      textColor=colors.HexColor("#2D3748"),
  )

  table_cell_maindraw = ParagraphStyle(
      "TableCellMain",
      parent=table_cell_style,
      textColor=colors.HexColor("#155724"),
      fontName="Helvetica-Bold",
  )

  table_cell_reserve = ParagraphStyle(
      "TableCellReserve",
      parent=table_cell_style,
      textColor=colors.HexColor("#856404"),
      fontName="Helvetica-Bold",
  )

  story = []

  story.append(
      Paragraph(
          "🎾 Comprehensive Tournament Priority & Strategy Report", title_style
      )
  )
  story.append(
      Paragraph(
          "<b>Player:</b> Ela Velic &nbsp;|&nbsp; <b>Framework:</b> OTA Junior"
          " Competitive Analysis",
          body_style,
      )
  )
  story.append(
      HRFlowable(
          width="100%",
          thickness=1.5,
          color=colors.HexColor("#2B6CB0"),
          spaceBefore=6,
          spaceAfter=12,
      )
  )

  def parse_inline(txt):
    txt = re.sub(r"\*\*\*(.*?)\*\*\*", r"<b><i>\1</i></b>", txt)
    txt = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", txt)
    txt = re.sub(r"\*(.*?)\*", r"<i>\1</i>", txt)
    return txt

  if advisor_text:
    story.append(Paragraph("🤖 Gemini Priority Recommendation", h1_style))
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.75,
            color=colors.HexColor("#2B6CB0"),
            spaceAfter=8,
        )
    )

    lines = advisor_text.split("\n")
    i = 0
    while i < len(lines):
      line = lines[i].strip()

      if line.startswith("|") and "|" in line[1:]:
        table_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip().startswith("|"):
          table_lines.append(lines[i].strip())
          i += 1

        rows = []
        for t_line in table_lines:
          if "---" in t_line:
            continue
          cells = [parse_inline(c.strip()) for c in t_line.split("|")[1:-1]]
          rows.append(cells)

        if rows:
          table_data = []
          for row_idx, row in enumerate(rows):
            formatted_row = []
            for cell in row:
              if row_idx == 0:
                formatted_row.append(
                    Paragraph(f"<b>{cell}</b>", table_header_style)
                )
              else:
                formatted_row.append(Paragraph(cell, table_cell_style))
            table_data.append(formatted_row)

          num_cols = len(table_data[0]) if table_data else 1
          col_width = 540 / num_cols
          t = Table(table_data, colWidths=[col_width] * num_cols)
          t.setStyle(
              TableStyle([
                  ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("TOPPADDING", (0, 0), (-1, -1), 4),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                  ("LEFTPADDING", (0, 0), (-1, -1), 5),
                  ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                  ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                  (
                      "ROWBACKGROUNDS",
                      (0, 1),
                      (-1, -1),
                      [colors.white, colors.HexColor("#F7FAFC")],
                  ),
              ])
          )
          story.append(t)
          story.append(Spacer(1, 6))
        continue

      if not line:
        i += 1
        continue

      if line.startswith("# "):
        story.append(Paragraph(parse_inline(line[2:]), h1_style))
      elif line.startswith("## "):
        story.append(Paragraph(parse_inline(line[3:]), h1_style))
      elif line.startswith("### "):
        story.append(Paragraph(parse_inline(line[4:]), h2_style))
      elif line.startswith("> "):
        story.append(Paragraph(parse_inline(line[2:]), quote_style))
      elif line.startswith("* ") or line.startswith("- "):
        story.append(Paragraph(f"• {parse_inline(line[2:])}", bullet_style))
      else:
        story.append(Paragraph(parse_inline(line), body_style))

      i += 1

  if tournament_results:
    story.append(Spacer(1, 10))
    story.append(
        Paragraph("📋 Scraped Tournament Fields & Player Statuses", h1_style)
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.75,
            color=colors.HexColor("#2B6CB0"),
            spaceAfter=8,
        )
    )

    for idx, (url, data) in enumerate(tournament_results):
      if "error" in data:
        continue

      t_title = data.get("title", f"Tournament {idx+1}")
      t_date = data.get("date", "N/A")
      t_star = data.get("star_level", "N/A")
      t_age = data.get("age_group", "N/A")
      win_p = data.get("winner_points", "N/A")
      fin_p = data.get("finalist_points", "N/A")
      df_players = data.get("processed_df", pd.DataFrame())

      header_html = (
          f"<b>{idx+1}. {t_title}</b> ({t_age} | {t_star})<br/><font"
          f" size=7.5 color='#718096'>Dates: {t_date} | Winner Pts: {win_p} |"
          f" Finalist Pts: {fin_p}</font>"
      )
      story.append(Paragraph(header_html, h2_style))
      story.append(Spacer(1, 3))

      if not df_players.empty:
        table_rows = [[
            Paragraph("<b>Player Name</b>", table_header_style),
            Paragraph("<b>Rank</b>", table_header_style),
            Paragraph("<b>Registration Status</b>", table_header_style),
        ]]

        for _, p_row in df_players.iterrows():
          p_name = str(p_row.get("Player Name", ""))
          p_rank = str(p_row.get("Rank", ""))
          p_status = str(p_row.get("Registration Status", ""))

          p_name_p = Paragraph(p_name, table_cell_style)
          p_rank_p = Paragraph(p_rank, table_cell_style)

          status_lower = p_status.lower()
          if "maindraw" in status_lower:
            p_status_p = Paragraph(f"<b>{p_status}</b>", table_cell_maindraw)
          elif "reserve" in status_lower:
            p_status_p = Paragraph(f"<b>{p_status}</b>", table_cell_reserve)
          else:
            p_status_p = Paragraph(p_status, table_cell_style)

          table_rows.append([p_name_p, p_rank_p, p_status_p])

        p_table = Table(table_rows, colWidths=[260, 80, 200])
        p_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A365D")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F7FAFC")],
                ),
            ])
        )
        story.append(KeepTogether([p_table]))
        story.append(Spacer(1, 8))

  doc.build(story, canvasmaker=NumberedCanvas)
  buffer.seek(0)
  return buffer.getvalue()


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

if "tournament_results" not in st.session_state:
  st.session_state.tournament_results = None
if "gemini_response_text" not in st.session_state:
  st.session_state.gemini_response_text = ""

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
    st.session_state.gemini_response_text = ""

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
            tourn_summary += f"\nSheet {s_name}:\n{s_df.to_string()}\n"
        except Exception:
          tourn_summary = "Historical tournament patterns unavailable."

        players_summary = ""
        try:
          p_xls = pd.ExcelFile("players.xlsx")
          for s_name in p_xls.sheet_names:
            p_df = pd.read_excel(p_xls, s_name)
            players_summary += f"\nPlayers sheet {s_name} sample:\n{p_df.head(5).to_string()}\n"
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
          model = genai.GenerativeModel("gemini-3.6-flash")

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
                    Provide a structured, rigorous comparative analysis and recommendation using markdown formatting (including bullet points and tables where appropriate):
                    - Briefly note compliance under the policy while centering the analysis on strategic trade-offs (draw density, seed positioning, match load, and ranking point gains).
                    - Incorporate historical peer withdrawal trends from `tourn.xlsx` to estimate realistic movement on main draws and reserve lists.
                    - Clearly state which specific tournament(s) Ela should commit to and which ones she should drop.
                    - Give clear, actionable instructions.
                    """

          response = model.generate_content(prompt)
          st.session_state.gemini_response_text = response.text

      except Exception as api_err:
        st.error(f"Failed to generate Gemini response: {str(api_err)}")

  if st.session_state.gemini_response_text:
    st.markdown("### 📋 Gemini Comprehensive Priority Recommendation")
    st.write(st.session_state.gemini_response_text)

    st.markdown("---")
    pdf_bytes = generate_pdf_report(
        tournament_results, st.session_state.gemini_response_text
    )
    st.download_button(
        label="📥 Download PDF Report",
        data=pdf_bytes,
        file_name="Ela_Tournament_Strategy_Report.pdf",
        mime="application/pdf",
        type="primary",
    )
