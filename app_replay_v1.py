# app_replay_v1b.py
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="CBA Dialog Replay (Eventlog) – v1b", layout="wide")
st.title("CBA Dialog Replay – Schritt 1b (Read-only, PK & Sortierung)")

st.markdown("""
Diese Version nutzt **(VPID, Question, Dialogstep)** als Primärschlüssel und sortiert pro Dialog:
1) nach **Dialogstep** (numerisch), sonst
2) nach **time_of_student_answer** (Millisekunden, numerisch).
""")

# ---------------------------
# Hilfsfunktionen
# ---------------------------
def read_table(uploaded):
    if uploaded.name.endswith(".csv"):
        return pd.read_csv(uploaded)
    elif uploaded.name.endswith(".xlsx"):
        return pd.read_excel(uploaded)
    else:
        st.error("Bitte CSV oder XLSX hochladen.")
        st.stop()

def to_int_safe(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

def to_num_ms(x, default=np.nan):
    try:
        return pd.to_numeric(x)
    except Exception:
        return default

def bubble(role, text):
    if text is None or (isinstance(text, float) and np.isnan(text)) or str(text).strip() == "":
        return
    bg = "#f1f5f9" if role == "Tutor" else "#ffffff"
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-radius:10px;padding:10px;margin:6px 0;background:{bg}">
          <div style="font-size:12px;color:#64748b;">{role}</div>
          <div style="white-space:pre-wrap;">{text}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_turn(row):
    # Tutor-Frage
    tq = row.get("Tutor_Text_Question", "")
    if isinstance(tq, str) and tq.strip():
        bubble("Tutor", tq)
    # Schüler
    stxt = row.get("Student.Text", "")
    if isinstance(stxt, str) and stxt.strip():
        bubble("Schüler:in", stxt)
    # Tutor-Assessment / Hint / Feedback
    ta = row.get("Tutor_Text_Assessment", "")
    if isinstance(ta, str) and ta.strip():
        bubble("Tutor", ta)

# ---------------------------
# Datei laden
# ---------------------------
st.sidebar.header("Daten")
uploaded = st.sidebar.file_uploader("CSV oder XLSX hochladen", type=["csv", "xlsx"])

if not uploaded:
    st.info("⬅️ Lade links eure Eventlog-Datei hoch (CSV/XLSX).")
    st.stop()

df = read_table(uploaded)

# Spaltenhinweise
with st.sidebar.expander("Erkannte Spalten"):
    st.code(", ".join(df.columns))

# Erwartete Kernspalten
core = ["VPID", "Question", "Dialogstep"]
missing_core = [c for c in core if c not in df.columns]
if missing_core:
    st.error(f"Fehlende Kernspalten für den Primärschlüssel: {missing_core}")
    st.stop()

# Typen vorbereiten für Navigation & Sortierung
df["VPID_str"] = df["VPID"].astype(str)
df["Question_int"] = df["Question"].apply(lambda v: to_int_safe(v, None))
df["Dialogstep_int"] = df["Dialogstep"].apply(lambda v: to_int_safe(v, None))
if "time_of_student_answer" in df.columns:
    df["time_ms"] = to_num_ms(df["time_of_student_answer"], np.nan)
else:
    df["time_ms"] = np.nan

# Duplicate-Check (PK)
dups = df.duplicated(subset=["VPID_str", "Question_int", "Dialogstep_int"], keep=False)
if dups.any():
    st.warning("⚠️ Es gibt Duplikate bzgl. (VPID, Question, Dialogstep). "
               "Das kann die Replay-Reihenfolge stören. Beispiele unten.")
    with st.expander("Beispiele für PK-Duplikate"):
        cols_show = ["VPID", "Question", "Dialogstep", "Type",
                     "Tutor_Text_Question","Student.Text","Tutor_Text_Assessment",
                     "time_of_student_answer","EventID"]
        st.dataframe(df.loc[dups, cols_show].head(50), use_container_width=True)

# ---------------------------
# Navigation
# ---------------------------
left, right = st.columns([1, 2], vertical_alignment="top")

with left:
    st.subheader("Navigation")

    vpids = sorted(df["VPID_str"].unique().tolist())
    sel_vpid = st.selectbox("VPID (Schüler:in)", vpids)

    df_v = df[df["VPID_str"] == sel_vpid].copy()
    q_list = sorted([q for q in df_v["Question_int"].dropna().unique().tolist()])
    if not q_list:
        st.error("Keine `Question`-Werte für diese VPID gefunden.")
        st.stop()

    sel_q = st.selectbox("Question (Frage-Nr.)", q_list)

with right:
    st.subheader("Dialog-Vorschau")

    sub = df_v[df_v["Question_int"] == sel_q].copy()
    if sub.empty:
        st.error("Keine Ereignisse für diese Auswahl gefunden.")
        st.stop()

    # Reihenfolge: Dialogstep_int (aufsteigend), Fallback time_ms
    # fehlende Schritte ganz nach hinten
    sub["order_key"] = sub["Dialogstep_int"].apply(lambda v: v if v is not None else 10**9)
    # Bei Gleichstand oder None -> time_ms (Millisekunden)
    sub["order_key_2"] = sub["time_ms"].fillna(1e15)

    sub = sub.sort_values(by=["order_key", "order_key_2"], ascending=[True, True])

    # Chat rendern
    for _, r in sub.iterrows():
        render_turn(r)

    with st.expander("Rohdaten für diesen Dialog"):
        cols_show = [c for c in [
            "VPID","Question","Dialogstep","Type",
            "Tutor_Text_Question","Student.Text","Tutor_Text_Assessment",
            "Next.Step","Evaluation","time_of_student_answer","EventID",
            "Anzahl_Woerter_Antwort","M_Wortlaenge_Antwort"
        ] if c in sub.columns]
        st.dataframe(sub[cols_show].reset_index(drop=True), use_container_width=True)

st.markdown("---")