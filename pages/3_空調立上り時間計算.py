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
    temp_history = [(0, current_temp)]
    
    # 余剰能力 = 空調能力 - 定常熱負荷
    net_power = effective_ac_capacity - steady_load_w
    
    if net_power <= 0:
        return None, "エラー: 空調能力が定常熱負荷を下回っている（または等しい）ため、目標温度に到達しません。"
        
    # シミュレーションループ
    if mode == "冷房":
        if t_start <= t_target:
            return 0, temp_history
        while current_temp > t_target:
            delta_t = (net_power * dt) / c_room
            current_temp -= delta_t
            time_seconds += dt
            temp_history.append((time_seconds / 60, current_temp))
            if time_seconds > 86400: # 24時間でタイムアウト
                return None, "エラー: 24時間以内に目標温度に到達しませんでした。"
    else: # 暖房
        if t_start >= t_target:
            return 0, temp_history
        while current_temp < t_target:
            delta_t = (net_power * dt) / c_room
            current_temp += delta_t
            time_seconds += dt
            temp_history.append((time_seconds / 60, current_temp))
            if time_seconds > 86400:
                return None, "エラー: 24時間以内に目標温度に到達しませんでした。"
                
    return time_seconds / 60, temp_history

# --- UI設定 ---
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("■ 条件設定")
    
    # 必須パラメータ
    mode = st.radio("運転モード", ["冷房", "暖房"], horizontal=True)
    volume_m3 = st.number_input("室容積 (m³)", value=280.0, step=10.0, help="床面積 × 天井高")
    steady_load_w = st.number_input("定常熱負荷 (W)", value=10000, step=100, help="熱負荷計算書で算出された最大熱負荷")
    ac_capacity_w = st.number_input("空調機の定格能力 (W)", value=14000, step=100, help="カタログ記載の全能力")
    
    if mode == "冷房":
        t_start = st.number_input("初期室温 (℃)", value=32.0, step=0.5)
        t_target = st.number_input("目標室温 (℃)", value=26.0, step=0.5)
    else:
        t_start = st.number_input("初期室温 (℃)", value=10.0, step=0.5)
        t_target = st.number_input("目標室温 (℃)", value=22.0, step=0.5)
        
    # 任意パラメータ（アコーディオンで隠す）
    with st.expander("⚙️ 詳細設定（任意パラメータ）"):
        furniture_factor = st.number_input("家具・内装の熱容量割増係数", value=4.0, step=0.5, help="目安: ガランとした部屋=2.0, 一般的なオフィス=4.0, 書庫=6.0~10.0")
        shr = st.number_input("顕熱比 (SHR)", value=0.75, step=0.05, help="冷房時のみ適用。温度を下げるために使われる能力の割合")
        inverter_boost = st.number_input("インバータ最大運転係数", value=1.2, step=0.1, help="立上り時のフルパワー割増率")

    run_button = st.button("シミュレーション実行", type="primary")

with col2:
    st.subheader("■ 判定結果")
    if run_button:
        if (mode == "冷房" and t_start <= t_target) or (mode == "暖房" and t_start >= t_target):
            st.warning("初期室温がすでに目標室温に達しています。")
        else:
            with st.spinner("計算中..."):
                time_minutes, result = calculate_startup_time(
                    mode, volume_m3, steady_load_w, ac_capacity_w, 
                    t_start, t_target, furniture_factor, shr, inverter_boost
                )
                
                if time_minutes is None:
                    st.error(result) # エラーメッセージの表示
                else:
                    st.success(f"✅ **推定立上り時間: 約 {time_minutes:.1f} 分**")
                    
                    # グラフ描画用データフレーム作成
                    df = pd.DataFrame(result, columns=["経過時間 (分)", "室温 (℃)"])
                    df["目標室温 (℃)"] = t_target
                    df.set_index("経過時間 (分)", inplace=True)
                    
                    # Streamlit標準の折れ線グラフ（文字化け防止のためst.line_chartを使用）
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
        st.info("👈 左側のパネルから条件を設定し、「シミュレーション実行」ボタンを押してください。")
