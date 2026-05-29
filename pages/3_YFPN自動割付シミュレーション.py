import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# --- ページ設定 ---
st.set_page_config(page_title="YFPN 自動割付シミュレーション", layout="wide")
st.title("📐 ユカリラ YFPN 自動割付シミュレーション")
st.markdown("部屋の寸法とダクトボックス（SA）の位置を入力するだけで、マニュアルのルールに従った最適なパネル割付図を自動生成します。")

# --- サイドバー (入力UI) ---
st.sidebar.header("【部屋の寸法設定】")
room_w = st.sidebar.number_input("部屋の横幅 W (mm)", value=5000, step=100)
room_d = st.sidebar.number_input("部屋の奥行 D (mm)", value=4000, step=100)

st.sidebar.header("【空調・ダクト設定】")
duct_pos = st.sidebar.selectbox("ダクトボックス(SA)の設置壁", ["上 (Top)", "下 (Bottom)", "左 (Left)", "右 (Right)"])
airflow = st.sidebar.number_input("エアコン最大風量 (m3/h)", value=1000, step=100)

# --- パネル組み合わせ最適化アルゴリズム（動的計画法） ---
@st.cache_data
def find_best_combination(target_length):
    """
    指定された長さに対して、606, 909, 1820のパネルを12mmの隙間で配置し、
    「両端に606を置かない」というルールを守りつつ、最も長く敷き詰める組み合わせを探す。
    """
    panels = [606, 909, 1820]
    # dp[length][last_panel] = combo_list
    dp = {0: {0: []}}
    
    for current_len in range(int(target_length) + 1):
        if current_len in dp:
            for last_p, combo in dp[current_len].items():
                for p in panels:
                    # 最初の1枚目は隙間なし、2枚目以降は12mmの隙間を足す
                    new_len = current_len + p if current_len == 0 else current_len + 12 + p
                    if new_len <= target_length:
                        if new_len not in dp:
                            dp[new_len] = {}
                        new_combo = combo + [p]
                        # 同じ長さに到達するなら、パネル枚数が少ない（1820を多く使う）方を優先
                        if p not in dp[new_len] or len(new_combo) < len(dp[new_len][p]):
                            dp[new_len][p] = new_combo
                            
    # 条件（両端が606ではない）を満たす最大の長さを探す
    for l in range(int(target_length), -1, -1):
        if l in dp:
            for last_p, combo in dp[l].items():
                if len(combo) > 0:
                    if combo[0] != 606 and combo[-1] != 606:
                        return combo, l
    return [], 0

# --- 割付計算ロジック ---
def calculate_layout(w, d, airflow):
    # 1. 流路幅の計算 (マニュアル 3.2, 3.4)
    # 面風速5m/s以下、流路高さ96.5mm(0.0965m)で計算
    H = 0.0965
    min_clearance = 470 # 壁からの最低離隔距離(mm)
    
    # SAメイン流路幅 (Ds)
    Ds_calc = (airflow / (3600 * 5 * H)) * 1000
    Ds = max(min_clearance, Ds_calc)
    
    # 2. サブ流路の列数計算 (マニュアル 3.3)
    available_w = w - (min_clearance * 2)
    num_cols = int((available_w + 12) // 612) # 600mmパネル + 12mm隙間
    
    if num_cols <= 0:
        return None, "部屋の幅が狭すぎてパネルを配置できません。"
        
    # RAメイン流路幅 (Dr)
    Dr_calc = ((airflow / num_cols) / (3600 * 5 * H)) * 1000
    Dr = max(min_clearance, Dr_calc)
    
    # 3. パネルの組み合わせ計算 (マニュアル 4.2〜4.4)
    available_d = d - Ds - Dr
    if available_d < 909:
        return None, "部屋の奥行きが狭すぎてパネルを配置できません。"
        
    combo, combo_len = find_best_combination(available_d)
    
    if not combo:
        return None, "ルールに適合するパネルの組み合わせが見つかりませんでした。"
        
    # 4. 座標の生成 (常にSAが「上」にある前提で計算)
    border_x = (w - (num_cols * 612 - 12)) / 2
    
    rects = []
    # SA流路 (x, y, width, height, color, label)
    rects.append((0, d - Ds, w, Ds, '#ffcccc', 'SA Main Flow'))
    # RA流路
    rects.append((0, 0, w, d - Ds - combo_len, '#ccccff', 'RA Main Flow'))
    
    panel_counts = {606: 0, 909: 0, 1820: 0}
    
    for col in range(num_cols):
        current_x = border_x + col * 612
        current_y = d - Ds
        
        for p in combo:
            current_y -= p
            rects.append((current_x, current_y, 600, p, '#ccffcc', f'{p}'))
            panel_counts[p] += 1
            current_y -= 12 # 隙間
            
    return {
        'rects': rects,
        'num_cols': num_cols,
        'combo': combo,
        'panel_counts': panel_counts,
        'Ds': Ds,
        'Dr': d - Ds - combo_len
    }, None

# --- 実行ボタン ---
if st.sidebar.button("割付図を生成する", type="primary"):
    with st.spinner('最適な割付を計算中...'):
        
        # ダクト位置に合わせて内部のWとDを入れ替える（計算を共通化する賢い処理）
        is_vertical = duct_pos in ["上 (Top)", "下 (Bottom)"]
        calc_w = room_w if is_vertical else room_d
        calc_d = room_d if is_vertical else room_w
        
        result, error_msg = calculate_layout(calc_w, calc_d, airflow)
        
        if error_msg:
            st.error(error_msg)
        else:
            # --- 描画処理 ---
            fig, ax = plt.subplots(figsize=(10, 10))
            
            # 部屋の枠
            ax.add_patch(patches.Rectangle((0, 0), room_w, room_d, fill=False, edgecolor='black', linewidth=3))
            
            # 座標の回転マッピング
            for (x, y, w, h, color, label) in result['rects']:
                if duct_pos == "上 (Top)":
                    draw_x, draw_y, draw_w, draw_h = x, y, w, h
                elif duct_pos == "下 (Bottom)":
                    draw_x, draw_y, draw_w, draw_h = x, calc_d - y - h, w, h
                elif duct_pos == "左 (Left)":
                    draw_x, draw_y, draw_w, draw_h = y, x, h, w
                elif duct_pos == "右 (Right)":
                    draw_x, draw_y, draw_w, draw_h = calc_d - y - h, x, h, w
                
                rect = patches.Rectangle((draw_x, draw_y), draw_w, draw_h, fill=True, facecolor=color, edgecolor='gray', linewidth=1)
                ax.add_patch(rect)
                
                # パネルのテキストラベル（小さすぎない場合のみ表示）
                if label not in ['SA Main Flow', 'RA Main Flow']:
                    ax.text(draw_x + draw_w/2, draw_y + draw_h/2, label, 
                            ha='center', va='center', fontsize=8, color='darkgreen')

            # グラフの見た目調整
            ax.set_xlim(-200, room_w + 200)
            ax.set_ylim(-200, room_d + 200)
            ax.set_aspect('equal')
            ax.set_xlabel("Width (mm)")
            ax.set_ylabel("Depth (mm)")
            ax.set_title(f"YFPN Layout / Duct: {duct_pos}")
            ax.grid(True, linestyle=':', alpha=0.6)
            
            # --- 結果表示UI ---
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.pyplot(fig)
                
            with col2:
                st.success("✅ 割付計算が完了しました！")
                st.subheader("■ 使用パネル枚数")
                st.write(f"- **1800サイズ (1820mm):** {result['panel_counts'][1820]} 枚")
                st.write(f"- **900サイズ (909mm):** {result['panel_counts'][909]} 枚")
                st.write(f"- **600サイズ (606mm):** {result['panel_counts'][606]} 枚")
                st.markdown("---")
                st.subheader("■ 流路・設計データ")
                st.write(f"- **列数 (サブ流路):** {result['num_cols']} 列")
                st.write(f"- **SAメイン流路幅:** {int(result['Ds'])} mm")
                st.write(f"- **RAメイン流路幅:** {int(result['Dr'])} mm")
                st.info("💡 赤いエリアがSA（給気）流路、青いエリアがRA（還流）流路です。マニュアルの「端部に600サイズを置かない」ルールを遵守して配置されています。")
使い方と確認ポイント
