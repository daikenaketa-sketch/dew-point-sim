import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import datetime
import json
import os
import requests

st.set_page_config(page_title="リアルタイム温湿度モニター", layout="wide")

# ==========================================
# 内部処理（ファイル保存・API取得）
# ==========================================
SETTINGS_FILE = "monitor_settings.json"
BG_IMAGE_FILE = "current_bg.png"

# 設定（機器情報と座標）を読み込む
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {} # 初期状態は空っぽ

# 設定を保存する
def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

settings = load_settings()

# おんどとりAPIからデータを取得する関数
def fetch_ondotori_data():
    try:
        api_key = st.secrets["ondotori"]["api_key"]
        login_id = st.secrets["ondotori"]["login_id"]
        login_pass = st.secrets["ondotori"]["login_pass"]
    except KeyError:
        st.error("⚠️ APIキーが設定されていません。Streamlit CloudのSecretsを設定してください。")
        return None

    # 修正箇所：正しいAPIのURLとヘッダー
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
            # 登録されているシリアル番号のデータだけを抽出
            if serial in settings:
                channels = device.get("channel", [])
                temp = next((ch["value"] for ch in channels if ch["num"] == 1), "--")
                rh = next((ch["value"] for ch in channels if ch["num"] == 2), "--")
                display_data[serial] = {"temp": temp, "rh": rh}
        return display_data
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return None

# ==========================================
# UI: サイドバー（管理者メニュー）
# ==========================================
st.sidebar.header("⚙️ 管理者メニュー")

# 1. 画像アップロード
st.sidebar.subheader("1. 図面のアップロード")
uploaded_file = st.sidebar.file_uploader("新しい図面画像を選択", type=["png", "jpg", "jpeg"])
if uploaded_file is not None:
    image = Image.open(uploaded_file)
    image.save(BG_IMAGE_FILE)
    st.sidebar.success("図面を更新しました！")

st.sidebar.divider()

# 2. 機器（おんどとり）の登録・削除
st.sidebar.subheader("2. 機器の登録・管理")
with st.sidebar.expander("➕ 新しい機器を登録 / 編集", expanded=False):
    new_serial = st.text_input("シリアル番号 (例: 5214A123)")
    new_name = st.text_input("画面に表示する名前 (例: 体育館)")
    if st.button("登録・更新する"):
        if new_serial and new_name:
            if new_serial not in settings:
                # 新規登録の場合は初期座標を(100, 100)にする
                settings[new_serial] = {"name": new_name, "x": 100, "y": 100}
            else:
                # 既存の場合は名前だけ更新
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
if settings:
    selected_serial = st.sidebar.selectbox("動かしたいポイントを選択", options=list(settings.keys()), format_func=lambda x: settings[x]["name"])
    
    new_x = st.sidebar.slider("X座標 (横)", 0, 2000, settings[selected_serial]["x"])
    new_y = st.sidebar.slider("Y座標 (縦)", 0, 2000, settings[selected_serial]["y"])

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

now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
st.info(f"🔄 最終データ更新: **{now_str}** （5分ごとに自動更新されます）")

with st.spinner("おんどとりから最新データを取得中..."):
    current_data = fetch_ondotori_data()

# 画像の描画処理
if os.path.exists(BG_IMAGE_FILE):
    img = Image.open(BG_IMAGE_FILE).convert("RGBA")
else:
    img = Image.new("RGBA", (1200, 800), (240, 240, 240, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "※左のメニューから図面画像をアップロードしてください", fill="black")

draw = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("arial.ttf", 24)
except IOError:
    font = ImageFont.load_default()

# データを画像に書き込む
if current_data and settings:
    for serial, info in settings.items():
        x, y = info["x"], info["y"]
        point_name = info["name"]
        
        if serial in current_data:
            temp = current_data[serial]["temp"]
            rh = current_data[serial]["rh"]
            text = f"{point_name}\n{temp}℃ / {rh}%"
            
            # 選択中のポイントは赤枠にする
            is_selected = (settings and serial == selected_serial)
            outline_color = "red" if is_selected else "black"
            text_color = "red" if is_selected else "black"
            
            bbox = draw.textbbox((x, y), text, font=font)
            draw.rectangle([bbox[0]-5, bbox[1]-5, bbox[2]+5, bbox[3]+5], fill=(255, 255, 255, 220), outline=outline_color, width=2)
            draw.text((x, y), text, fill=text_color, font=font)

st.image(img, use_container_width=True)

# 5分(300秒)ごとにページを自動リロード
st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)
