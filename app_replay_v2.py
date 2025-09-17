# app_replay_v4_synced.py
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="CBA Annotation Template", layout="wide")
st.title("CBA Annotation Template")

# ---------------------------
# Helpers
# ---------------------------
def read_table(uploaded):
    if uploaded.name.endswith(".csv"):
        return pd.read_csv(uploaded)
    elif uploaded.name.endswith(".xlsx"):
        try:
            import openpyxl  # in requirements.txt
            return pd.read_excel(uploaded)
        except Exception as e:
            st.error("Excel erkannt, konnte aber nicht gelesen werden. "
                     "Bitte 'openpyxl' installieren (pip install openpyxl) oder CSV hochladen.\n\nDetails: {}".format(e))
            st.stop()
    else:
        st.error("Bitte CSV oder XLSX hochladen.")
        st.stop()

def to_int_safe(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

def to_num_ms_series(s):
    try:
        return pd.to_numeric(s, errors="coerce")
    except Exception:
        return pd.Series([np.nan]*len(s), index=s.index)

def bubble(role, text):
    if text is None or (isinstance(text, float) and np.isnan(text)) or str(text).strip() == "":
        return
    bg = "#ecf5f5" if role == "Tutor" else "#CAE3E3"
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-radius:10px;padding:10px;margin:6px 0;background:{bg}">
          <div style="font-size:12px;color:#64748b;">{role}</div>
          <div style="white-space:pre-wrap;">{text}</div>
        </div>
        """, unsafe_allow_html=True
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
        st.session_state.codes = {}  # {(vpid_str, question_int): {...}}
    if "sel_vpid_val" not in st.session_state:
        st.session_state.sel_vpid_val = None
    if "sel_q_idx" not in st.session_state:
        st.session_state.sel_q_idx = 0
        
def goto_next_question_or_person(q_list, vpids):
    """Wenn letzte Frage: zur ersten Frage der nächsten VPID springen.
       Sonst: zur nächsten Frage derselben VPID."""
    # Noch Fragen übrig? -> nächste Frage
    if st.session_state.sel_q_idx < len(q_list) - 1:
        st.session_state.sel_q_idx += 1
    else:
        # Letzte Frage -> nächste VPID (falls vorhanden)
        cur = st.session_state.sel_vpid_val
        try:
            i = vpids.index(cur)
        except ValueError:
            i = -1
        if i != -1 and i < len(vpids) - 1:
            st.session_state.sel_vpid_val = vpids[i + 1]
            st.session_state.sel_q_idx = 0
        else:
            # Wir sind bei der letzten VPID und ihrer letzten Frage
            st.info("Letzte Frage der letzten VPID erreicht.")
    # Neu rendern
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


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

# Kernspalten prüfen
core = ["VPID", "Question", "Dialogstep"]
missing_core = [c for c in core if c not in df.columns]
if missing_core:
    st.error(f"Fehlende Kernspalten für den Primärschlüssel: {missing_core}")
    st.stop()

# Hilfsspalten
df["VPID_str"] = df["VPID"].astype(str)
df["Question_int"] = df["Question"].apply(lambda v: to_int_safe(v, None))
df["Dialogstep_int"] = df["Dialogstep"].apply(lambda v: to_int_safe(v, None))
df["time_ms"] = to_num_ms_series(df["time_of_student_answer"]) if "time_of_student_answer" in df.columns else np.nan

# PK-Duplikate
dups = df.duplicated(subset=["VPID_str", "Question_int", "Dialogstep_int"], keep=False)
if dups.any():
    st.warning("⚠️ PK-Duplikate gefunden (VPID, Question, Dialogstep). Beispiele unten.")
    with st.expander("Beispiele für PK-Duplikate"):
        cols_show = ["VPID","Question","Dialogstep","Type","Tutor_Text_Question","Student.Text",
                     "Tutor_Text_Assessment","time_of_student_answer","EventID"]
        st.dataframe(df.loc[dups, [c for c in cols_show if c in df.columns]].head(50), use_container_width=True)


# ---------------------------
# Top-Navigation (2 Reihen)
# ---------------------------

# VPID-Liste
vpids = sorted(df["VPID_str"].unique().tolist())
if not st.session_state.sel_vpid_val or st.session_state.sel_vpid_val not in vpids:
    st.session_state.sel_vpid_val = vpids[0]

# Reihe 1: VPID & Question
row1_col1, row1_col2 = st.columns([1, 1])  # erste Zeile: zwei Spalten

with row1_col1:
    # VPID wählen
    sel_vpid = st.selectbox(
        "VPID (Schüler:in)",
        vpids,
        index=vpids.index(st.session_state.sel_vpid_val)
    )

# Hat sich die VPID geändert?
vpid_changed = (sel_vpid != st.session_state.sel_vpid_val)
st.session_state.sel_vpid_val = sel_vpid

# Fragenliste zur gewählten VPID
df_v = df[df["VPID_str"] == sel_vpid].copy()
q_list = sorted([q for q in df_v["Question_int"].dropna().unique().tolist()])
if not q_list:
    st.error("Keine `Question`-Werte für diese VPID gefunden.")
    st.stop()

# Bei VPID-Wechsel: auf erste Frage springen
if vpid_changed:
    st.session_state.sel_q_idx = 0

with row1_col2:
    # Question wählen (Drop-down)
    sel_q = st.selectbox(
        "Question",
        q_list,
        index=min(max(st.session_state.sel_q_idx, 0), len(q_list)-1)
    )
# Index synchronisieren, falls manuell geändert
try:
    st.session_state.sel_q_idx = q_list.index(sel_q)
except ValueError:
    st.session_state.sel_q_idx = 0

# Reihe 2: Vor/Zurück Buttons
row2_col1, row2_col2 = st.columns([1, 1])  # zweite Zeile: zwei Spalten

with row2_col1:
    if st.button("← Vorherige", use_container_width=True):
        st.session_state.sel_q_idx = max(0, st.session_state.sel_q_idx - 1)
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()

with row2_col2:
    with row2_col2:
        if st.button("Nächste →", use_container_width=True):
            goto_next_question_or_person(q_list, vpids)

# Die aktuell ausgewählte Frage:
sel_q = q_list[st.session_state.sel_q_idx]

# ---------------------------
# Side-by-side: links Dialog • rechts Coding (zur selben Frage)
# ---------------------------
left, right = st.columns([1, 1])  # garantiert nebeneinander bei layout="wide"

# ----- Links: Dialog -----
with left:
    st.subheader(f"Dialog • VPID {sel_vpid} • Question {sel_q}")
    sub = df_v[df_v["Question_int"] == sel_q].copy()
    if sub.empty:
        st.warning("Keine Ereignisse für diese Frage.")
    else:
        # Sortierung: Dialogstep (coerce), dann time_ms
        order1 = pd.to_numeric(sub["Dialogstep_int"], errors="coerce").fillna(1e9)
        order2 = pd.to_numeric(sub["time_ms"], errors="coerce").fillna(1e15) if "time_ms" in sub else pd.Series([1e15]*len(sub), index=sub.index)
        sub = sub.assign(order_key=order1, order_key_2=order2).sort_values(
            by=["order_key", "order_key_2"], ascending=[True, True]
        )
        for _, r in sub.iterrows():
            render_turn(r)

# ----- Rechts: Coding zur selben Frage -----
with right:
    st.subheader(f"Coding • VPID {sel_vpid} • Question {sel_q}")

    key_tuple = (sel_vpid, int(sel_q))
    existing = st.session_state.codes.get(key_tuple, {})
    present_default = bool(existing.get("misconception_present", False))
    text_default = existing.get("misconception_text", "")

    with st.form(key=f"form_single_{sel_vpid}_{sel_q}"):
        c1, c2 = st.columns([1, 2])
        with c1:
            choice = st.radio(
                "Fehlvorstellung vorhanden?",
                options=["Ja", "Nein"],
                index=0 if present_default else 1,
                horizontal=True,
                key=f"radio_single_{sel_vpid}_{sel_q}"
            )
            misconception_present = (choice == "Ja")
        with c2:
            misconception_text = st.text_area(
                "Welche Fehlvorstellung?",
                value=text_default,
                height=120,
                key=f"txt_single_{sel_vpid}_{sel_q}",
                placeholder="z. B. 'Treibhausgas = Sauerstoff', 'Verwechslung Reflexion/Absorption' …"
            )

        b1, b2, _ = st.columns([1, 1, 2])
        save = b1.form_submit_button("💾 Speichern")
        save_next = b2.form_submit_button("💾 Speichern & nächste →")

    if save or save_next:
        st.session_state.codes[key_tuple] = {
            "misconception_present": misconception_present,
            "misconception_text": (misconception_text or "").strip(),
        }
        st.success("Coding gespeichert.", icon="✅")

                
        if save_next:
            st.session_state.codes[key_tuple] = {
                "misconception_present": misconception_present,
                "misconception_text": (misconception_text or "").strip(),
            }
            goto_next_question_or_person(q_list, vpids)

# ---------------------------
# Export
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
