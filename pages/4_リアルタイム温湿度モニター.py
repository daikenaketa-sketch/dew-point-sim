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
# 内部処理（ファイル保存・API取得）
# ==========================================
SETTINGS_FILE = "monitor_settings.json"
BG_IMAGE_FILE = "current_bg.png"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

settings = load_settings()

# データを5分間記憶する（スライダーのラグ防止）
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
                temp = next((ch["value"] for ch in channels if ch["num"] == 1), "--")
                rh = next((ch["value"] for ch in channels if ch["num"] == 2), "--")
                
                # 🌟 最終更新日時を取得して日本時間に変換
                unixtime = device.get("unixtime")
                if unixtime:
                    dt = datetime.datetime.utcfromtimestamp(unixtime) + datetime.timedelta(hours=9)
                    last_update = dt.strftime('%m/%d %H:%M')
                else:
                    last_update = "--"
                    
                display_data[serial] = {"temp": temp, "rh": rh, "last_update": last_update}
        return display_data
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# 画像サイズの取得とBase64化（HTML描画用）
# ==========================================
if os.path.exists(BG_IMAGE_FILE):
    img = Image.open(BG_IMAGE_FILE)
    img_w, img_h = img.size
    with open(BG_IMAGE_FILE, "rb") as f:
        bg_b64 = base64.b64encode(f.read()).decode()
else:
    img_w, img_h = 1200, 800
    bg_b64 = None

# ==========================================
# UI: サイドバー（管理者メニュー）
# ==========================================
st.sidebar.header("⚙️ 管理者メニュー")

# 1. 画像・PDFアップロード
st.sidebar.subheader("1. 図面のアップロード")
uploaded_file = st.sidebar.file_uploader("新しい図面を選択 (PDFも可)", type=["png", "jpg", "jpeg", "pdf"])

if uploaded_file is not None:
    if uploaded_file.name.lower().endswith(".pdf"):
        try:
            doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            image.save(BG_IMAGE_FILE)
            st.sidebar.success("PDFを図面として読み込みました！")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"PDFの読み込みに失敗しました: {e}")
    else:
        image = Image.open(uploaded_file)
        image.save(BG_IMAGE_FILE)
        st.sidebar.success("図面を更新しました！")
        st.rerun()

st.sidebar.divider()

# 2. 機器（おんどとり）の登録・削除
st.sidebar.subheader("2. 機器の登録・管理")
with st.sidebar.expander("➕ 新しい機器を登録 / 編集", expanded=False):
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

# 3. 座標調整スライダー
st.sidebar.subheader("3. 測定ポイントの位置調整")
selected_serial = None
if settings:
    selected_serial = st.sidebar.selectbox("動かしたいポイントを選択", options=list(settings.keys()), format_func=lambda x: settings[x]["name"])
    
    # スライダーの最大値を画像の実際のサイズに合わせる
    max_x = max(img_w, 1)
    max_y = max(img_h, 1)
    current_x = min(settings[selected_serial]["x"], max_x)
    current_y = min(settings[selected_serial]["y"], max_y)

    new_x = st.sidebar.slider("X座標 (横)", 0, max_x, current_x)
    new_y = st.sidebar.slider("Y座標 (縦)", 0, max_y, current_y)

    if new_x != settings[selected_serial]["x"] or new_y != settings[selected_serial]["y"]:
        settings[selected_serial]["x"] = new_x
        settings[selected_serial]["y"] = new_y
        save_settings(settings)
else:
    st.sidebar.info("先に「2. 機器の登録」を行ってください。")

# ==========================================
# UI: メイン画面（モニター表示）
# ==========================================
st.title("📡 リアルタイム温湿度モニター")

# APIキーの取得とデータフェッチ
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

# 🌟 HTMLとCSSを使って、画像の上にダッシュボード風のカードを重ねて描画する
if bg_b64:
    html_content = f"""
    <div style="position: relative; width: 100%; max-width: {img_w}px; margin: 0 auto; border: 1px solid #ccc;">
        <img src="data:image/png;base64,{bg_b64}" style="width: 100%; height: auto; display: block;" />
    """
    
    if current_data and settings:
        for serial, info in settings.items():
            x, y = info["x"], info["y"]
            
            # 座標をパーセンテージに変換（画面サイズが変わってもズレないようにする）
            left_pct = (x / img_w) * 100
            top_pct = (y / img_h) * 100
            
            temp = current_data.get(serial, {}).get("temp", "--")
            rh = current_data.get(serial, {}).get("rh", "--")
            last_update = current_data.get(serial, {}).get("last_update", "--")
            
            # 選択中のポイントは枠線を赤くする
            border_color = "#ff4b4b" if serial == selected_serial else "#ddd"
            box_shadow = "0 8px 16px rgba(255, 75, 75, 0.4)" if serial == selected_serial else "0 4px 8px rgba(0,0,0,0.15)"
            
            # ダッシュボード風のカードデザイン
            card_html = f"""
            <div style="
                position: absolute; 
                left: {left_pct}%; 
                top: {top_pct}%; 
                transform: translate(-50%, -50%);
                background-color: rgba(255, 255, 255, 0.95);
                border: 3px solid {border_color};
                border-radius: 10px;
                padding: 10px 15px;
                box-shadow: {box_shadow};
                text-align: center;
                min-width: 140px;
                z-index: 10;
                white-space: nowrap;
            ">
                <div style="font-size: 14px; font-weight: bold; color: #333; border-bottom: 1px solid #eee; padding-bottom: 4px; margin-bottom: 8px;">
                    {info['name']}
                </div>
                <div style="font-size: 32px; font-weight: bold; color: #000; line-height: 1.1;">
                    {temp}<span style="font-size: 16px; font-weight: normal; color: #666;">℃</span>
                </div>
                <div style="font-size: 22px; font-weight: bold; color: #000; line-height: 1.1; margin-top: 4px;">
                    {rh}<span style="font-size: 14px; font-weight: normal; color: #666;">%</span>
                </div>
                <div style="font-size: 11px; color: #888; margin-top: 8px;">
                    最終更新: {last_update}
                </div>
            </div>
            """
            html_content += card_html

    html_content += "</div>"
    st.markdown(html_content, unsafe_allow_html=True)
else:
    st.info("※左のメニューから図面(画像またはPDF)をアップロードしてください")

# 5分(300秒)ごとにページを自動リロード
st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)
