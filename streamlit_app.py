# Points Lookup Calculation
        winner_points = "N/A"
        finalist_points = "N/A"

        if points_df is not None and not points_df.empty:
          players = data.get("players", [])
          total_players = len(players)
          age_group_raw = data.get("age_group", "").upper()
          star_level_raw = data.get("star_level", "").lower()

          # 1. Determine target age category (e.g., U12 or U14)
          target_age = "12" if "12" in age_group_raw else "14"

          try:
            # Print columns or map dynamically based on typical structure:
            # Col 0: Age Group, Col 1: Draw Size, Col 2: Tournament Type, Col 3: Finish Position, Col 4: Points
            df_pts = points_df.copy()
            # Standardize columns to string for safe searching
            df_pts["Age_Str"] = df_pts.iloc[:, 0].astype(str)
            df_pts["Draw_Str"] = df_pts.iloc[:, 1].astype(str)
            df_pts["Type_Str"] = df_pts.iloc[:, 2].astype(str)
            df_pts["Finish_Str"] = df_pts.iloc[:, 3].astype(str)

            # Filter by Age Group (e.g., contains 12)
            filtered_pts = df_pts[
                df_pts["Age_Str"].str.contains(target_age, case=False, na=False)
            ]

            # Filter by Tournament Type / Star Level (e.g., "Rising Stars" or "3 Star")
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
              # Extract star numbers if applicable (e.g., "3 Star" -> "3")
              star_match = re.search(r"(\d+)", star_level_raw)
              if star_match:
                star_num = star_match.group(1)
                filtered_pts = filtered_pts[
                    filtered_pts["Type_Str"].str.contains(
                        star_num, case=False, na=False
                    )
                ]

            # Match Draw Size range (handles text formats like "3 players", "8 or more", etc.)
            def match_draw_size(draw_text, count):
              draw_text_lower = draw_text.lower()
              if "or more" in draw_text_lower:
                num_match = re.search(r"(\d+)", draw_text_lower)
                if num_match and count >= int(num_match.group(1)):
                  return True
              else:
                numbers = [int(n) for n in re.findall(r"\d+", draw_text_lower)]
                if len(numbers) == 1:
                  if count == numbers[0]:
                    return True
                elif len(numbers) >= 2:
                  if numbers[0] <= count <= numbers[1]:
                    return True
              return False

            filtered_pts = filtered_pts[
                filtered_pts["Draw_Str"].apply(
                    lambda x: match_draw_size(x, total_players)
                )
            ]

            # Find Winner and Finalist rows
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
              winner_points = win_row.iloc[0, 4]  # Points column
            if not fin_row.empty:
              finalist_points = fin_row.iloc[0, 4]  # Points column
          except Exception as e:
            # Fallback debug option if needed
            pass
