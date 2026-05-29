import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# --- ページ設定 ---
st.set_page_config(page_title="YFPN 自動割付シミュレーション", layout="wide")
st.title("📐 ユカリラ YFPN 自動割付シミュレーション 【最新版テスト】")
st.error("※この赤いメッセージが見えていれば、最新のコードが正しく反映されています！")

# --- サイドバー (入力UI) ---
# （これ以降のコードはそのまま残してください）
# --- サイドバー (入力UI) ---
st.sidebar.header("【部屋の寸法設定】")
room_w = st.sidebar.number_input("部屋の横幅 W (mm)", value=5000, step=100)
room_d = st.sidebar.number_input("部屋の奥行 D (mm)", value=4000, step=100)

st.sidebar.header("【空調・ダクト設定】")
duct_pos = st.sidebar.selectbox("ダクトボックス(SA)の設置壁", ["上 (Top)", "下 (Bottom)", "左 (Left)", "右 (Right)"])
airflow = st.sidebar.number_input("エアコン最大風量 (m3/h)", value=1000, step=100)

# --- パネル組み合わせ最適化アルゴリズム ---
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
                    if combo[0] != 606 and combo[-1] != 606:
                        margin = target_length - l
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
        
    # 描画用データの整理
    draw_data = {
        'sa_main': (0, d - Ds, w, Ds),
        'ra_main': (0, 0, w, Dr),
        'sub_flows': [],
        'blocks': [],
        'panels': [],
        'borders': []
    }
    
    # ボーダー材（余白）の領域
    if border_x > 0:
        draw_data['borders'].append((0, Dr, border_x, d - Ds - Dr))
        draw_data['borders'].append((w - border_x, Dr, border_x, d - Ds - Dr))
    if combo_len < (d - Ds - Dr):
        draw_data['borders'].append((border_x, Dr, w - 2*border_x, (d - Ds - Dr) - combo_len))
        
    panel_counts = {606: 0, 909: 0, 1820: 0}
    block_size = 100 # 仕切材の描画サイズ(mm)
    
    for col in range(num_cols):
        cx = border_x + col * 612
        
        # サブ流路と仕切材（櫛の歯状の表現）
        if col % 2 == 0: # SAサブ流路（RA側が行き止まり）
            draw_data['sub_flows'].append((cx, Dr + block_size, 600, d - Ds - Dr - block_size, 'SA'))
            draw_data['blocks'].append((cx, Dr, 600, block_size))
        else: # RAサブ流路（SA側が行き止まり）
            draw_data['sub_flows'].append((cx, Dr, 600, d - Ds - Dr - block_size, 'RA'))
            draw_data['blocks'].append((cx, d - Ds - block_size, 600, block_size))
            
        # パネルの配置
        cy = d - Ds
        for p in combo:
            cy -= p
            draw_data['panels'].append((cx, cy, 600, p, p))
            panel_counts[p] += 1
            cy -= 12 
            
    return {
        'draw_data': draw_data,
        'num_cols': num_cols,
        'panel_counts': panel_counts,
        'Ds': Ds,
        'Dr': Dr,
        'border_x': border_x,
        'border_y': (d - Ds - Dr) - combo_len
    }, None

# --- 座標回転ヘルパー関数 ---
def rotate_rect(x, y, w, h, pos, cw, cd):
    if pos == "上 (Top)": return x, y, w, h
    if pos == "下 (Bottom)": return x, cd - y - h, w, h
    if pos == "左 (Left)": return cd - y - h, x, h, w
    if pos == "右 (Right)": return y, cw - x - w, h, w

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
            
            d_data = result['draw_data']
            
            # 1. メイン流路の描画
            rx, ry, rw, rh = rotate_rect(*d_data['sa_main'], duct_pos, calc_w, calc_d)
            ax.add_patch(patches.Rectangle((rx, ry), rw, rh, facecolor='#ff9999', edgecolor='black'))
            ax.text(rx+rw/2, ry+rh/2, 'SA Main Flow', ha='center', va='center', fontsize=12, fontweight='bold')
            
            rx, ry, rw, rh = rotate_rect(*d_data['ra_main'], duct_pos, calc_w, calc_d)
            ax.add_patch(patches.Rectangle((rx, ry), rw, rh, facecolor='#9999ff', edgecolor='black'))
            ax.text(rx+rw/2, ry+rh/2, 'RA Main Flow', ha='center', va='center', fontsize=12, fontweight='bold')
            
            # 2. サブ流路の描画
            for x, y, w, h, ftype in d_data['sub_flows']:
                rx, ry, rw, rh = rotate_rect(x, y, w, h, duct_pos, calc_w, calc_d)
                color = '#ffcccc' if ftype == 'SA' else '#ccccff'
                ax.add_patch(patches.Rectangle((rx, ry), rw, rh, facecolor=color, edgecolor='none'))
                
            # 3. 仕切材（ブロック）の描画
            for x, y, w, h in d_data['blocks']:
                rx, ry, rw, rh = rotate_rect(x, y, w, h, duct_pos, calc_w, calc_d)
                ax.add_patch(patches.Rectangle((rx, ry), rw, rh, facecolor='#333333', edgecolor='black'))
                
            # 4. ボーダー材の描画（斜線ハッチング）
            for x, y, w, h in d_data['borders']:
                rx, ry, rw, rh = rotate_rect(x, y, w, h, duct_pos, calc_w, calc_d)
                ax.add_patch(patches.Rectangle((rx, ry), rw, rh, facecolor='#e0e0e0', edgecolor='gray', hatch='//'))
                
            # 5. パネルの描画（透明な枠線のみにして下の流路を見せる！）
            for x, y, w, h, label in d_data['panels']:
                rx, ry, rw, rh = rotate_rect(x, y, w, h, duct_pos, calc_w, calc_d)
                ax.add_patch(patches.Rectangle((rx, ry), rw, rh, fill=False, edgecolor='green', linewidth=2))
                ax.text(rx+rw/2, ry+rh/2, str(label), ha='center', va='center', fontsize=10, color='darkgreen', fontweight='bold')

            ax.set_xlim(-200, room_w + 200)
            ax.set_ylim(-200, room_d + 200)
            ax.set_aspect('equal')
            ax.set_xlabel("Width (mm)")
            ax.set_ylabel("Depth (mm)")
            ax.set_title(f"YFPN Layout / Duct: {duct_pos}")
            
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
                
                st.info("""
                **【図面の見方】**
                - 🟩 **緑の枠線**: 床パネル（下が見えるように透明にしています）
                - 🟥 **赤色**: SA（給気）流路
                - 🟦 **青色**: RA（還流）流路
                - ⬛ **黒色**: 流路仕切材（ここで空気が行き止まりになります）
                - ⬜ **斜線**: ボーダー材（余白）
                """)
