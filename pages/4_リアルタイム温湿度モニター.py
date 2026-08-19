import streamlit as st
import base64
from PIL import Image
import datetime
import json
import os
import requests
import fitz  # PDFを読み込むためのツール(PyMuPDF)
import sys
from streamlit_autorefresh import st_autorefresh  # ★追加：自動更新ライブラリを読み込む

st.set_page_config(page_title="リアルタイム温湿度モニター", layout="wide")

# ==========================================
# EXE化対応：実行されているフォルダのパスを取得
# ==========================================
if getattr(sys, 'frozen', False):
    # EXEとして実行されている場合、EXEがあるフォルダを取得
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 通常のPythonスクリプトとして実行されている場合
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if "monitor_mode" not in st.session_state:
    st.session_state.monitor_mode = False

# ==========================================
# アプリ全体の設定管理
# ==========================================
APP_SETTINGS_FILE = os.path.join(BASE_DIR, "app_settings.json")

def load_app_settings():
    if os.path.exists(APP_SETTINGS_FILE):
        try:
            with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"ondotori_api": "", "ondotori_id": "", "ondotori_pass": ""}

def save_app_settings(settings):
    with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

app_settings = load_app_settings()

# ==========================================
# 複数フロア（図面）の管理
# ==========================================
FLOORS_FILE = os.path.join(BASE_DIR, "floors.json")

def load_floors():
    if os.path.exists(FLOORS_FILE):
        with open(FLOORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["メイン"]

def save_floors(floors):
    with open(FLOORS_FILE, "w", encoding="utf-8") as f:
        json.dump(floors, f, ensure_ascii=False, indent=4)

floors = load_floors()

# ==========================================
# UI: サイドバー（フロア選択 ＆ 全画面ボタン）
# ==========================================
if st.sidebar.button("📺 モニター全画面モードを開始", type="primary", use_container_width=True):
    st.session_state.monitor_mode = True
    st.rerun()

st.sidebar.divider()

st.sidebar.header("📂 フロア（図面）の選択")
current_floor = st.sidebar.selectbox("表示するフロアを切り替え", floors)

with st.sidebar.expander("➕ 新しいフロアを追加"):
    new_floor_name = st.text_input("新しいフロア名 (例: 2階, 別館)")
    if st.button("追加する"):
        if new_floor_name and new_floor_name not in floors:
            floors.append(new_floor_name)
            save_floors(floors)
            st.success(f"{new_floor_name} を追加しました！")
            st.rerun()

with st.sidebar.expander("🗑️ 現在のフロアを削除"):
    if len(floors) > 1:
        if st.button(f"「{current_floor}」を削除"):
            floors.remove(current_floor)
            save_floors(floors)
            if os.path.exists(os.path.join(BASE_DIR, f"settings_{current_floor}.json")): os.remove(os.path.join(BASE_DIR, f"settings_{current_floor}.json"))
            if os.path.exists(os.path.join(BASE_DIR, f"bg_{current_floor}.png")): os.remove(os.path.join(BASE_DIR, f"bg_{current_floor}.png"))
            st.success("削除しました！")
            st.rerun()

st.sidebar.divider()

# ==========================================
# 内部処理（設定ファイルの読み書き）
# ==========================================
SETTINGS_FILE = os.path.join(BASE_DIR, f"settings_{current_floor}.json")
BG_IMAGE_FILE = os.path.join(BASE_DIR, f"bg_{current_floor}.png")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

settings = load_settings()

# ==========================================
# データ取得関数
# ==========================================
@st.cache_data(ttl=300)
def fetch_ondotori_data(api_key, login_id, login_pass, settings_keys):
    if not api_key or not login_id or not login_pass:
        return {"error": "おんどとりの設定（APIキー等）が入力されていません。"}
    
    url = "https://api.webstorage.jp/v1/devices/current"
    headers = {"X-HTTP-Method-Override": "GET", "Content-Type": "application/json"}
    payload = {"api-key": api_key, "login-id": login_id, "login-pass": login_pass}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        display_data = {}
        for device in data.get("devices", []):
            serial = device.get("serial")
            if serial in settings_keys:
                channels = device.get("channel", [])
                ch1_val, ch1_unit = "--", "℃"
                ch2_val, ch2_unit = "--", "%"
                
                for ch in channels:
                    num = str(ch.get("num"))
                    val = ch.get("value", "--")
                    unit = ch.get("unit", "")
                    if unit == "C": unit = "℃"
                    
                    if num == "1":
                        ch1_val = val
                        if unit: ch1_unit = unit
                    elif num == "2":
                        ch2_val = val
                        if unit: ch2_unit = unit
                
                unixtime = device.get("unixtime")
                if unixtime:
                    try:
                        dt = datetime.datetime.utcfromtimestamp(int(unixtime)) + datetime.timedelta(hours=9)
                        last_update = dt.strftime('%m/%d %H:%M')
                    except:
                        last_update = "--"
                else:
                    last_update = "--"
                
                display_data[serial] = {
                    "ch1_val": ch1_val, "ch1_unit": ch1_unit,
                    "ch2_val": ch2_val, "ch2_unit": ch2_unit,
                    "last_update": last_update
                }
        return display_data
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# UI: サイドバー（管理者メニュー）
# ==========================================
st.sidebar.header("⚙️ 管理者メニュー")

st.sidebar.subheader("☁️ おんどとり クラウド設定")
o_api = st.sidebar.text_input("APIキー", value=app_settings.get("ondotori_api", ""), type="password")
o_id = st.sidebar.text_input("ログインID", value=app_settings.get("ondotori_id", ""))
o_pass = st.sidebar.text_input("パスワード", value=app_settings.get("ondotori_pass", ""), type="password")

if (o_api != app_settings.get("ondotori_api", "") or 
    o_id != app_settings.get("ondotori_id", "") or 
    o_pass != app_settings.get("ondotori_pass", "")):
    
    app_settings["ondotori_api"] = o_api
    app_settings["ondotori_id"] = o_id
    app_settings["ondotori_pass"] = o_pass
    save_app_settings(app_settings)

st.sidebar.divider()

st.sidebar.subheader("1. 図面のアップロード")
uploaded_file = st.sidebar.file_uploader(f"「{current_floor}」の図面を選択 (PDFも可)", type=["png", "jpg", "jpeg", "pdf"])

if uploaded_file is not None:
    file_key = f"{current_floor}_{uploaded_file.file_id}"
    if "processed_file_id" not in st.session_state or st.session_state.processed_file_id != file_key:
        try:
            if uploaded_file.name.lower().endswith(".pdf"):
                doc = fitz.open(stream=uploaded_file.getvalue(), filetype="pdf")
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            else:
                image = Image.open(uploaded_file)
            
            image.save(BG_IMAGE_FILE, format="PNG")
            st.session_state.processed_file_id = file_key
            st.sidebar.success(f"「{current_floor}」の図面を読み込みました！")
        except Exception as e:
            st.sidebar.error(f"図面の読み込みに失敗しました: {e}")

bg_b64 = None
img_w, img_h = 1200, 800

if os.path.exists(BG_IMAGE_FILE):
    try:
        img = Image.open(BG_IMAGE_FILE)
        img.verify()
        img = Image.open(BG_IMAGE_FILE)
        img.load() 
        img_w, img_h = img.size
        with open(BG_IMAGE_FILE, "rb") as f:
            bg_b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        try: os.remove(BG_IMAGE_FILE)
        except: pass
        st.warning(f"⚠️ 「{current_floor}」の図面データがありません。アップロードしてください。")
        bg_b64 = None
        img_w, img_h = 1200, 800

st.sidebar.divider()

st.sidebar.subheader("2. 機器の登録・管理")
with st.sidebar.expander(f"➕ 「{current_floor}」に機器を登録", expanded=False):
    new_serial = st.text_input("シリアル番号 (例: 5214A123)")
    mode_options = {"両方表示 (ch1 & ch2)": "all", "ch1のみ表示": "ch1", "ch2のみ表示": "ch2"}
    selected_mode_label = st.selectbox("表示タイプ", list(mode_options.keys()))
    new_name = st.text_input("画面に表示する名前 (例: 6m地点)")

    if st.button("登録・更新する"):
        if new_serial and new_name:
            mode = mode_options[selected_mode_label]
            new_key = f"ondotori_{new_serial}_{mode}"
            settings[new_key] = {"source": "ondotori", "serial": new_serial, "name": new_name, "x": img_w // 2, "y": img_h // 2, "mode": mode}
            save_settings(settings)
            st.success(f"{new_name} を登録しました！")
            st.rerun()
        else:
            st.warning("必要な情報をすべて入力してください。")

if settings:
    with st.sidebar.expander("🗑️ 登録済みの機器を削除", expanded=False):
        def format_del_label(k):
            info = settings[k]
            return f"{info['name']} ({info['serial']})"
        
        del_key = st.selectbox("削除する機器を選択", options=list(settings.keys()), format_func=format_del_label, key="del_device_select")
        if st.button("この機器を削除"):
            del settings[del_key]
            save_settings(settings)
            st.success("削除しました！")
            st.rerun()

st.sidebar.divider()

st.sidebar.subheader("3. 測定ポイントの位置調整")
selected_key = None
if settings:
    selected_key = st.sidebar.selectbox("動かしたいポイントを選択", options=list(settings.keys()), format_func=lambda x: settings[x]["name"], key="move_device_select")
    
    max_x = max(img_w, 1)
    max_y = max(img_h, 1)
    current_x = min(settings[selected_key]["x"], max_x)
    current_y = min(settings[selected_key]["y"], max_y)

    slider_key_x = f"x_{current_floor}_{selected_key}"
    slider_key_y = f"y_{current_floor}_{selected_key}"

    def update_position():
        settings[selected_key]["x"] = st.session_state[slider_key_x]
        settings[selected_key]["y"] = st.session_state[slider_key_y]
        save_settings(settings)

    st.sidebar.slider("X座標 (横)", 0, max_x, current_x, key=slider_key_x, on_change=update_position)
    st.sidebar.slider("Y座標 (縦)", 0, max_y, current_y, key=slider_key_y, on_change=update_position)

# ==========================================
# UI: メイン画面（モニター表示）
# ==========================================
if st.session_state.monitor_mode:
    # ★ 究極の全画面化CSS ★
    st.markdown("""
    <style>
        /* サイドバー、ヘッダー、フッターを完全に非表示 */
        [data-testid="stSidebar"] {display: none !important;}
        [data-testid="collapsedControl"] {display: none !important;}
        header {display: none !important;}
        footer {display: none !important;}
        
        /* メイン画面の余白を完全にゼロにする */
        .block-container {
            padding: 0 !important; 
            max-width: 100% !important;
            margin: 0 !important;
        }
        
        /* 戻るボタンを右下に小さく半透明で固定配置 */
        div[data-testid="stButton"] {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 9999;
            opacity: 0.2;
            transition: opacity 0.3s;
        }
        div[data-testid="stButton"]:hover {
            opacity: 1.0;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # タイトルは表示せず、戻るボタンだけを配置
    if st.button("⚙️ 設定に戻る (F11でブラウザ全画面)"):
        st.session_state.monitor_mode = False
        st.rerun()
else:
    st.title(f"📡 リアルタイム温湿度モニター - {current_floor}")

current_data_ondotori = {}

with st.spinner("最新データを取得中..."):
    ondotori_serials = list(set([info["serial"] for info in settings.values() if info.get("source", "ondotori") == "ondotori"]))
    if ondotori_serials:
        current_data_ondotori = fetch_ondotori_data(app_settings.get("ondotori_api"), app_settings.get("ondotori_id"), app_settings.get("ondotori_pass"), ondotori_serials)
        if "error" in current_data_ondotori:
            st.error(f"おんどとり取得エラー: {current_data_ondotori['error']}")

def get_color(unit):
    if "C" in unit or "℃" in unit: return "#d32f2f"
    if "%" in unit or "rh" in unit.lower(): return "#1976d2"
    if "V" in unit or "mV" in unit: return "#2e7d32"
    return "#333333"

if bg_b64:
    if st.session_state.monitor_mode:
        # 全画面モード：画面いっぱいに広げ、アスペクト比を維持して中央配置
        html_content = f'''
        <div style="display: flex; justify-content: center; align-items: center; width: 100%; height: 100vh; background-color: #e0e0e0;">
            <div style="position: relative; max-width: 100%; max-height: 100%; aspect-ratio: {img_w} / {img_h};">
                <img src="data:image/png;base64,{bg_b64}" style="width: 100%; height: 100%; display: block; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
        '''
    else:
        # 通常モード：今まで通り
        html_content = f'''
        <div style="position: relative; display: inline-block; width: 100%; max-width: {img_w}px;">
            <img src="data:image/png;base64,{bg_b64}" style="width: 100%; height: auto; border: 1px solid #ccc;">
        '''
    
    if settings:
        for key, info in settings.items():
            x, y = info["x"], info["y"]
            
            left_pct = (x / img_w) * 100
            top_pct = (y / img_h) * 100
            
            border_color = "#ff4b4b" if key == selected_key and not st.session_state.monitor_mode else "#aaa"
            box_shadow = "0 4px 12px rgba(255, 75, 75, 0.6)" if key == selected_key and not st.session_state.monitor_mode else "0 2px 6px rgba(0,0,0,0.2)"
            
            content_html = ""
            last_update = "--"
            
            serial = info["serial"]
            mode = info.get("mode", "all")
            
            ch1_val = current_data_ondotori.get(serial, {}).get("ch1_val", "--")
            ch1_unit = current_data_ondotori.get(serial, {}).get("ch1_unit", "℃")
            ch2_val = current_data_ondotori.get(serial, {}).get("ch2_val", "--")
            ch2_unit = current_data_ondotori.get(serial, {}).get("ch2_unit", "%")
            last_update = current_data_ondotori.get(serial, {}).get("last_update", "--")
            
            ch1_color = get_color(ch1_unit)
            ch2_color = get_color(ch2_unit)
            
            ch1_html = f'<div style="color: {ch1_color}; font-weight: bold; font-size: 1.1em;">{ch1_val}<span style="font-size: 0.8em;">{ch1_unit}</span></div>' if ch1_val != "--" else ""
            ch2_html = f'<div style="color: {ch2_color}; font-weight: bold; font-size: 1.1em;">{ch2_val}<span style="font-size: 0.8em;">{ch2_unit}</span></div>' if ch2_val != "--" else ""
            ch2_only_html = f'<div style="color: {ch2_color}; font-weight: bold; font-size: 1.1em;">{ch2_val}<span style="font-size: 0.8em;">{ch2_unit}</span></div>' if ch2_val != "--" else ""
            
            if mode == "ch1": content_html = ch1_html
            elif mode == "ch2": content_html = ch2_only_html
            else: content_html = ch1_html + ch2_html
            
            card_html = (
                f'<div style="position: absolute; left: {left_pct}%; top: {top_pct}%; transform: translate(-50%, -50%); '
                f'background-color: rgba(255, 255, 255, 0.9); border: 2px solid {border_color}; border-radius: 8px; '
                f'padding: 6px 10px; box-shadow: {box_shadow}; text-align: center; min-width: 80px; z-index: 10;">'
                f'<div style="font-size: 0.75em; color: #555; margin-bottom: 2px; border-bottom: 1px solid #ddd; padding-bottom: 2px;">{info["name"]}</div>'
                f'<div style="line-height: 1.2;">{content_html}</div>'
                f'<div style="font-size: 0.65em; color: #888; margin-top: 4px;">{last_update}</div>'
                f'</div>'
            )
            html_content += card_html

    html_content += "</div>"
    if st.session_state.monitor_mode:
        html_content += "</div>"
        
    st.markdown(html_content, unsafe_allow_html=True)
else:
    st.info(f"※左のメニューから「{current_floor}」の図面(画像またはPDF)をアップロードしてください")

st.markdown('<br><br>', unsafe_allow_html=True)
