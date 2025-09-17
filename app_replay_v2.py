# app_replay_v2_coding.py
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="CBA Dialog Replay – Coding v2", layout="wide")
st.title("CBA Dialog Replay – Schritt 2 (Coding + Auto-Weiter)")

st.markdown("""
Diese Version zeigt den Dialog (Replay) und bietet zwei Coding-Felder pro *(VPID, Question)*:
1) **Fehlvorstellung vorhanden?** (Ja/Nein)  
2) **Welche Fehlvorstellung?** (Freitext)  

Nach **Speichern** springt die Ansicht automatisch zur **nächsten Frage** derselben VPID.
""")

# ---------------------------
# Hilfsfunktionen
# ---------------------------
def read_table(uploaded):
    if uploaded.name.endswith(".csv"):
        return pd.read_csv(uploaded)
    elif uploaded.name.endswith(".xlsx"):
        try:
            return pd.read_excel(uploaded)
        except Exception as e:
            st.error("Excel-Datei erkannt, aber konnte nicht gelesen werden. "
                     "Bitte installiere das Paket 'openpyxl' (pip install openpyxl) "
                     f"oder lade eine CSV hoch.\n\nDetails: {e}")
            st.stop()
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
        return pd.to_numeric(x, errors="coerce").fillna(default)
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
    tq = row.get("Tutor_Text_Question", "")
    if isinstance(tq, str) and tq.strip():
        bubble("Tutor", tq)
    stxt = row.get("Student.Text", "")
    if isinstance(stxt, str) and stxt.strip():
        bubble("Schüler:in", stxt)
    ta = row.get("Tutor_Text_Assessment", "")
    if isinstance(ta, str) and ta.strip():
        bubble("Tutor", ta)

def init_session():
    if "codes" not in st.session_state:
        # {(vpid_str, question_int): {"misconception_present": True/False, "misconception_text": str}}
        st.session_state.codes = {}
    if "sel_vpid_idx" not in st.session_state:
        st.session_state.sel_vpid_idx = 0
    if "sel_q_idx" not in st.session_state:
        st.session_state.sel_q_idx = 0

init_session()

# ---------------------------
# Datei laden
# ---------------------------
st.sidebar.header("Daten")
uploaded = st.sidebar.file_uploader("CSV oder XLSX hochladen", type=["csv", "xlsx"])

if not uploaded:
    st.info("⬅️ Lade links eure Eventlog-Datei hoch (CSV/XLSX).")
    st.stop()

df = read_table(uploaded)

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
    st.warning("⚠️ Es gibt Duplikate bzgl. (VPID, Question, Dialogstep). Beispielhafte Zeilen unten.")
    with st.expander("Beispiele für PK-Duplikate"):
        cols_show = ["VPID", "Question", "Dialogstep", "Type",
                     "Tutor_Text_Question","Student.Text","Tutor_Text_Assessment",
                     "time_of_student_answer","EventID"]
        st.dataframe(df.loc[dups, [c for c in cols_show if c in df.columns]].head(50), use_container_width=True)

# ---------------------------
# Navigation
# ---------------------------
left, right = st.columns([1, 2])  # kein vertical_alignment-Argument

with left:
    st.subheader("Navigation")

    vpids = sorted(df["VPID_str"].unique().tolist())
    sel_vpid_idx_safe = min(max(st.session_state.sel_vpid_idx, 0), max(len(vpids)-1, 0))
    sel_vpid = st.selectbox("VPID (Schüler:in)", vpids, index=sel_vpid_idx_safe)
    st.session_state.sel_vpid_idx = vpids.index(sel_vpid)

    df_v = df[df["VPID_str"] == sel_vpid].copy()
    q_list = sorted([q for q in df_v["Question_int"].dropna().unique().tolist()])
    if not q_list:
        st.error("Keine `Question`-Werte für diese VPID gefunden.")
        st.stop()

    sel_q_idx_safe = min(max(st.session_state.sel_q_idx, 0), max(len(q_list)-1, 0))
    sel_q = st.selectbox("Question (Frage-Nr.)", q_list, index=sel_q_idx_safe)
    st.session_state.sel_q_idx = q_list.index(sel_q)

with right:
    st.subheader("Dialog-Vorschau")

    sub = df_v[df_v["Question_int"] == sel_q].copy()
    if sub.empty:
        st.error("Keine Ereignisse für diese Auswahl gefunden.")
        st.stop()

    # Sortierung: erst Dialogstep, fallback time_ms (Millisekunden)
    sub["order_key"] = sub["Dialogstep_int"].apply(lambda v: v if v is not None else 10**9)
    sub["order_key_2"] = sub["time_ms"].fillna(1e15)
    sub = sub.sort_values(by=["order_key", "order_key_2"], ascending=[True, True])

    # Replay
    for _, r in sub.iterrows():
        render_turn(r)

    # ---------------------------
    # Coding-UI
    # ---------------------------
    st.markdown("---")
    st.subheader("Coding für diese Frage")

    key_tuple = (sel_vpid, int(sel_q))
    existing = st.session_state.codes.get(key_tuple, {})

    # 1) Fehlvorstellung vorhanden? (binär)
    inv_default = {True: "Ja", False: "Nein"}
    current_choice = inv_default[existing.get("misconception_present", False)] if existing else "Nein"

    choice = st.radio(
        "Liegt eine Fehlvorstellung vor?",
        options=["Ja", "Nein"],
        index=0 if current_choice == "Ja" else 1,
        horizontal=True
    )
    misconception_present = (choice == "Ja")

    # 2) Welche Fehlvorstellung? (Freitext)
    misconception_text = st.text_area(
        "Welche Fehlvorstellung liegt vor?",
        value=existing.get("misconception_text", ""),
        height=100,
        placeholder="z. B. 'Treibhausgas = Sauerstoff', 'Verwechslung Reflexion/Absorption' …"
    )

    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("💾 Speichern", use_container_width=True):
            st.session_state.codes[key_tuple] = {
                "misconception_present": misconception_present,
                "misconception_text": (misconception_text or "").strip(),
            }
            st.success("Coding gespeichert.")

    def goto_next_question():
        """Zur nächsten Question derselben VPID springen."""
        idx = q_list.index(sel_q)
        if idx < len(q_list) - 1:
            st.session_state.sel_q_idx = idx + 1
        else:
            st.session_state.sel_q_idx = idx  # am Ende bleiben
            st.balloons()
            st.info("Für diese VPID gibt es keine weitere Frage.")
        # rerun
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()

    with col2:
        if st.button("💾 Speichern & nächste Frage →", use_container_width=True):
            st.session_state.codes[key_tuple] = {
                "misconception_present": misconception_present,
                "misconception_text": (misconception_text or "").strip(),
            }
            goto_next_question()

# ---------------------------
# Export (optional)
# ---------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("Export")
if st.session_state.codes:
    rows = []
    for (vpid, q), val in st.session_state.codes.items():
        rows.append({
            "VPID": vpid,
            "Question": q,
            "misconception_present": bool(val.get("misconception_present", False)),
            "misconception_text": val.get("misconception_text", ""),
        })
    export_df = pd.DataFrame(rows).sort_values(["VPID", "Question"])
    st.sidebar.download_button(
        label="Codings als CSV herunterladen",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name="cba_codings.csv",
        mime="text/csv",
    )
else:
    st.sidebar.caption("Noch keine Codings vorhanden.")
