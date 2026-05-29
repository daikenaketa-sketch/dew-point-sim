import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.sparse import lil_matrix, eye
from scipy.sparse.linalg import spsolve
import math

# --- ページ設定 ---
st.set_page_config(page_title="結露リスク シミュレーション", layout="wide")
st.title("床下空調 結露リスク シミュレーション")
st.write("左側のサイドバーで条件を設定し、「シミュレーション実行」ボタンを押してください。")

# --- 1. 露点温度計算関数 ---
def calculate_dew_point(t, rh):
    a = 17.27
    b = 237.7
    alpha = ((a * t) / (b + t)) + math.log(rh / 100.0)
    return (b * alpha) / (a - alpha)

# --- サイドバー (入力UI) ---
st.sidebar.header("【環境条件】")
T_1F = st.sidebar.number_input("1階天井裏温度 (℃)", value=30.0, step=1.0)
RH_1F = st.sidebar.number_input("1階天井裏 相対湿度 (%)", value=80.0, step=1.0)
T_void = st.sidebar.number_input("床下空気温度 (℃)", value=18.0, step=1.0)

st.sidebar.header("【構造・材料条件】")
L_mm = st.sidebar.number_input("スラブ厚み (mm)", value=150, step=10)
L = L_mm / 1000.0
R_ins = st.sidebar.number_input("断熱材の熱抵抗 (㎡K/W)", value=0.71, step=0.01)

st.sidebar.header("【欠損条件】")
point_width_cm = st.sidebar.number_input("支持脚の穴の幅 (cm)", value=10.0, step=1.0)
point_pitch_cm = st.sidebar.number_input("支持脚のピッチ (cm)", value=50.0, step=5.0)
line_width_cm = st.sidebar.number_input("目地隙間の幅 (cm)", value=2.0, step=0.5)
line_pitch_cm = st.sidebar.number_input("断熱材のピッチ (cm)", value=90.0, step=5.0)

point_width = point_width_cm / 100.0
point_pitch = point_pitch_cm / 100.0
line_width = line_width_cm / 100.0
line_pitch = line_pitch_cm / 100.0

# 固定パラメータ
lam_c = 1.6
rho_c = 2300.0
c_c = 880.0
alpha_c = lam_c / (rho_c * c_c)
R_se = 0.11
R_si = 0.045
U_se = 1.0 / R_se
U_cut = 1.0 / R_si
U_ins = 1.0 / (R_si + R_ins)

# --- シミュレーション関数 ---
def simulate_point_defect(cut_width, pitch, times_to_record):
    R_max = pitch / 2.0
    r_cut = cut_width / 2.0
    dr = 0.0025
    dz = 0.005
    Nr = int(R_max / dr)
    Nz = int(L / dz)
    N = (Nr + 1) * (Nz + 1)
    
    A = lil_matrix((N, N))
    b = np.zeros(N)
    def idx(i, j): return i * (Nz + 1) + j
    
    for i in range(Nr + 1):
        r = i * dr
        Ui = U_cut if r <= r_cut + 1e-5 else U_ins
        for j in range(Nz + 1):
            k = idx(i, j)
            coef_r_minus = 0.0
            coef_r_plus = 0.0
            diag_r = -2/dr**2
            if i == 0:
                coef_r_plus = 4/dr**2
                diag_r = -4/dr**2
            elif i == Nr:
                coef_r_minus = 2/dr**2
            else:
                coef_r_minus = 1/dr**2 - 1/(2*r*dr)
                coef_r_plus = 1/dr**2 + 1/(2*r*dr)
                
            coef_z_minus = 0.0
            coef_z_plus = 0.0
            diag_z = -2/dz**2
            if j == 0:
                coef_z_plus = 2/dz**2
                diag_z += -2*Ui/(lam_c*dz)
                b[k] = -2*Ui*T_void/(lam_c*dz)
            elif j == Nz:
                coef_z_minus = 2/dz**2
                diag_z += -2*U_se/(lam_c*dz)
                b[k] = -2*U_se*T_1F/(lam_c*dz)
            else:
                coef_z_minus = 1/dz**2
                coef_z_plus = 1/dz**2
                
            A[k, k] = diag_r + diag_z
            if coef_r_minus > 0: A[k, idx(i-1, j)] = coef_r_minus
            if coef_r_plus > 0: A[k, idx(i+1, j)] = coef_r_plus
            if coef_z_minus > 0: A[k, idx(i, j-1)] = coef_z_minus
            if coef_z_plus > 0: A[k, idx(i, j+1)] = coef_z_plus

    dt = 60.0
    max_time = max(times_to_record)
    num_steps = int(max_time / dt)
    
    I = eye(N, format='csr')
    A_csr = A.tocsr()
    M = I - alpha_c * dt * A_csr
    rhs_const = - alpha_c * dt * b
    
    T_current = np.full(N, T_1F)
    results = {}
    
    for step in range(1, num_steps + 1):
        current_time = step * dt
        T_current = spsolve(M, T_current + rhs_const)
        if current_time in times_to_record:
            results[current_time] = T_current.reshape((Nr + 1, Nz + 1))[:, Nz]
            
    results['steady'] = spsolve(A_csr, b).reshape((Nr + 1, Nz + 1))[:, Nz]
    return np.linspace(0, R_max, Nr + 1), results

def simulate_line_defect(gap_width, pitch, times_to_record):
    X_max = pitch / 2.0
    x_cut = gap_width / 2.0
    dx = 0.0025
    dz = 0.005
    Nx = int(X_max / dx)
    Nz = int(L / dz)
    N = (Nx + 1) * (Nz + 1)
    
    A = lil_matrix((N, N))
    b = np.zeros(N)
    def idx(i, j): return i * (Nz + 1) + j
    
    for i in range(Nx + 1):
        x = i * dx
        Ui = U_cut if x <= x_cut + 1e-5 else U_ins
        for j in range(Nz + 1):
            k = idx(i, j)
            coef_x_minus = 0.0
            coef_x_plus = 0.0
            diag_x = -2/dx**2
            if i == 0:
                coef_x_plus = 2/dx**2
            elif i == Nx:
                coef_x_minus = 2/dx**2
            else:
                coef_x_minus = 1/dx**2
                coef_x_plus = 1/dx**2
                
            coef_z_minus = 0.0
            coef_z_plus = 0.0
            diag_z = -2/dz**2
            if j == 0:
                coef_z_plus = 2/dz**2
                diag_z += -2*Ui/(lam_c*dz)
                b[k] = -2*Ui*T_void/(lam_c*dz)
            elif j == Nz:
                coef_z_minus = 2/dz**2
                diag_z += -2*U_se/(lam_c*dz)
                b[k] = -2*U_se*T_1F/(lam_c*dz)
            else:
                coef_z_minus = 1/dz**2
                coef_z_plus = 1/dz**2
                
            A[k, k] = diag_x + diag_z
            if coef_x_minus > 0: A[k, idx(i-1, j)] = coef_x_minus
            if coef_x_plus > 0: A[k, idx(i+1, j)] = coef_x_plus
            if coef_z_minus > 0: A[k, idx(i, j-1)] = coef_z_minus
            if coef_z_plus > 0: A[k, idx(i, j+1)] = coef_z_plus

    dt = 60.0
    max_time = max(times_to_record)
    num_steps = int(max_time / dt)
    
    I = eye(N, format='csr')
    A_csr = A.tocsr()
    M = I - alpha_c * dt * A_csr
    rhs_const = - alpha_c * dt * b
    
    T_current = np.full(N, T_1F)
    results = {}
    
    for step in range(1, num_steps + 1):
        current_time = step * dt
        T_current = spsolve(M, T_current + rhs_const)
        if current_time in times_to_record:
            results[current_time] = T_current.reshape((Nx + 1, Nz + 1))[:, Nz]
            
    results['steady'] = spsolve(A_csr, b).reshape((Nx + 1, Nz + 1))[:, Nz]
    return np.linspace(0, X_max, Nx + 1), results

# --- 実行ボタン ---
if st.sidebar.button("シミュレーション実行", type="primary"):
    with st.spinner('計算中...（約10〜20秒かかります）'):
        dew_point = calculate_dew_point(T_1F, RH_1F)
        
        times = [10 * 60, 60 * 60, 5 * 60 * 60]
        labels = {600: "10 Minutes", 3600: "1 Hour", 18000: "5 Hours", 'steady': "Infinite (Steady State)"}
        
        r_arr, res_point = simulate_point_defect(point_width, point_pitch, times)
        x_arr, res_line = simulate_line_defect(line_width, line_pitch, times)
        
        st.subheader(f"💧 1階天井裏の露点温度: {dew_point:.2f} ℃")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**【結果1: 点状欠損 (支持脚 {point_width_cm}cm穴 / {point_pitch_cm}cmピッチ)】**")
            for t_key, T_bot in res_point.items():
                st.write(f"- [{labels[t_key]}] 欠損直下の温度: **{T_bot[0]:.2f} ℃**")
                
        with col2:
            st.markdown(f"**【結果2: 線状欠損 (目地隙間 {line_width_cm}cm / {line_pitch_cm}cmピッチ)】**")
            for t_key, T_bot in res_line.items():
                st.write(f"- [{labels[t_key]}] 欠損直下の温度: **{T_bot[0]:.2f} ℃**")

        # グラフ描画
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        for t_key, T_bot in res_point.items():
            ax1.plot(r_arr * 100, T_bot, label=labels[t_key])
        ax1.axhline(y=dew_point, color='r', linestyle='--', label=f"Dew Point ({dew_point:.2f} C)")
        ax1.set_title(f"Point Defect ({point_width_cm}cm Hole, {point_pitch_cm}cm Pitch)")
        ax1.set_xlabel("Distance from Center (cm)")
        ax1.set_ylabel("Temperature (C)")
        ax1.legend()
        ax1.grid(True)
        
        for t_key, T_bot in res_line.items():
            ax2.plot(x_arr * 100, T_bot, label=labels[t_key])
        ax2.axhline(y=dew_point, color='r', linestyle='--', label=f"Dew Point ({dew_point:.2f} C)")
        ax2.set_title(f"Line Defect ({line_width_cm}cm Gap, {line_pitch_cm}cm Pitch)")
        ax2.set_xlabel("Distance from Center (cm)")
        ax2.set_ylabel("Temperature (C)")
        ax2.legend()
        ax2.grid(True)
        
        st.pyplot(fig)
        
        # 結露判定
        min_temp_point = res_point['steady'][0]
        min_temp_line = res_line['steady'][0]
        if min_temp_point <= dew_point or min_temp_line <= dew_point:
            st.error("⚠️ 警告: 定常状態で露点温度を下回る箇所があります。結露リスクが高いです。")
        else:
            st.success("✅ 安全: 定常状態でも露点温度を上回っています。結露リスクは低いです。")
