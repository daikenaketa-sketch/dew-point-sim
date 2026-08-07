import streamlit as st
import base64
from PIL import Image
import datetime
import json
import os
import requests
import fitz  # PDFを読み込むためのツール(PyMuPDF)

st.set_page_config(page_title="リアルタイム温湿度モニター", layout="wide")

# ==========================================
# 🌟 新機能：複数フロア（図面）の管理
# ==========================================
FLOORS_FILE = "floors.json"

def load_floors():
    if os.path.exists(FLOORS_FILE):
        with open(FLOORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["メイン"]

def save_floors(floors):
    with open(FLOORS_FILE, "w", encoding="utf-8") as f:
        json.dump(floors, f, ensure_ascii=False, indent=4)

floors = load_floors()

# 💡 今まで作ったデータを「メイン」として自動引き継ぎする処理
if os.path.exists("monitor_settings.json") and not os.path.exists("settings_メイン.json"):
    os.rename("monitor_settings.json", "settings_メイン.json")
if os.path.exists("monitor_bg.png") and not os.path.exists("bg_メイン.png"):
    os.rename("monitor_bg.png", "bg_メイン.png")

# ==========================================
# UI: サイドバー（フロア選択）
# ==========================================
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
        elif new_floor_name in floors:
            st.warning("その名前は既に存在します。")

with st.sidebar.expander("🗑️ 現在のフロアを削除"):
    if len(floors) > 1:
        if st.button(f"「{current_floor}」を削除"):
            floors.remove(current_floor)
            save_floors(floors)
            if os.path.exists(f"settings_{current_floor}.json"): os.remove(f"settings_{current_floor}.json")
            if os.path.exists(f"bg_{current_floor}.png"): os.remove(f"bg_{current_floor}.png")
            st.success("削除しました！")
            st.rerun()
    else:
        st.info("最後の1つは削除できません。")

st.sidebar.divider()

# ==========================================
# 内部処理（選択中のフロアに応じたファイル設定）
# ==========================================
SETTINGS_FILE = f"settings_{current_floor}.json"
BG_IMAGE_FILE = f"bg_{current_floor}.png"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

settings = load_settings()

@st.cache_data(ttl=300)
def fetch_ondotori_data(api_key, login_id, login_pass, settings_keys):
    url = "https://api.webstorage.jp/v1/devices/current"
    headers = {
        "X-HTTP-Method-Override": "GET",
        "Content-Type": "application/json"
    }
    payload = {
        "api-key": api_key,
        "login-id": login_id,
        "login-pass": login_pass
    }

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
                    except (ValueError, TypeError):
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
        try:
            os.remove(BG_IMAGE_FILE)
        except:
            pass
        st.warning(f"⚠️ 「{current_floor}」の図面データがありません。アップロードしてください。")
        bg_b64 = None
        img_w, img_h = 1200, 800

st.sidebar.divider()

st.sidebar.subheader("2. 機器の登録・管理")
with st.sidebar.expander(f"➕ 「{current_floor}」に機器を登録", expanded=False):
    new_serial = st.text_input("シリアル番号 (例: 5214A123)")
    new_name = st.text_input("画面に表示する名前 (例: 体育館)")
    if st.button("登録・更新する"):
        if new_serial and new_name:
            if new_serial not in settings:
                settings[new_serial] = {"name": new_name, "x": img_w // 2, "y": img_h // 2}
            else:
                settings[new_serial]["name"] = new_name
            save_settings(settings)
            st.success(f"{new_name} を登録しました！")
            st.rerun()
        else:
            st.warning("シリアル番号と名前の両方を入力してください。")

if settings:
    with st.sidebar.expander("🗑️ 登録済みの機器を削除", expanded=False):
        del_serial = st.selectbox("削除する機器を選択", options=list(settings.keys()), format_func=lambda x: f"{settings[x]['name']} ({x})")
        if st.button("この機器を削除"):
            del settings[del_serial]
            save_settings(settings)
            st.success("削除しました！")
            st.rerun()

st.sidebar.divider()

st.sidebar.subheader("3. 測定ポイントの位置調整")
selected_serial = None
if settings:
    selected_serial = st.sidebar.selectbox("動かしたいポイントを選択", options=list(settings.keys()), format_func=lambda x: settings[x]["name"])
    
    max_x = max(img_w, 1)
    max_y = max(img_h, 1)
    current_x = min(settings[selected_serial]["x"], max_x)
    current_y = min(settings[selected_serial]["y"], max_y)

    new_x = st.sidebar.slider("X座標 (横)", 0, max_x, current_x, key=f"x_{current_floor}_{selected_serial}")
    new_y = st.sidebar.slider("Y座標 (縦)", 0, max_y, current_y, key=f"y_{current_floor}_{selected_serial}")

    if new_x != settings[selected_serial]["x"] or new_y != settings[selected_serial]["y"]:
        settings[selected_serial]["x"] = new_x
        settings[selected_serial]["y"] = new_y
        save_settings(settings)
else:
    st.sidebar.info("先に「2. 機器の登録」を行ってください。")

# ==========================================
# UI: メイン画面（モニター表示）
# ==========================================
st.title(f"📡 リアルタイム温湿度モニター - {current_floor}")

current_data = None
try:
    api_key = st.secrets["ondotori"]["api_key"]
    login_id = st.secrets["ondotori"]["login_id"]
    login_pass = st.secrets["ondotori"]["login_pass"]
    
    with st.spinner("おんどとりから最新データを取得中..."):
        settings_keys = tuple(settings.keys())
        current_data = fetch_ondotori_data(api_key, login_id, login_pass, settings_keys)
        
        if current_data and "error" in current_data:
            st.error(f"データ取得エラー: {current_data['error']}")
            current_data = None
except KeyError:
    st.error("⚠️ APIキーが設定されていません。Streamlit CloudのSecretsを設定してください。")

if bg_b64:
    html_content = f'<div style="position: relative; width: 100%; max-width: {img_w}px; margin: 0 auto; border: 1px solid #ccc;"><img src="data:image/png;base64,{bg_b64}" style="width: 100%; height: auto; display: block;" />'
    
    if current_data and settings:
        for serial, info in settings.items():
            x, y = info["x"], info["y"]
            
            left_pct = (x / img_w) * 100
            top_pct = (y / img_h) * 100
            
            ch1_val = current_data.get(serial, {}).get("ch1_val", "--")
            ch1_unit = current_data.get(serial, {}).get("ch1_unit", "℃")
            ch2_val = current_data.get(serial, {}).get("ch2_val", "--")
            ch2_unit = current_data.get(serial, {}).get("ch2_unit", "%")
            last_update = current_data.get(serial, {}).get("last_update", "--")
            
            border_color = "#ff4b4b" if serial == selected_serial else "#aaa"
            box_shadow = "0 4px 12px rgba(255, 75, 75, 0.6)" if serial == selected_serial else "0 2px 6px rgba(0,0,0,0.2)"
            
            def get_color(unit):
                if "C" in unit or "℃" in unit: return "#d32f2f" # 赤色
                if "%" in unit or "rh" in unit.lower(): return "#1976d2" # 青色
                return "#333333" # その他は黒
                
            ch1_color = get_color(ch1_unit)
            ch2_color = get_color(ch2_unit)
            
            ch1_html = f'<div style="font-size: 20px; font-weight: bold; color: {ch1_color}; line-height: 1.1;">{ch1_val}<span style="font-size: 12px; font-weight: normal; margin-left: 2px;">{ch1_unit}</span></div>' if ch1_val != "--" else ""
            ch2_html = f'<div style="font-size: 20px; font-weight: bold; color: {ch2_color}; line-height: 1.1; margin-top: 2px;">{ch2_val}<span style="font-size: 12px; font-weight: normal; margin-left: 2px;">{ch2_unit}</span></div>' if ch2_val != "--" else ""
            
            card_html = f'<div style="position: absolute; left: {left_pct}%; top: {top_pct}%; transform: translate(-50%, -50%); background-color: rgba(255, 255, 255, 0.95); border: 2px solid {border_color}; border-radius: 6px; padding: 4px 8px; box-shadow: {box_shadow}; text-align: center; min-width: 80px; z-index: 10; white-space: nowrap;"><div style="font-size: 12px; font-weight: bold; color: #333; border-bottom: 1px solid #ccc; padding-bottom: 2px; margin-bottom: 4px;">{info["name"]}</div>{ch1_html}{ch2_html}<div style="font-size: 10px; color: #888; margin-top: 4px;">{last_update}</div></div>'
            html_content += card_html

    html_content += "</div>"
    st.markdown(html_content, unsafe_allow_html=True)
else:
    st.info(f"※左のメニューから「{current_floor}」の図面(画像またはPDF)をアップロードしてください")

st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)
