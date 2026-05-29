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
    panels = [606, 909, 1820]
    dp = {0: {0: []}}
    
    for current_len in range(int(target_length) + 1):
        if current_len in dp:
            for last_p, combo in dp[current_len].items():
                for p in panels:
                    new_len = current_len + p if current_len == 0 else current_len + 12 + p
                    if new_len <= target_length:
                        if new_len not in dp:
                            dp[new_len] = {}
                        new_combo = combo + [p]
                        if p not in dp[new_len] or len(new_combo) < len(dp[new_len][p]):
                            dp[new_len][p] = new_combo
                            
    for l in range(int(target_length), -1, -1):
        if l in dp:
            for last_p, combo in dp[l].items():
                if len(combo) > 0:
                    # ルール：両端に606サイズは置かない
                    if combo[0] != 606 and combo[-1] != 606:
                        margin = target_length - l
                        # ルール：ボーダー材（余白）は150mm以上必要（ピッタリ0はOK）
                        if margin >= 150 or margin == 0:
                            return combo, l
    return [], 0

# --- 割付計算ロジック ---
def calculate_layout(w, d, airflow):
    H = 0.0965
    min_clearance = 470 
    
    Ds_calc = (airflow / (3600 * 5 * H)) * 1000
    Ds = max(min_clearance, Ds_calc)
    
    available_w = w - (min_clearance * 2)
    num_cols = int((available_w + 12) // 612) 
    
    if num_cols <= 0:
        return None, "部屋の幅が狭すぎてパネルを配置できません。"
        
    # 左右のボーダー材が150mm以上になるように列数を自動調整
    border_x = (w - (num_cols * 612 - 12)) / 2
    while border_x < 150 and num_cols > 1:
        num_cols -= 1
        border_x = (w - (num_cols * 612 - 12)) / 2
        
    Dr_calc = ((airflow / num_cols) / (3600 * 5 * H)) * 1000
    Dr = max(min_clearance, Dr_calc)
    
    available_d = d - Ds - Dr
    if available_d < 909:
        return None, "部屋の奥行きが狭すぎてパネルを配置できません。"
        
    combo, combo_len = find_best_combination(available_d)
    
    if not combo:
        return None, "ルールに適合するパネルの組み合わせが見つかりませんでした。"
        
    rects = []
    # 背景：SAメイン流路 (赤)
    rects.append((0, d - Ds, w, Ds, '#ffcccc', 'SA Main Flow', 1.0))
    # 背景：RAメイン流路 (青)
    rects.append((0, 0, w, Dr, '#ccccff', 'RA Main Flow', 1.0))
    
    for col in range(num_cols):
        current_x = border_x + col * 612
        
        # サブ流路の背景色 (SAは赤、RAは青を交互に配置)
        if col % 2 == 0:
            rects.append((current_x, Dr, 600, d - Ds - Dr, '#ffe6e6', 'SA Sub', 1.0))
        else:
            rects.append((current_x, Dr, 600, d - Ds - Dr, '#e6e6ff', 'RA Sub', 1.0))
            
        # ボーダー材 (パネルが届かない余白部分をグレーで描画)
        if combo_len < (d - Ds - Dr):
            border_y = Dr
            border_h = (d - Ds - Dr) - combo_len
            rects.append((current_x, border_y, 600, border_h, '#e0e0e0', 'Border', 1.0))

    panel_counts = {606: 0, 909: 0, 1820: 0}
    for col in range(num_cols):
        current_x = border_x + col * 612
        current_y = d - Ds
        
        for p in combo:
            current_y -= p
            # パネルは半透明の緑で描画（下の流路を透けさせる）
            rects.append((current_x, current_y, 600, p, '#ccffcc', f'{p}', 0.8))
            panel_counts[p] += 1
            current_y -= 12 
            
    return {
        'rects': rects,
        'num_cols': num_cols,
        'combo': combo,
        'panel_counts': panel_counts,
        'Ds': Ds,
        'Dr': Dr,
        'border_x': border_x,
        'border_y': (d - Ds - Dr) - combo_len
    }, None

# --- 実行ボタン ---
if st.sidebar.button("割付図を生成する", type="primary"):
    with st.spinner('最適な割付を計算中...'):
        is_vertical = duct_pos in ["上 (Top)", "下 (Bottom)"]
        calc_w = room_w if is_vertical else room_d
        calc_d = room_d if is_vertical else room_w
        
        result, error_msg = calculate_layout(calc_w, calc_d, airflow)
        
        if error_msg:
            st.error(error_msg)
        else:
            fig, ax = plt.subplots(figsize=(10, 10))
            ax.add_patch(patches.Rectangle((0, 0), room_w, room_d, fill=False, edgecolor='black', linewidth=3))
            
            for (x, y, w, h, color, label, alpha) in result['rects']:
                if duct_pos == "上 (Top)":
                    draw_x, draw_y, draw_w, draw_h = x, y, w, h
                elif duct_pos == "下 (Bottom)":
                    draw_x, draw_y, draw_w, draw_h = x, calc_d - y - h, w, h
                elif duct_pos == "左 (Left)":
                    draw_x, draw_y, draw_w, draw_h = calc_d - y - h, x, h, w
                elif duct_pos == "右 (Right)":
                    draw_x, draw_y, draw_w, draw_h = y, calc_w - x - w, h, w
                
                rect = patches.Rectangle((draw_x, draw_y), draw_w, draw_h, fill=True, facecolor=color, edgecolor='gray', linewidth=1, alpha=alpha)
                ax.add_patch(rect)
                
                if label and label not in ['SA Sub', 'RA Sub', 'Border']:
                    text_color = 'black' if 'Main Flow' in label else 'darkgreen'
                    ax.text(draw_x + draw_w/2, draw_y + draw_h/2, label, 
                            ha='center', va='center', fontsize=8, color=text_color, fontweight='bold')

            ax.set_xlim(-200, room_w + 200)
            ax.set_ylim(-200, room_d + 200)
            ax.set_aspect('equal')
            ax.set_xlabel("Width (mm)")
            ax.set_ylabel("Depth (mm)")
            ax.set_title(f"YFPN Layout / Duct: {duct_pos}")
            ax.grid(True, linestyle=':', alpha=0.6)
            
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
                st.write(f"- **左右ボーダー材幅:** {int(result['border_x'])} mm")
                st.write(f"- **還流口側ボーダー材幅:** {int(result['border_y'])} mm")
                st.info("💡 薄い赤がSA（給気）流路、薄い青がRA（還流）流路です。パネル（緑）は流路の上に半透明で配置されています。")
