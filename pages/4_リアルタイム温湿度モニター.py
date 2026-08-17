import streamlit as st
import base64
from PIL import Image
import datetime
import json
import os
import glob
import requests
import fitz  # PDFを読み込むためのツール(PyMuPDF)
import shutil
import tempfile

st.set_page_config(page_title="リアルタイム温湿度モニター", layout="wide")

# ==========================================
# 初期設定
# ==========================================
if "monitor_mode" not in st.session_state:
    st.session_state.monitor_mode = False

# ==========================================
# アプリ全体の設定管理（フォルダパスの記憶用）
# ==========================================
APP_SETTINGS_FILE = "app_settings.json"

def load_app_settings():
    if os.path.exists(APP_SETTINGS_FILE):
        try:
            with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"gl840_dir": "gl840_data"}

def save_app_settings(settings):
    with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

app_settings = load_app_settings()

# ==========================================
# 複数フロア（図面）の管理
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

if os.path.exists("monitor_settings.json") and not os.path.exists("settings_メイン.json"):
    os.rename("monitor_settings.json", "settings_メイン.json")
if os.path.exists("monitor_bg.png") and not os.path.exists("bg_メイン.png"):
    os.rename("monitor_bg.png", "bg_メイン.png")

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
# 内部処理（設定ファイルの読み書き）
# ==========================================
SETTINGS_FILE = f"settings_{current_floor}.json"
BG_IMAGE_FILE = f"bg_{current_floor}.png"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            new_data = {}
            changed = False
            for k, v in data.items():
                if "source" not in v:
                    v["source"] = "ondotori"
                    changed = True
                if "serial" not in v and v["source"] == "ondotori":
                    new_key = f"{k}_all"
                    new_data[new_key] = {"source": "ondotori", "serial": k, "name": v["name"], "x": v["x"], "y": v["y"], "mode": "all"}
                    changed = True
                else:
                    new_data[k] = v
            if changed:
                with open(SETTINGS_FILE, "w", encoding="utf-8") as fw:
                    json.dump(new_data, fw, ensure_ascii=False, indent=4)
            return new_data
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

@st.cache_data(ttl=60) # GL840はローカルなので1分更新
def fetch_gl840_data(folder_path):
    # パスの前後の引用符を削除（コピペ対策）
    folder_path = folder_path.strip('\'"')
    
    if not os.path.exists(folder_path):
        return {"error": f"指定されたフォルダ '{folder_path}' が見つかりません。"}
        
    # サブフォルダも含めて再帰的にCSVを検索（大文字・小文字対応）
    csv_files = glob.glob(os.path.join(folder_path, "**", "*.csv"), recursive=True)
    csv_files.extend(glob.glob(os.path.join(folder_path, "**", "*.CSV"), recursive=True))
    
    if not csv_files:
        return {"error": f"'{folder_path}' 内（サブフォルダ含む）にCSVファイルが見つかりません。"}
    
    # 最新のCSVファイルを取得
    latest_file = max(csv_files, key=os.path.getctime)
    
    try:
        # 記録中でファイルがロック（読み取り専用）されている場合を回避するため、
        # 一時ファイルにコピーしてから読み込む
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "temp_gl840_read.csv")
        
        try:
            shutil.copy2(latest_file, temp_file)
            target_file = temp_file
        except Exception:
            # コピーすらできない場合は直接読み込みを試みる
            target_file = latest_file

        with open(target_file, "r", encoding="shift_jis", errors="replace") as f:
            lines = f.readlines()
            
        if target_file == temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
            
        header_idx = -1
        for i, line in enumerate(lines):
            # グラフテックのデータ開始行を特定
            if line.startswith("番号,日付 時間,ms,") or line.startswith("NO.,Time,ms,"):
                header_idx = i
                break
                
        if header_idx == -1 or len(lines) <= header_idx + 2:
            return {"error": "CSVのフォーマットが異なります（データ行が見つかりません）。"}
            
        headers = lines[header_idx].strip().split(",")
        units = lines[header_idx + 1].strip().split(",")
        
        # データ行のみを抽出（空行を除外）
        data_lines = [l.strip() for l in lines[header_idx+2:] if l.strip()]
        if not data_lines:
            return {"error": "データが記録されていません。"}
            
        # 一番最後の行（最新データ）を取得
        latest_data = data_lines[-1].split(",")
        time_str = latest_data[1] # 日付 時間の列
        
        try:
            # 時刻フォーマットの吸収 (2025/9/1 17:22:09 または 2025-09-01 17:22:09)
            time_str_clean = time_str.replace("/", "-")
            dt = datetime.datetime.strptime(time_str_clean, "%Y-%m-%d %H:%M:%S")
            formatted_time = dt.strftime("%m/%d %H:%M")
        except:
            formatted_time = time_str
            
        result = {}
        for i, col_name in enumerate(headers):
            if col_name.startswith("CH"):
                if i < len(latest_data):
                    val = latest_data[i]
                    
                    # 単位のクリーニング（文字化けや表記ブレを吸収）
                    unit = ""
                    if i < len(units):
                        raw_unit = units[i].strip()
                        if "C" in raw_unit or "℃" in raw_unit or "ﾟC" in raw_unit:
                            unit = "℃"
                        elif "mV" in raw_unit:
                            unit = "mV"
                        elif "V" in raw_unit:
                            unit = "V"
                        elif "%" in raw_unit or "RH" in raw_unit.upper():
                            unit = "%"
                        else:
                            unit = raw_unit.replace("·", "").strip()
                            
                    result[col_name] = {
                        "val": val,
                        "unit": unit,
                        "time": formatted_time
                    }
        return result
    except Exception as e:
        return {"error": f"ファイルの読み込みエラー: {str(e)}"}

# ==========================================
# UI: サイドバー（管理者メニュー）
# ==========================================
st.sidebar.header("⚙️ 管理者メニュー")

# --- GL840 フォルダ設定 ---
st.sidebar.subheader("📁 ローカルデータ設定 (GL840)")
input_gl840_dir = st.sidebar.text_input(
    "GL840 CSVフォルダのパス", 
    value=app_settings.get("gl840_dir", "gl840_data"), 
    help="測定ロガーがCSVを保存するPC上の絶対パス（例: C:\\Users\\Name\\Documents\\GL840）を指定してください。"
)

# 入力されたパスが変更されたら設定ファイルに保存する
if input_gl840_dir != app_settings.get("gl840_dir", "gl840_data"):
    app_settings["gl840_dir"] = input_gl840_dir
    save_app_settings(app_settings)

gl840_dir = app_settings.get("gl840_dir", "gl840_data")

if not os.path.exists(gl840_dir):
    try:
        os.makedirs(gl840_dir, exist_ok=True)
    except:
        pass # 権限エラー等の場合は無視（メイン画面でエラー表示される）

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
    source_options = ["おんどとり (クラウド)", "GL840 (ローカルCSV)"]
    selected_source = st.selectbox("データソース", source_options)
    
    if selected_source == "おんどとり (クラウド)":
        new_serial = st.text_input("シリアル番号 (例: 5214A123)")
        mode_options = {"両方表示 (ch1 & ch2)": "all", "ch1のみ表示": "ch1", "ch2のみ表示": "ch2"}
        selected_mode_label = st.selectbox("表示タイプ", list(mode_options.keys()))
    else:
        new_ch = st.text_input("チャンネル番号 (例: CH1, CH2)")
        st.caption(f"※上の「ローカルデータ設定」で指定したフォルダ内の最新CSVからデータを読み取ります。")

    new_name = st.text_input("画面に表示する名前 (例: 6m地点)")

    if st.button("登録・更新する"):
        if selected_source == "おんどとり (クラウド)" and new_serial and new_name:
            mode = mode_options[selected_mode_label]
            new_key = f"ondotori_{new_serial}_{mode}"
            settings[new_key] = {"source": "ondotori", "serial": new_serial, "name": new_name, "x": img_w // 2, "y": img_h // 2, "mode": mode}
            save_settings(settings)
            st.success(f"{new_name} を登録しました！")
            st.rerun()
        elif selected_source == "GL840 (ローカルCSV)" and new_ch and new_name:
            new_ch = new_ch.upper().strip()
            new_key = f"gl840_{new_ch}"
            settings[new_key] = {"source": "gl840", "ch": new_ch, "name": new_name, "x": img_w // 2, "y": img_h // 2}
            save_settings(settings)
            st.success(f"{new_name} を登録しました！")
            st.rerun()
        else:
            st.warning("必要な情報をすべて入力してください。")

if settings:
    with st.sidebar.expander("🗑️ 登録済みの機器を削除", expanded=False):
        def format_del_label(k):
            info = settings[k]
            if info.get("source") == "gl840":
                return f"{info['name']} ({info['ch']})"
            else:
                return f"{info['name']} ({info['serial']})"
                
        del_key = st.selectbox("削除する機器を選択", options=list(settings.keys()), format_func=format_del_label)
        if st.button("この機器を削除"):
            del settings[del_key]
            save_settings(settings)
            st.success("削除しました！")
            st.rerun()

st.sidebar.divider()

st.sidebar.subheader("3. 測定ポイントの位置調整")
selected_key = None
if settings:
    selected_key = st.sidebar.selectbox("動かしたいポイントを選択", options=list(settings.keys()), format_func=lambda x: settings[x]["name"])
    
    max_x = max(img_w, 1)
    max_y = max(img_h, 1)
    current_x = min(settings[selected_key]["x"], max_x)
    current_y = min(settings[selected_key]["y"], max_y)

    new_x = st.sidebar.slider("X座標 (横)", 0, max_x, current_x, key=f"x_{current_floor}_{selected_key}")
    new_y = st.sidebar.slider("Y座標 (縦)", 0, max_y, current_y, key=f"y_{current_floor}_{selected_key}")

    if new_x != settings[selected_key]["x"] or new_y != settings[selected_key]["y"]:
        settings[selected_key]["x"] = new_x
        settings[selected_key]["y"] = new_y
        save_settings(settings)
else:
    st.sidebar.info("先に「2. 機器の登録」を行ってください。")

# ==========================================
# UI: メイン画面（モニター表示）
# ==========================================
if st.session_state.monitor_mode:
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {display: none !important;}
        [data-testid="collapsedControl"] {display: none !important;}
        header {visibility: hidden !important;}
        footer {visibility: hidden !important;}
        .block-container {padding-top: 1rem !important; padding-bottom: 0rem !important; max-width: 100% !important;}
        </style>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([8, 2])
    with col1:
        st.title(f"📡 リアルタイム温湿度モニター - {current_floor}")
    with col2:
        st.write("")
        if st.button("⚙️ 設定画面に戻る", use_container_width=True):
            st.session_state.monitor_mode = False
            st.rerun()
else:
    st.title(f"📡 リアルタイム温湿度モニター - {current_floor}")

current_data_ondotori = {}
current_data_gl840 = {}

with st.spinner("最新データを取得中..."):
    # おんどとりのデータ取得
    ondotori_serials = list(set([info["serial"] for info in settings.values() if info.get("source", "ondotori") == "ondotori"]))
    if ondotori_serials:
        try:
            api_key = st.secrets["ondotori"]["api_key"]
            login_id = st.secrets["ondotori"]["login_id"]
            login_pass = st.secrets["ondotori"]["login_pass"]
            current_data_ondotori = fetch_ondotori_data(api_key, login_id, login_pass, ondotori_serials)
            if "error" in current_data_ondotori:
                st.error(f"おんどとり取得エラー: {current_data_ondotori['error']}")
        except KeyError:
            st.error("⚠️ おんどとりのAPIキーが設定されていません。")

    # GL840のデータ取得
    gl840_chs = list(set([info["ch"] for info in settings.values() if info.get("source") == "gl840"]))
    if gl840_chs:
        current_data_gl840 = fetch_gl840_data(gl840_dir)
        if "error" in current_data_gl840:
            st.error(f"GL840取得エラー: {current_data_gl840['error']}")

if bg_b64:
    html_content = f'<div style="position: relative; width: 100%; max-width: {img_w}px; margin: 0 auto; border: 1px solid #ccc;"><img src="data:image/png;base64,{bg_b64}" style="width: 100%; height: auto; display: block;" />'
    
    if settings:
        for key, info in settings.items():
            source = info.get("source", "ondotori")
            x, y = info["x"], info["y"]
            
            left_pct = (x / img_w) * 100
            top_pct = (y / img_h) * 100
            
            border_color = "#ff4b4b" if key == selected_key and not st.session_state.monitor_mode else "#aaa"
            box_shadow = "0 4px 12px rgba(255, 75, 75, 0.6)" if key == selected_key and not st.session_state.monitor_mode else "0 2px 6px rgba(0,0,0,0.2)"
            
            def get_color(unit):
                if "C" in unit or "℃" in unit: return "#d32f2f" # 赤
                if "%" in unit or "rh" in unit.lower(): return "#1976d2" # 青
                if "V" in unit or "mV" in unit: return "#2e7d32" # 緑
                return "#333333"
            
            content_html = ""
            last_update = "--"
            
            if source == "ondotori":
                serial = info["serial"]
                mode = info.get("mode", "all")
                
                ch1_val = current_data_ondotori.get(serial, {}).get("ch1_val", "--")
                ch1_unit = current_data_ondotori.get(serial, {}).get("ch1_unit", "℃")
                ch2_val = current_data_ondotori.get(serial, {}).get("ch2_val", "--")
                ch2_unit = current_data_ondotori.get(serial, {}).get("ch2_unit", "%")
                last_update = current_data_ondotori.get(serial, {}).get("last_update", "--")
                
                ch1_color = get_color(ch1_unit)
                ch2_color = get_color(ch2_unit)
                
                ch1_html = f'<div style="font-size: 20px; font-weight: bold; color: {ch1_color}; line-height: 1.1;">{ch1_val}<span style="font-size: 12px; font-weight: normal; margin-left: 2px;">{ch1_unit}</span></div>' if ch1_val != "--" else ""
                ch2_html = f'<div style="font-size: 20px; font-weight: bold; color: {ch2_color}; line-height: 1.1; margin-top: 2px;">{ch2_val}<span style="font-size: 12px; font-weight: normal; margin-left: 2px;">{ch2_unit}</span></div>' if ch2_val != "--" else ""
                ch2_only_html = f'<div style="font-size: 20px; font-weight: bold; color: {ch2_color}; line-height: 1.1;">{ch2_val}<span style="font-size: 12px; font-weight: normal; margin-left: 2px;">{ch2_unit}</span></div>' if ch2_val != "--" else ""
                
                if mode == "ch1": content_html = ch1_html
                elif mode == "ch2": content_html = ch2_only_html
                else: content_html = ch1_html + ch2_html
                
            elif source == "gl840":
                ch = info["ch"]
                val = current_data_gl840.get(ch, {}).get("val", "--")
                unit = current_data_gl840.get(ch, {}).get("unit", "")
                last_update = current_data_gl840.get(ch, {}).get("time", "--")
                
                color = get_color(unit)
                content_html = f'<div style="font-size: 20px; font-weight: bold; color: {color}; line-height: 1.1;">{val}<span style="font-size: 12px; font-weight: normal; margin-left: 2px;">{unit}</span></div>' if val != "--" else ""
            
            card_html = f'<div style="position: absolute; left: {left_pct}%; top: {top_pct}%; transform: translate(-50%, -50%); background-color: rgba(255, 255, 255, 0.95); border: 2px solid {border_color}; border-radius: 6px; padding: 4px 8px; box-shadow: {box_shadow}; text-align: center; min-width: 80px; z-index: 10; white-space: nowrap;"><div style="font-size: 12px; font-weight: bold; color: #333; border-bottom: 1px solid #ccc; padding-bottom: 2px; margin-bottom: 4px;">{info["name"]}</div>{content_html}<div style="font-size: 10px; color: #888; margin-top: 4px;">{last_update}</div></div>'
            html_content += card_html

    html_content += "</div>"
    st.markdown(html_content, unsafe_allow_html=True)
else:
    st.info(f"※左のメニューから「{current_floor}」の図面(画像またはPDF)をアップロードしてください")

st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
