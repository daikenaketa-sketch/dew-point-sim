import streamlit as st
import pandas as pd

# --- ページ設定 ---
st.set_page_config(page_title="空調立上り時間シミュレーション", layout="wide")
st.title("⏱️ 空調立上り時間（プルダウン/プルアップ）シミュレーション")
st.markdown("熱負荷計算書と空調機の能力から、目標温度に達するまでの時間を簡易推定します。")

# --- 計算ロジック関数 ---
def calculate_startup_time(mode, volume_m3, steady_load_w, ac_capacity_w, t_start, t_target, furniture_factor, shr, inverter_boost):
    # 物理定数
    rho_air = 1.2  # 空気の密度 [kg/m3]
    c_air = 1006   # 空気の比熱 [J/kg・K]
    
    # 室内の等価熱容量 [J/K]
    c_room = volume_m3 * rho_air * c_air * furniture_factor
    
    # 空調の有効能力 [W] (暖房時は潜熱処理がないため顕熱比1.0とする)
    if mode == "冷房":
        effective_ac_capacity = ac_capacity_w * inverter_boost * shr
    else:
        effective_ac_capacity = ac_capacity_w * inverter_boost * 1.0
        
    current_temp = t_start
    time_seconds = 0
    dt = 60  # 1分(60秒)ごとに計算
    temp_history = [{"経過時間 (分)": 0, "室温 (℃)": current_temp}]
    
    # 余剰能力 = 空調能力 - 定常熱負荷
    net_power = effective_ac_capacity - steady_load_w
    
    if net_power <= 0:
        return None, None, "エラー: 空調能力が定常熱負荷を下回っている（または等しい）ため、目標温度に到達しません。"
        
    # シミュレーションループ
    if mode == "冷房":
        if t_start <= t_target:
            return 0, temp_history, None
        while current_temp > t_target:
            delta_t = (net_power * dt) / c_room
            current_temp -= delta_t
            time_seconds += dt
            temp_history.append({"経過時間 (分)": time_seconds / 60, "室温 (℃)": current_temp})
            if time_seconds > 86400:  # 24時間でタイムアウト
                return None, None, "エラー: 24時間以内に目標温度に到達しませんでした。"
    else:  # 暖房
        if t_start >= t_target:
            return 0, temp_history, None
        while current_temp < t_target:
            delta_t = (net_power * dt) / c_room
            current_temp += delta_t
            time_seconds += dt
            temp_history.append({"経過時間 (分)": time_seconds / 60, "室温 (℃)": current_temp})
            if time_seconds > 86400:
                return None, None, "エラー: 24時間以内に目標温度に到達しませんでした。"
                
    return time_seconds / 60, temp_history, None

# --- サイドバー：入力フォーム ---
st.sidebar.header("📝 入力条件")

mode = st.sidebar.radio("運転モード", ["冷房", "暖房"], horizontal=True)

st.sidebar.subheader("必須パラメータ")
volume_m3 = st.sidebar.number_input("室容積 (m³)", min_value=10.0, value=280.0, step=10.0, help="床面積 × 天井高")
steady_load_w = st.sidebar.number_input("定常熱負荷 (W)", min_value=100, value=10000, step=100, help="熱負荷計算書で算出された最大熱負荷")
ac_capacity_w = st.sidebar.number_input("空調機の定格能力 (W)", min_value=100, value=14000, step=100, help="カタログ記載の全能力")

if mode == "冷房":
    t_start = st.sidebar.number_input("初期室温 (℃)", value=32.0, step=0.5)
    t_target = st.sidebar.number_input("目標室温 (℃)", value=26.0, step=0.5)
else:
    t_start = st.sidebar.number_input("初期室温 (℃)", value=10.0, step=0.5)
    t_target = st.sidebar.number_input("目標室温 (℃)", value=22.0, step=0.5)

with st.sidebar.expander("⚙️ 詳細設定（任意パラメータ）"):
    furniture_factor = st.number_input("家具・内装の熱容量割増係数", min_value=1.0, value=4.0, step=0.5, help="目安: ガランとした部屋=2.0, 一般的なオフィス=4.0, 書庫=6.0~10.0")
    shr = st.number_input("顕熱比 (SHR)", min_value=0.1, max_value=1.0, value=0.75, step=0.05, help="冷房時のみ適用。温度を下げるために使われる能力の割合")
    inverter_boost = st.number_input("インバータ最大運転係数", min_value=1.0, max_value=2.0, value=1.2, step=0.1, help="立上り時のフルパワー割増率")

# --- メイン画面 ---
if st.sidebar.button("シミュレーション実行", type="primary"):
    if (mode == "冷房" and t_start <= t_target) or (mode == "暖房" and t_start >= t_target):
        st.warning("初期室温がすでに目標室温に達しています。")
    else:
        with st.spinner("計算中..."):
            time_minutes, history, error = calculate_startup_time(
                mode, volume_m3, steady_load_w, ac_capacity_w, 
                t_start, t_target, furniture_factor, shr, inverter_boost
            )
            
            if error:
                st.error(f"⚠️ {error}")
            else:
                st.success("✅ 計算が完了しました！")
                
                # 結果を大きく表示
                col1, col2 = st.columns(2)
                col1.metric(label="推定立上り時間", value=f"約 {time_minutes:.1f} 分")
                col2.metric(label="目標温度", value=f"{t_target} ℃")
                
                # グラフの描画
                st.subheader("📈 室温の推移")
                df = pd.DataFrame(history)
                df["目標室温 (℃)"] = t_target
                df.set_index("経過時間 (分)", inplace=True)
                
                # Streamlit標準の折れ線グラフ
                chart_color = ["#1f77b4", "#2ca02c"] if mode == "冷房" else ["#ff7f0e", "#2ca02c"]
                st.line_chart(df, color=chart_color)
                
                # 補足情報（計算の裏側データ）
                effective_cap = ac_capacity_w * inverter_boost * (shr if mode=="冷房" else 1.0)
                net_cap = effective_cap - steady_load_w
                heat_capacity = volume_m3 * 1.2 * 1006 * furniture_factor
                
                st.info(f"""
**【計算の内部データ】**
- 部屋の等価熱容量: `{heat_capacity:,.0f} J/K`
- 空調の有効能力: `{effective_cap:,.0f} W`
- 余剰能力（温度変化に寄与する熱量）: `{net_cap:,.0f} W`
""")
else:
    st.info("👈 左側のサイドバーから条件を設定し、「シミュレーション実行」ボタンを押してください。")

# --- 免責事項の表示 ---
st.markdown("---")
st.markdown("### 💡 計算に関する免責事項")
st.info("""
本計算結果は、集中熱容量モデル（0次元モデル）を用いた簡易的な推定値です。以下の点にご留意ください。

1. 本プログラムは定常熱負荷を一定として計算しており、外気温の変化や日射の変動などの動的な負荷変化は考慮していません。
2. 実際の立上り時間は、建物の断熱・蓄熱性能、家具の配置、空調機の制御方式により大きく変動する場合があります。
3. **本ツールによるシミュレーション結果は、あくまで目安としてご活用ください。実際の環境における完全な一致をお約束するものではございませんので、あらかじめご了承ください。**
4. **本ツールの計算結果に基づく機器選定やトラブル等につきましては、対応いたしかねる場合がございます。最終的な機器選定や空調設計にあたっては、必ず専門技術者にご相談・ご確認いただきますようお願いいたします。**
""")
