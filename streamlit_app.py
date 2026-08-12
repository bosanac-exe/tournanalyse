col4, col5 = st.columns(2)
        with col4:
          st.metric("🥇 Winner Points Potential", winner_points)
        with col5:
          st.metric("🥈 Finalist Points Potential", finalist_points)

        st.divider()
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

          df["_is_maindraw"] = (
              df["Registration Status"]
              .astype(str)
              .str.lower()
              .str.contains("maindraw")
          )
          df["_sort_rank"] = pd.to_numeric(df["Rank"], errors="coerce")

          df_maindraw = df[df["_is_maindraw"]].sort_values(
              by="_sort_rank", ascending=True, na_position="last"
          )
          df_others = df[~df["_is_maindraw"]].sort_values(
              by="Registration Status", ascending=True
          )

          df = pd.concat([df_maindraw, df_others]).drop(
              columns=["_is_maindraw", "_sort_rank"]
          )

          styled_df = df.style.apply(style_player_status, axis=1)
          table_height = (len(df) + 1) * 35 + 10

          st.dataframe(
              styled_df,
              use_container_width=False,
              hide_index=True,
              height=table_height,
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
