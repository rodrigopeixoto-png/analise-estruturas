import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import ezdxf
import tempfile
import os

st.set_page_config(page_title="Ftool Engine - Interativo", layout="wide")
st.title("🏗️ Motor Ftool: Geometria Interativa e Perfis")

# --- BIBLIOTECAS DE MATERIAIS E SEÇÕES ---import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import ezdxf
import tempfile
import os

st.set_page_config(page_title="Ftool Web Interativo", layout="wide")
st.title("🏗️ Ftool Web: Geometria DXF, Seleção por Clique e Perfis")

# -----------------------------------------------------------------------------
# 1. CATÁLOGO DE MATERIAIS E SEÇÕES (Laminados e Dobrados C)
# -----------------------------------------------------------------------------
MATERIAIS = {
    "Aço Estrutural (200 GPa)": 200.0,
    "Alumínio (70 GPa)": 70.0,
    "Concreto (25 GPa)": 25.0
}

# Perfis U Laminados Comerciais (Área cm², Inércia X cm⁴)
SECOES = {
    "U Laminado 3\" x 1a (76x35mm)": (5.44, 48.6),
    "U Laminado 4\" x 1a (101x40mm)": (7.15, 106.0),
    "U Laminado 6\" x 1a (152x48mm)": (10.48, 368.0),
    "U Laminado 8\" x 1a (203x57mm)": (14.59, 886.0),
    "U Laminado 10\" x 1a (254x66mm)": (19.34, 1806.0),
    "U Laminado 12\" x 1a (304x77mm)": (24.31, 3284.0),
    "Tubo Quadrado 100x5": (19.0, 280.0),
    "Barra Maciça 10x10": (100.0, 833.0)
}

# Gerador de Perfis U Dobrados tipo C (Chapas 10 até 18)
chapas = {18: 1.20, 16: 1.50, 14: 1.90, 13: 2.25, 12: 2.65, 11: 3.00, 10: 3.40}
dimensoes_dobrados = [
    (75, 25), (75, 40), (100, 40), (100, 50), 
    (120, 40), (150, 50), (200, 40)
]

for h_mm, b_mm in dimensoes_dobrados:
    for chapa_num, e_mm in chapas.items():
        h = h_mm / 10.0
        b = b_mm / 10.0
        e = e_mm / 10.0
        area = 2 * (b * e) + (h - 2*e) * e
        ix_alma = (e * (h - 2*e)**3) / 12
        ix_mesa = (b * e**3) / 12
        dist_m = (h - e) / 2
        inercia_x = ix_alma + 2 * (ix_mesa + (b * e) * (dist_m**2))
        nome_c = f"U Dobrado {h_mm}x{b_mm}x{e_mm}mm (Chapa {chapa_num})"
        SECOES[nome_c] = (round(area, 2), round(inercia_x, 2))

LISTA_SECOES = list(SECOES.keys())
LISTA_MATERIAIS = list(MATERIAIS.keys())

# -----------------------------------------------------------------------------
# 2. ESTADO DA SESSÃO (Memória)
# -----------------------------------------------------------------------------
if 'dados_nos' not in st.session_state:
    st.session_state.dados_nos = []
if 'dados_barras' not in st.session_state:
    st.session_state.dados_barras = []
if 'no_selecionado' not in st.session_state:
    st.session_state.no_selecionado = 1
if 'barra_selecionada' not in st.session_state:
    st.session_state.barra_selecionada = 1

# -----------------------------------------------------------------------------
# 3. UPLOAD DXF
# -----------------------------------------------------------------------------
st.subheader("1. Importar Geometria (DXF)")
arquivo_dxf = st.file_uploader("Arraste seu arquivo .dxf aqui", type=['dxf'])

if arquivo_dxf is not None and st.button("Processar DXF"):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp:
            tmp.write(arquivo_dxf.getvalue())
            tmp_path = tmp.name

        doc = ezdxf.readfile(tmp_path)
        os.remove(tmp_path)
        msp = doc.modelspace()

        nos_set = set()
        barras_dxf = []

        for linha in msp.query('LINE'):
            p1 = (round(linha.dxf.start.x, 3), round(linha.dxf.start.y, 3))
            p2 = (round(linha.dxf.end.x, 3), round(linha.dxf.end.y, 3))
            nos_set.update([p1, p2])
            barras_dxf.append((p1, p2))

        for polyline in msp.query('LWPOLYLINE'):
            pts = [(round(p[0], 3), round(p[1], 3)) for p in polyline.get_points(format='xy')]
            for i in range(len(pts) - 1):
                p1, p2 = pts[i], pts[i+1]
                nos_set.update([p1, p2])
                barras_dxf.append((p1, p2))

        nos_lista = sorted(list(nos_set), key=lambda pt: (pt[0], pt[1]))
        no_map = {pt: i+1 for i, pt in enumerate(nos_lista)}

        st.session_state.dados_nos = [
            {"Nó": no_map[n], "X": n[0], "Y": n[1], "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0}
            for n in nos_lista
        ]
        st.session_state.dados_barras = [
            {"Barra": i+1, "Nó Inic.": no_map[b[0]], "Nó Final": no_map[b[1]], "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[0]}
            for i, b in enumerate(barras_dxf)
        ]
        st.session_state.no_selecionado = 1
        st.session_state.barra_selecionada = 1
        st.success(f"Geometria importada: {len(nos_lista)} nós e {len(barras_dxf)} barras identificados.")
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")

# Se não carregar nada, carrega um pórtico simples de amostra
if not st.session_state.dados_nos:
    st.session_state.dados_nos = [
        {"Nó": 1, "X": 0.0, "Y": 0.0, "Apoio X": True, "Apoio Y": True, "Apoio Rot": True, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
        {"Nó": 2, "X": 0.0, "Y": 4.0, "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 15.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
        {"Nó": 3, "X": 5.0, "Y": 4.0, "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": -20.0, "Mz (kNm)": 0.0},
        {"Nó": 4, "X": 5.0, "Y": 0.0, "Apoio X": True, "Apoio Y": True, "Apoio Rot": True, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
    ]
    st.session_state.dados_barras = [
        {"Barra": 1, "Nó Inic.": 1, "Nó Final": 2, "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[0]},
        {"Barra": 2, "Nó Inic.": 2, "Nó Final": 3, "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[1]},
        {"Barra": 3, "Nó Inic.": 3, "Nó Final": 4, "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[0]},
    ]

# -----------------------------------------------------------------------------
# 4. VISUALIZAÇÃO INTERATIVA COM PLOTLY (LARGURA TOTAL)
# -----------------------------------------------------------------------------
st.subheader("2. Geometria Interativa (Clique sobre um Nó ou Barra)")

coords_map = {n['Nó']: (n['X'], n['Y']) for n in st.session_state.dados_nos}

fig = go.Figure()

# 4.1 Desenhar as barras
for b in st.session_state.dados_barras:
    n1, n2 = b['Nó Inic.'], b['Nó Final']
    if n1 in coords_map and n2 in coords_map:
        x1, y1 = coords_map[n1]
        x2, y2 = coords_map[n2]
        
        is_sel = (b['Barra'] == st.session_state.barra_selecionada)
        cor_linha = 'magenta' if is_sel else '#1f77b4'
        largura_linha = 4 if is_sel else 2

        fig.add_trace(go.Scatter(
            x=[x1, x2],
            y=[y1, y2],
            mode='lines',
            line=dict(color=cor_linha, width=largura_linha),
            hoverinfo='text',
            text=f"Barra {b['Barra']}<br>Seção: {b['Seção']}<br>Mat: {b['Material']}",
            customdata=[b['Barra'], b['Barra']],
            showlegend=False
        ))

# 4.2 Desenhar os nós
x_pts, y_pts, nos_ids, txt_hover = [], [], [], []
for n in st.session_state.dados_nos:
    x_pts.append(n['X'])
    y_pts.append(n['Y'])
    nos_ids.append(n['Nó'])
    info_ap = []
    if n['Apoio X']: info_ap.append("Dx")
    if n['Apoio Y']: info_ap.append("Dy")
    if n['Apoio Rot']: info_ap.append("Rz")
    txt_ap = f"Apoios: [{', '.join(info_ap)}]" if info_ap else "Livre"
    txt_hover.append(f"Nó {n['Nó']}<br>({n['X']}, {n['Y']})<br>{txt_ap}<br>Fx: {n['Fx (kN)']} kN, Fy: {n['Fy (kN)']} kN")

cores_nos = ['yellow' if nid == st.session_state.no_selecionado else 'red' for nid in nos_ids]

fig.add_trace(go.Scatter(
    x=x_pts,
    y=y_pts,
    mode='markers+text',
    marker=dict(size=9, color=cores_nos, line=dict(width=1, color='black')),
    text=[str(nid) for nid in nos_ids],
    textposition="top center",
    textfont=dict(size=9, color='darkred'),
    hoverinfo='text',
    hovertext=txt_hover,
    customdata=nos_ids,
    name='Nós'
))

fig.update_layout(
    height=400,
    margin=dict(l=20, r=20, t=20, b=20),
    xaxis=dict(scaleanchor="y", scaleratio=1, showgrid=True, zeroline=False),
    yaxis=dict(showgrid=True, zeroline=False),
    dragmode="pan",
    clickmode="event+select"
)

# Captura de clique direto no gráfico
event_click = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="main_plot")

# Processar o ponto clicado
if event_click and "selection" in event_click and event_click["selection"]["points"]:
    ponto = event_click["selection"]["points"][0]
    if "customdata" in ponto:
        cdata = ponto["customdata"]
        # Se for um número correspondente a um nó
        if any(n['Nó'] == cdata for n in st.session_state.dados_nos):
            st.session_state.no_selecionado = int(cdata)
        elif any(b['Barra'] == cdata for b in st.session_state.dados_barras):
            st.session_state.barra_selecionada = int(cdata)

# -----------------------------------------------------------------------------
# 5. PAINEL DE ATRIBUIÇÃO RÁPIDA (ABAIXO DO DESENHO)
# -----------------------------------------------------------------------------
st.subheader("3. Painel de Atribuição")
col_p1, col_p2 = st.columns(2)

with col_p1:
    st.markdown("#### 📍 Configurar Nó")
    sel_n = st.selectbox(
        "Selecione o Nó (ou clique diretamente no desenho):", 
        options=[n['Nó'] for n in st.session_state.dados_nos],
        index=[n['Nó'] for n in st.session_state.dados_nos].index(st.session_state.no_selecionado) if st.session_state.no_selecionado in [n['Nó'] for n in st.session_state.dados_nos] else 0
    )
    st.session_state.no_selecionado = sel_n
    idx_no = next(i for i, item in enumerate(st.session_state.dados_nos) if item["Nó"] == sel_n)

    c1, c2, c3 = st.columns(3)
    ap_x = c1.checkbox("Fixar X (Dx)", value=st.session_state.dados_nos[idx_no]["Apoio X"])
    ap_y = c2.checkbox("Fixar Y (Dy)", value=st.session_state.dados_nos[idx_no]["Apoio Y"])
    ap_rot = c3.checkbox("Fixar Rotação (Rz)", value=st.session_state.dados_nos[idx_no]["Apoio Rot"])

    cf1, cf2, cf3 = st.columns(3)
    fx = cf1.number_input("Fx (kN)", value=float(st.session_state.dados_nos[idx_no]["Fx (kN)"]))
    fy = cf2.number_input("Fy (kN)", value=float(st.session_state.dados_nos[idx_no]["Fy (kN)"]))
    mz = cf3.number_input("Mz (kNm)", value=float(st.session_state.dados_nos[idx_no]["Mz (kNm)"]))

    if st.button("Salvar Condições no Nó", use_container_width=True):
        st.session_state.dados_nos[idx_no]["Apoio X"] = ap_x
        st.session_state.dados_nos[idx_no]["Apoio Y"] = ap_y
        st.session_state.dados_nos[idx_no]["Apoio Rot"] = ap_rot
        st.session_state.dados_nos[idx_no]["Fx (kN)"] = fx
        st.session_state.dados_nos[idx_no]["Fy (kN)"] = fy
        st.session_state.dados_nos[idx_no]["Mz (kNm)"] = mz
        st.rerun()

with col_p2:
    st.markdown("#### 📏 Configurar Barra")
    sel_b = st.selectbox(
        "Selecione a Barra (ou clique na linha roxa no desenho):",
        options=[b['Barra'] for b in st.session_state.dados_barras],
        index=[b['Barra'] for b in st.session_state.dados_barras].index(st.session_state.barra_selecionada) if st.session_state.barra_selecionada in [b['Barra'] for b in st.session_state.dados_barras] else 0
    )
    st.session_state.barra_selecionada = sel_b
    idx_barra = next(i for i, item in enumerate(st.session_state.dados_barras) if item["Barra"] == sel_b)

    mat_atual = st.session_state.dados_barras[idx_barra]["Material"]
    sec_atual = st.session_state.dados_barras[idx_barra]["Seção"]

    mat_escolhido = st.selectbox("Material:", LISTA_MATERIAIS, index=LISTA_MATERIAIS.index(mat_atual) if mat_atual in LISTA_MATERIAIS else 0)
    sec_escolhida = st.selectbox("Seção Perfil C / Comercial:", LISTA_SECOES, index=LISTA_SECOES.index(sec_atual) if sec_atual in LISTA_SECOES else 0)

    area_exib, inercia_exib = SECOES[sec_escolhida]
    st.caption(f"Propriedades da Seção: **Área = {area_exib} cm²** | **Ix = {inercia_exib} cm⁴**")

    c_ap1, c_ap2 = st.columns(2)
    if c_ap1.button("Salvar Nesta Barra", use_container_width=True):
        st.session_state.dados_barras[idx_barra]["Material"] = mat_escolhido
        st.session_state.dados_barras[idx_barra]["Seção"] = sec_escolhida
        st.rerun()
    if c_ap2.button("Aplicar a TODAS as Barras", use_container_width=True):
        for b in st.session_state.dados_barras:
            b["Material"] = mat_escolhido
            b["Seção"] = sec_escolhida
        st.rerun()

# -----------------------------------------------------------------------------
# 6. MOTOR MATRICIAL E DIAGRAMAS
# -----------------------------------------------------------------------------
def matriz_rigidez_local(E, A, I, L):
    k = np.zeros((6, 6))
    EA_L = (E * A) / L; EI_L = (E * I) / L
    EI_L2 = (E * I) / (L**2); EI_L3 = (E * I) / (L**3)
    k[0,0] = EA_L; k[0,3] = -EA_L; k[3,0] = -EA_L; k[3,3] = EA_L
    k[1,1] = 12*EI_L3; k[1,4] = -12*EI_L3; k[4,1] = -12*EI_L3; k[4,4] = 12*EI_L3
    k[1,2] = k[2,1] = 6*EI_L2; k[1,5] = k[5,1] = 6*EI_L2
    k[2,4] = k[4,2] = -6*EI_L2; k[4,5] = k[5,4] = -6*EI_L2
    k[2,2] = 4*EI_L; k[5,5] = 4*EI_L; k[2,5] = 2*EI_L; k[5,2] = 2*EI_L
    return k

def matriz_transformacao(dx, dy, L):
    c, s = dx/L, dy/L
    T = np.zeros((6, 6))
    T[0,0] = c; T[0,1] = s; T[1,0] = -s; T[1,1] = c; T[2,2] = 1
    T[3,3] = c; T[3,4] = s; T[4,3] = -s; T[4,4] = c; T[5,5] = 1
    return T

st.divider()

if st.button("▶️ Calcular Esforços e Gerar Diagramas", type="primary", use_container_width=True):
    num_nos = len(st.session_state.dados_nos)
    num_gdl = num_nos * 3
    K_global = np.zeros((num_gdl, num_gdl))
    F_global = np.zeros(num_gdl)
    restricoes = np.zeros(num_gdl, dtype=bool)

    no_to_idx = {row['Nó']: i for i, row in enumerate(st.session_state.dados_nos)}

    for i, row in enumerate(st.session_state.dados_nos):
        idx = i * 3
        F_global[idx]   = row['Fx (kN)'] * 1000
        F_global[idx+1] = row['Fy (kN)'] * 1000
        F_global[idx+2] = row['Mz (kNm)'] * 1000
        restricoes[idx]   = row['Apoio X']
        restricoes[idx+1] = row['Apoio Y']
        restricoes[idx+2] = row['Apoio Rot']

    info_barras = []
    for b in st.session_state.dados_barras:
        n1, n2 = b['Nó Inic.'], b['Nó Final']
        E = MATERIAIS[b['Material']] * 1e9
        A_cm2, I_cm4 = SECOES[b['Seção']]
        A = A_cm2 * 1e-4
        I = I_cm4 * 1e-8

        x1, y1 = coords_map[n1]
        x2, y2 = coords_map[n2]
        dx, dy = x2 - x1, y2 - y1
        L = np.hypot(dx, dy)

        if L > 0:
            K_loc = matriz_rigidez_local(E, A, I, L)
            T = matriz_transformacao(dx, dy, L)
            K_g = T.T @ K_loc @ T

            idx1 = no_to_idx[n1] * 3
            idx2 = no_to_idx[n2] * 3
            indices = [idx1, idx1+1, idx1+2, idx2, idx2+1, idx2+2]

            for r in range(6):
                for c in range(6):
                    K_global[indices[r], indices[c]] += K_g[r, c]

            info_barras.append({'indices': indices, 'K_loc': K_loc, 'T': T, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})

    gdl_livres = np.where(~restricoes)[0]
    U_global = np.zeros(num_gdl)

    try:
        if len(gdl_livres) > 0:
            K_livre = K_global[np.ix_(gdl_livres, gdl_livres)]
            F_livre = F_global[gdl_livres]
            U_global[gdl_livres] = np.linalg.solve(K_livre, F_livre)

        Reacoes = K_global @ U_global - F_global

        esforcos = []
        for info in info_barras:
            U_elem = U_global[info['indices']]
            u_loc = info['T'] @ U_elem
            f_loc = info['K_loc'] @ u_loc
            esforcos.append({
                **info,
                'N': f_loc[3] / 1000,
                'V': f_loc[1] / 1000,
                'M1': -f_loc[2] / 1000,
                'M2': f_loc[5] / 1000
            })

        st.success("Cálculo concluído com sucesso!")

        t1, t2, t3, t4, t5 = st.tabs(["📉 Deformada", "🟥 Normal (N)", "🟦 Transverso (V)", "🟩 Fletor (M)", "📊 Reações"])

        def plot_diagrama_plotly(esf_list, tipo):
            fig_d = go.Figure()
            for e in esf_list:
                x1, y1, x2, y2 = e['x1'], e['y1'], e['x2'], e['y2']
                L = np.hypot(x2-x1, y2-y1)
                nx, ny = -(y2-y1)/L, (x2-x1)/L
                
                v1 = e['N'] if tipo == 'N' else (e['V'] if tipo == 'V' else e['M1'])
                v2 = e['N'] if tipo == 'N' else (e['V'] if tipo == 'V' else e['M2'])
                esc = 0.05
                
                px1, py1 = x1 + nx * v1 * esc, y1 + ny * v1 * esc
                px2, py2 = x2 + nx * v2 * esc, y2 + ny * v2 * esc
                
                fig_d.add_trace(go.Scatter(x=[x1, x2], y=[y1, y2], mode='lines', line=dict(color='gray', width=1), showlegend=False))
                fig_d.add_trace(go.Scatter(
                    x=[x1, px1, px2, x2, x1],
                    y=[y1, py1, py2, y2, y1],
                    fill='toself',
                    mode='lines',
                    line=dict(width=1),
                    hoverinfo='text',
                    text=f"Valor Nó 1: {v1:.1f}<br>Valor Nó 2: {v2:.1f}",
                    showlegend=False
                ))
            fig_d.update_layout(height=400, margin=dict(l=20,r=20,t=20,b=20), xaxis=dict(scaleanchor="y", scaleratio=1))
            return fig_d

        with t1:
            fig_def = go.Figure()
            esc_def = 30
            for info in info_barras:
                idx1 = info['indices'][0:3]
                idx2 = info['indices'][3:6]
                x1_d = info['x1'] + U_global[idx1[0]] * esc_def
                y1_d = info['y1'] + U_global[idx1[1]] * esc_def
                x2_d = info['x2'] + U_global[idx2[0]] * esc_def
                y2_d = info['y2'] + U_global[idx2[1]] * esc_def
                fig_def.add_trace(go.Scatter(x=[info['x1'], info['x2']], y=[info['y1'], info['y2']], mode='lines', line=dict(color='gray', dash='dash', width=1), showlegend=False))
                fig_def.add_trace(go.Scatter(x=[x1_d, x2_d], y=[y1_d, y2_d], mode='lines+markers', line=dict(color='red', width=2), showlegend=False))
            fig_def.update_layout(height=400, margin=dict(l=20,r=20,t=20,b=20), xaxis=dict(scaleanchor="y", scaleratio=1))
            st.plotly_chart(fig_def, use_container_width=True)

        with t2:
            st.plotly_chart(plot_diagrama_plotly(esforcos, 'N'), use_container_width=True)
        with t3:
            st.plotly_chart(plot_diagrama_plotly(esforcos, 'V'), use_container_width=True)
        with t4:
            st.plotly_chart(plot_diagrama_plotly(esforcos, 'M'), use_container_width=True)

        with t5:
            res = []
            for n in st.session_state.dados_nos:
                if n['Apoio X'] or n['Apoio Y'] or n['Apoio Rot']:
                    idx = no_to_idx[n['Nó']] * 3
                    res.append({
                        "Nó": n['Nó'],
                        "Rx (kN)": round(Reacoes[idx] / 1000, 2),
                        "Ry (kN)": round(Reacoes[idx+1] / 1000, 2),
                        "R_Momento (kNm)": round(Reacoes[idx+2] / 1000, 2)
                    })
            if res:
                st.dataframe(pd.DataFrame(res), use_container_width=True)

    except np.linalg.LinAlgError:
        st.error("Estrutura instável (hipostática). Verifique se aplicou apoios suficientes para impedir translações e rotações.")
MATERIAIS = {
    "Aço Estrutural (200 GPa)": 200.0,
    "Alumínio (70 GPa)": 70.0,
    "Concreto (25 GPa)": 25.0
}

# 1. Perfis U Laminados (Padrão Americano / Gerdau)
# Valores exatos de catálogo comercial. Formato: "Nome": (Área cm², Inércia X cm⁴)
SECOES = {
    "U Laminado 3\" x 1a (76x35mm)": (5.44, 48.6),
    "U Laminado 4\" x 1a (101x40mm)": (7.15, 106.0),
    "U Laminado 6\" x 1a (152x48mm)": (10.48, 368.0),
    "U Laminado 8\" x 1a (203x57mm)": (14.59, 886.0),
    "U Laminado 10\" x 1a (254x66mm)": (19.34, 1806.0),
    "U Laminado 12\" x 1a (304x77mm)": (24.31, 3284.0),
    
    # Seções genéricas para fundações ou pilares de betão
    "Tubo Quadrado 100x5": (19.0, 280.0),
    "Viga Retangular 15x30": (450.0, 33750.0),
    "Barra Maciça 10x10": (100.0, 833.0)
}

# 2. Gerador Automático de Perfis U Dobrados (Chapas Finas a Frio)
# Espessuras comerciais (Chapa MSG : Espessura em mm)
chapas = {18: 1.20, 16: 1.50, 14: 1.90, 13: 2.25, 12: 2.65, 11: 3.00, 10: 3.40}

# Combinações de Altura x Base (em mm) solicitadas (de 75x25 até 200x40)
dimensoes_dobrados = [
    (75, 25), (75, 40), (100, 40), (100, 50), 
    (120, 40), (150, 50), (200, 40)
]

for h_mm, b_mm in dimensoes_dobrados:
    for chapa, e_mm in chapas.items():
        # Conversão para centímetros (unidade do motor matemático)
        h = h_mm / 10.0
        b = b_mm / 10.0
        e = e_mm / 10.0
        
        # Área da seção transversal
        area = 2 * (b * e) + (h - 2*e) * e
        
        # Momento de Inércia em X (Flexão no eixo forte) 
        # Fórmula: Ix_alma + 2 * (Ix_mesa + Steiner_mesa)
        ix_alma = (e * (h - 2*e)**3) / 12
        ix_mesa_proprio = (b * e**3) / 12
        area_mesa = b * e
        dist_mesa = (h - e) / 2
        steiner_mesa = area_mesa * (dist_mesa**2)
        
        inercia_x = ix_alma + 2 * (ix_mesa_proprio + steiner_mesa)
        
        # Adiciona o perfil ao catálogo com valores arredondados para 2 casas decimais
        nome_perfil = f"U Dobrado {h_mm}x{b_mm}x{e_mm} (Chapa {chapa})"
        SECOES[nome_perfil] = (round(area, 2), round(inercia_x, 2))

# --- ESTADO DA SESSÃO (Memória do App) ---
if 'dados_nos' not in st.session_state:
    st.session_state.dados_nos = []
if 'dados_barras' not in st.session_state:
    st.session_state.dados_barras = []

st.subheader("1. Importar Geometria (DXF)")
arquivo_dxf = st.file_uploader("Selecione o arquivo .dxf gerado pelo seu CAD", type=['dxf'])

if arquivo_dxf is not None and st.button("Processar Novo DXF"):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp:
            tmp.write(arquivo_dxf.getvalue())
            tmp_path = tmp.name
            
        doc = ezdxf.readfile(tmp_path)
        os.remove(tmp_path)
        msp = doc.modelspace()
        
        nos_set = set()
        barras_dxf = []
        
        for linha in msp.query('LINE'):
            start = (round(linha.dxf.start.x, 3), round(linha.dxf.start.y, 3))
            end = (round(linha.dxf.end.x, 3), round(linha.dxf.end.y, 3))
            nos_set.update([start, end])
            barras_dxf.append((start, end))
            
        for polyline in msp.query('LWPOLYLINE'):
            points = [(round(p[0], 3), round(p[1], 3)) for p in polyline.get_points(format='xy')]
            for i in range(len(points) - 1):
                start, end = points[i], points[i+1]
                nos_set.update([start, end])
                barras_dxf.append((start, end))
            
        nos_lista = sorted(list(nos_set), key=lambda x: (x[0], x[1]))
        no_map = {no: i+1 for i, no in enumerate(nos_lista)}
        
        st.session_state.dados_nos = [{"Nó": no_map[no], "X": no[0], "Y": no[1], "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0} for no in nos_lista]
        st.session_state.dados_barras = [{"Barra": i+1, "Nó Inic.": no_map[barra[0]], "Nó Final": no_map[barra[1]], "Material": "Aço (200 GPa)", "Seção": "Perfil W200x31.3"} for i, barra in enumerate(barras_dxf)]
        
        st.success("Geometria carregada! Use o painel abaixo para aplicar cargas e apoios.")
    except Exception as e:
        st.error(f"Erro ao ler DXF: {e}")

# Layout Principal (Desenho à esquerda, Painel de Ferramentas à direita)
if st.session_state.dados_nos:
    st.divider()
    col_plot, col_tools = st.columns([2, 1])
    
    # Dicionário rápido de coordenadas para o plot
    coords_nos = {row['Nó']: (row['X'], row['Y']) for row in st.session_state.dados_nos}
    
    with col_plot:
        st.subheader("Visualização da Estrutura")
        mostrar_ids = st.checkbox("Mostrar IDs dos Nós", value=True)
        fig_preview, ax_preview = plt.subplots(figsize=(10, 5)) 
        
        for row in st.session_state.dados_barras:
            n1, n2 = row['Nó Inic.'], row['Nó Final']
            if n1 in coords_nos and n2 in coords_nos:
                x1, y1 = coords_nos[n1]
                x2, y2 = coords_nos[n2]
                ax_preview.plot([x1, x2], [y1, y2], color='blue', linewidth=1.5, zorder=1)
                
        for no_id, (x, y) in coords_nos.items():
            ax_preview.scatter(x, y, color='red', s=30, zorder=2)
            if mostrar_ids:
                ax_preview.annotate(f"{int(no_id)}", (x, y), textcoords="offset points", xytext=(4,4), ha='left', fontsize=9, color='darkred', fontweight='bold')

        ax_preview.set_aspect('equal')
        ax_preview.grid(True, linestyle=':', alpha=0.6)
        st.pyplot(fig_preview)

    with col_tools:
        st.subheader("Painel de Atribuição Rápida")
        st.write("Selecione o Nó no gráfico e aplique as condições:")
        
        no_selecionado = st.selectbox("📌 Selecionar Nó:", options=[row['Nó'] for row in st.session_state.dados_nos])
        
        # Encontra os dados atuais do nó selecionado
        idx_no = next((i for i, item in enumerate(st.session_state.dados_nos) if item["Nó"] == no_selecionado), None)
        
        if idx_no is not None:
            c1, c2, c3 = st.columns(3)
            ap_x = c1.checkbox("Fixar X", value=st.session_state.dados_nos[idx_no]["Apoio X"])
            ap_y = c2.checkbox("Fixar Y", value=st.session_state.dados_nos[idx_no]["Apoio Y"])
            ap_rot = c3.checkbox("Fixar Rot", value=st.session_state.dados_nos[idx_no]["Apoio Rot"])
            
            fx = st.number_input("Carga Fx (kN)", value=float(st.session_state.dados_nos[idx_no]["Fx (kN)"]))
            fy = st.number_input("Carga Fy (kN)", value=float(st.session_state.dados_nos[idx_no]["Fy (kN)"]))
            
            if st.button("Aplicar ao Nó"):
                st.session_state.dados_nos[idx_no]["Apoio X"] = ap_x
                st.session_state.dados_nos[idx_no]["Apoio Y"] = ap_y
                st.session_state.dados_nos[idx_no]["Apoio Rot"] = ap_rot
                st.session_state.dados_nos[idx_no]["Fx (kN)"] = fx
                st.session_state.dados_nos[idx_no]["Fy (kN)"] = fy
                st.rerun()

    st.divider()
    
    st.subheader("Tabelas de Dados (Propriedades pré-definidas)")
    st.write("Você também pode editar todo o sistema em massa utilizando as tabelas interativas.")
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        # Tabela de nós
        tabela_nos = st.data_editor(pd.DataFrame(st.session_state.dados_nos), hide_index=True, use_container_width=True)
    
    with col_t2:
        # Tabela de barras com Menus Suspensos (Dropdowns) nativos
        tabela_barras = st.data_editor(
            pd.DataFrame(st.session_state.dados_barras), 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "Material": st.column_config.SelectboxColumn(
                    "Material da Barra", options=list(MATERIAIS.keys()), required=True
                ),
                "Seção": st.column_config.SelectboxColumn(
                    "Perfil da Seção", options=list(SECOES.keys()), required=True
                )
            }
        )

    # Botão de Cálculo final (Simplificado para o exemplo)
    if st.button("▶️ Calcular Estrutura", type="primary", use_container_width=True):
        # Conversão das bibliotecas para os motores matemáticos
        # (Este bloco garante que o nome selecionado vire números de E, A, I reais)
        barras_prontas = []
        for _, row in tabela_barras.iterrows():
            E_val = MATERIAIS[row["Material"]]
            A_val, I_val = SECOES[row["Seção"]]
            barras_prontas.append({
                "Nó Inic.": row["Nó Inic."],
                "Nó Final": row["Nó Final."],
                "E (GPa)": E_val,
                "A (cm²)": A_val,
                "I (cm⁴)": I_val
            })
            
        st.success("As propriedades foram lidas corretamente! (A lógica de cálculo matricial já pode ser conectada aqui utilizando os valores E, A e I gerados acima).")
