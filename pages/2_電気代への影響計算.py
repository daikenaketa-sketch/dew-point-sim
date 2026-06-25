import streamlit as st
import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve
import math

# --- ページ設定 ---
st.set_page_config(page_title="消費電力影響シミュレーション", layout="wide")
st.title("💴 断熱欠損による消費電力（電気代）への影響シミュレーション")
st.markdown("支持脚や目地の隙間（断熱欠損）をウレタン等で塞がなかった場合、エアコンの電気代にどれくらい影響が出るかを計算します。")

# --- サイドバー (入力UI) ---
st.sidebar.header("【住宅・経済条件】")
floor_area = st.sidebar.number_input("1階床面積 (㎡)", value=50.0, step=5.0)
elec_price = st.sidebar.number_input("電気料金単価 (円/kWh)", value=30.0, step=1.0)

# ★追加：断熱欠損の条件をユーザーが入力できるようにしました
st.sidebar.header("【断熱欠損の条件】")
point_width_cm = st.sidebar.number_input("支持脚の穴の直径 (cm)", value=10.0, step=1.0, help="断熱材が欠損している部分の直径")
point_pitch_cm = st.sidebar.number_input("支持脚のピッチ (cm)", value=50.0, step=5.0, help="支持脚が配置されている間隔")

st.sidebar.header("【空調仕様（実機データ）】")
st.sidebar.markdown("**❄️ 冷房**")
cooling_capacity_kW = st.sidebar.number_input("冷房能力 (kW)", value=14.0, step=0.1)
cooling_power_kW = st.sidebar.number_input("冷房消費電力 (kW)", value=4.77, step=0.01)

st.sidebar.markdown("**🔥 暖房**")
heating_capacity_kW = st.sidebar.number_input("暖房能力 (kW)", value=16.0, step=0.1)
heating_power_kW = st.sidebar.number_input("暖房消費電力 (kW)", value=3.98, step=0.01)

# COPの自動計算
cop_cooling = cooling_capacity_kW / cooling_power_kW if cooling_power_kW > 0 else 1.0
cop_heating = heating_capacity_kW / heating_power_kW if heating_power_kW > 0 else 1.0

st.sidebar.header("【環境条件設定】")
st.sidebar.markdown("**冬の暖房時**")
T_air_w = st.sidebar.number_input("床下温風 (℃)", value=35.0, step=1.0)
T_ground_w = st.sidebar.number_input("冬の地中温度 (℃)", value=15.0, step=1.0)

st.sidebar.markdown("**夏の冷房時**")
T_air_s = st.sidebar.number_input("床下冷風 (℃)", value=18.0, step=1.0)
T_ground_s = st.sidebar.number_input("夏の地中温度 (℃)", value=25.0, step=1.0)

# --- 熱量計算関数 ---
# ★修正：入力された直径とピッチを引数として受け取るように変更
def calculate_heat_loss(T_air, T_ground, point_width_cm, point_pitch_cm, defect_mode="defect"):
    lam_c, lam_s = 1.6, 1.0
    L_c, L_s = 0.150, 2.000
    
    # 入力値からピッチと欠損半径を計算
    pitch = point_pitch_cm / 100.0
    R_max = pitch / 2.0
    r_cut = (point_width_cm / 100.0) / 2.0
    
    R_si, R_ins = 0.045, 0.71
    U_cut = 1.0 / R_si
    U_ins = 1.0 / (R_si + R_ins)

    dr, dz = 0.005, 0.02
    Nr = int(R_max / dr)
    Nz_c, Nz_s = int(L_c / dz), int(L_s / dz)
    Nz = Nz_c + Nz_s
    N = (Nr + 1) * (Nz + 1)
    
    A = lil_matrix((N, N))
    b = np.zeros(N)
    def idx(i, j): return i * (Nz + 1) + j

    for i in range(Nr + 1):
        r = i * dr
        Ui = U_ins if defect_mode == "perfect" else (U_cut if r <= r_cut + 1e-5 else U_ins)
        
        for j in range(Nz + 1):
            k = idx(i, j)
            lam = lam_c if j <= Nz_c else lam_s
            
            if j == 0:
                coef_r_minus = 0 if i == 0 else (1/dr**2 - 1/(2*r*dr) if i < Nr else 2/dr**2)
                coef_r_plus = 4/dr**2 if i == 0 else (1/dr**2 + 1/(2*r*dr) if i < Nr else 0)
                diag_r = -4/dr**2 if i == 0 else (-2/dr**2)
                A[k, k] = diag_r - 2/dz**2 - 2*Ui/(lam*dz)
                if coef_r_minus > 0: A[k, idx(i-1, j)] = coef_r_minus
                if coef_r_plus > 0: A[k, idx(i+1, j)] = coef_r_plus
                A[k, idx(i, j+1)] = 2/dz**2
                b[k] = -2*Ui*T_air/(lam*dz)
            elif j == Nz:
                A[k, k] = 1.0
                b[k] = T_ground
            else:
                coef_r_minus = 0 if i == 0 else (1/dr**2 - 1/(2*r*dr) if i < Nr else 2/dr**2)
                coef_r_plus = 4/dr**2 if i == 0 else (1/dr**2 + 1/(2*r*dr) if i < Nr else 0)
                diag_r = -4/dr**2 if i == 0 else (-2/dr**2)
                A[k, k] = diag_r - 2/dz**2
                if coef_r_minus > 0: A[k, idx(i-1, j)] = coef_r_minus
                if coef_r_plus > 0: A[k, idx(i+1, j)] = coef_r_plus
                A[k, idx(i, j-1)] = 1/dz**2
                A[k, idx(i, j+1)] = 1/dz**2

    T_steady = spsolve(A.tocsr(), b).reshape((Nr + 1, Nz + 1))
    
    total_heat_W = 0.0
    for i in range(Nr + 1):
        r = i * dr
        if i == 0: area = math.pi * (dr/2)**2
        elif i == Nr: area = math.pi * (r**2 - (r - dr/2)**2)
        else: area = math.pi * ((r + dr/2)**2 - (r - dr/2)**2)
        
        Ui = U_ins if defect_mode == "perfect" else (U_cut if r <= r_cut + 1e-5 else U_ins)
        T_surface = T_steady[i, 0]
        heat_flux = Ui * (T_air - T_surface) * area
        total_heat_W += heat_flux
        
    return total_heat_W * (1.0 / (pitch * pitch))

def calculate_electricity_cost(heat_diff_per_m2, area_m2, cop, unit_price):
    total_heat_diff = heat_diff_per_m2 * area_m2
    power_consumption_W = total_heat_diff / cop
    monthly_cost = power_consumption_W * 24 * 30 / 1000 * unit_price
    return total_heat_diff, power_consumption_W, monthly_cost

# --- 実行ボタン ---
if st.sidebar.button("シミュレーション実行", type="primary"):
    with st.spinner('熱伝導シミュレーションを実行中...'):
        
        # ★修正：関数呼び出し時に、サイドバーで入力された直径とピッチを渡す
        # 冬の計算
        heat_w_perf = calculate_heat_loss(T_air_w, T_ground_w, point_width_cm, point_pitch_cm, "perfect")
        heat_w_def = calculate_heat_loss(T_air_w, T_ground_w, point_width_cm, point_pitch_cm, "defect")
        diff_w = heat_w_def - heat_w_perf
        inc_w_pct = (heat_w_def / heat_w_perf - 1.0) * 100
        tot_w, pow_w, cost_w = calculate_electricity_cost(diff_w, floor_area, cop_heating, elec_price)

        # 夏の計算
        heat_s_perf = abs(calculate_heat_loss(T_air_s, T_ground_s, point_width_cm, point_pitch_cm, "perfect"))
        heat_s_def = abs(calculate_heat_loss(T_air_s, T_ground_s, point_width_cm, point_pitch_cm, "defect"))
        diff_s = heat_s_def - heat_s_perf
        inc_s_pct = (heat_s_def / heat_s_perf - 1.0) * 100
        tot_s, pow_s, cost_s = calculate_electricity_cost(diff_s, floor_area, cop_cooling, elec_price)

        # --- 結果表示 ---
        st.info(f"💡 **自動計算されたCOP** ｜ 冷房COP: **{cop_cooling:.2f}** / 暖房COP: **{cop_heating:.2f}**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⛄ 冬の暖房時")
            st.write(f"床下温風: {T_air_w}℃ / 地中温度: {T_ground_w}℃")
            st.metric(label="欠損による熱損失の悪化率", value=f"{inc_w_pct:.1f} %")
            st.write(f"- 欠損なし: {heat_w_perf:.2f} W/㎡")
            st.write(f"- 欠損あり: {heat_w_def:.2f} W/㎡")
            st.markdown("---")
            st.metric(label="1ヶ月の電気代増加額", value=f"約 {int(cost_w)} 円/月")
            st.write(f"（家全体の熱損失増加: {tot_w:.1f} W）")
            st.write(f"（エアコン消費電力増: 約 {pow_w:.1f} W）")

        with col2:
            st.subheader("🌻 夏の冷房時")
            st.write(f"床下冷風: {T_air_s}℃ / 地中温度: {T_ground_s}℃")
            st.metric(label="欠損による熱取得の悪化率", value=f"{inc_s_pct:.1f} %")
            st.write(f"- 欠損なし: {heat_s_perf:.2f} W/㎡")
            st.write(f"- 欠損あり: {heat_s_def:.2f} W/㎡")
            st.markdown("---")
            st.metric(label="1ヶ月の電気代増加額", value=f"約 {int(cost_s)} 円/月")
            st.write(f"（家全体の熱取得増加: {tot_s:.1f} W）")
            st.write(f"（エアコン消費電力増: 約 {pow_s:.1f} W）")

        st.divider()
        
        # 結論パネル
        st.success(f"""
        **【結論：なぜウレタンで塞がなくても良いのか？】** 
        断熱性能の悪化率は {inc_w_pct:.1f}% となりますが、実際の空調機の性能（COP）を考慮した電気代への影響は、
        **冬の暖房時で月額約 {int(cost_w)} 円、夏の冷房時で月額約 {int(cost_s)} 円** にすぎません。 
        これは、スラブ下の『地盤（土）』自体が巨大な断熱材として機能しているためです。 
        ウレタン等で塞ぐための材料費や職人の手間賃（数万円〜）を考慮すると、**費用対効果（コストメリット）が全く合わないため、塞がなくても実質的な問題はありません。**
        """)
