import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import ezdxf
import tempfile
import os

st.set_page_config(page_title="Ftool Web - Cargas Locais e Globais", layout="wide")
st.title("🏗️ Ftool Web: Cargas Locais/Globais, Multi-Seleção e Perfis C")

# -----------------------------------------------------------------------------
# 1. CATÁLOGO DE MATERIAIS E SEÇÕES (Laminados e Dobrados C)
# -----------------------------------------------------------------------------
MATERIAIS = {
    "Aço Estrutural (200 GPa)": 200.0,
    "Alumínio (70 GPa)": 70.0,
    "Concreto (25 GPa)": 25.0
}

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
        area = 2 * (b * e) + (h - 2 * e) * e
        ix_alma = (e * (h - 2 * e)**3) / 12
        ix_mesa = (b * e**3) / 12
        dist_m = (h - e) / 2
        inercia_x = ix_alma + 2 * (ix_mesa + (b * e) * (dist_m**2))
        nome_c = f"U Dobrado {h_mm}x{b_mm}x{e_mm}mm (Chapa {chapa_num})"
        SECOES[nome_c] = (round(area, 2), round(inercia_x, 2))

LISTA_SECOES = list(SECOES.keys())
LISTA_MATERIAIS = list(MATERIAIS.keys())

# -----------------------------------------------------------------------------
# 2. FUNÇÕES GEOMÉTRICAS: SEGMENTAÇÃO DXF, CAIXA E ÂNGULOS LOCAIS
# -----------------------------------------------------------------------------
def segmentar_linhas_com_nos(linhas_brutas, nos_unicos, tol=0.005):
    """Subdivide linhas contínuas em barras individuais onde nós intermediários se encontram."""
    barras_finais = []
    for p1, p2 in linhas_brutas:
        x1, y1 = p1
        x2, y2 = p2
        dx, dy = x2 - x1, y2 - y1
        L = np.hypot(dx, dy)
        if L < tol:
            continue
        nos_no_segmento = []
        for no in nos_unicos:
            xn, yn = no
            if np.hypot(xn - x1, yn - y1) < tol or np.hypot(xn - x2, yn - y2) < tol:
                continue
            t = ((xn - x1) * dx + (yn - y1) * dy) / (L * L)
            if 0 < t < 1:
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                if np.hypot(xn - proj_x, yn - proj_y) < tol:
                    nos_no_segmento.append((t, no))
        if not nos_no_segmento:
            barras_finais.append((p1, p2))
        else:
            nos_no_segmento.sort(key=lambda item: item[0])
            pts = [p1] + [item[1] for item in nos_no_segmento] + [p2]
            for i in range(len(pts) - 1):
                if np.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1]) > tol:
                    barras_finais.append((pts[i], pts[i+1]))

    barras_unicas = []
    set_vistas = set()
    for p1, p2 in barras_finais:
        chave = tuple(sorted([p1, p2]))
        if chave not in set_vistas:
            set_vistas.add(chave)
            barras_unicas.append((p1, p2))
    return barras_unicas

def linha_intercepta_caixa(x1, y1, x2, y2, xmin, xmax, ymin, ymax):
    """Verifica se um segmento de reta passa por dentro ou toca uma caixa delimitadora."""
    if (xmin <= x1 <= xmax and ymin <= y1 <= ymax) or (xmin <= x2 <= xmax and ymin <= y2 <= ymax):
        return True
    xm, ym = (x1 + x2) / 2, (y1 + y2) / 2
    if xmin <= xm <= xmax and ymin <= ym <= ymax:
        return True
    if max(x1, x2) < xmin or min(x1, x2) > xmax or max(y1, y2) < ymin or min(y1, y2) > ymax:
        return False
    def ccw(A, B, C):
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
    def cruzam(A, B, C, D):
        return (ccw(A,C,D) != ccw(B,C,D)) and (ccw(A,B,C) != ccw(A,B,D))

    A, B = (x1, y1), (x2, y2)
    cantos = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    for i in range(4):
        C, D = cantos[i], cantos[(i+1)%4]
        if cruzam(A, B, C, D):
            return True
    return False

def calcular_angulos_locais_nos(sel_nos, dados_barras, coords_map):
    """Determina a inclinação local média da barra/banzo conectada a cada nó selecionado."""
    angulos = {}
    for nid in sel_nos:
        ang_candidatos = []
        for b in dados_barras:
            n1, n2 = b['Nó Inic.'], b['Nó Final']
            if nid in (n1, n2):
                outro = n2 if n1 == nid else n1
                if outro in sel_nos and n1 in coords_map and n2 in coords_map:
                    xa, ya = coords_map[min(n1, n2, key=lambda k: coords_map[k][0])]
                    xb, yb = coords_map[max(n1, n2, key=lambda k: coords_map[k][0])]
                    dx, dy = xb - xa, yb - ya
                    if np.hypot(dx, dy) > 1e-4:
                        ang_candidatos.append(np.arctan2(dy, dx))
        if not ang_candidatos:
            todas_conectadas = []
            for b in dados_barras:
                n1, n2 = b['Nó Inic.'], b['Nó Final']
                if nid in (n1, n2) and n1 in coords_map and n2 in coords_map:
                    xa, ya = coords_map[min(n1, n2, key=lambda k: coords_map[k][0])]
                    xb, yb = coords_map[max(n1, n2, key=lambda k: coords_map[k][0])]
                    dx, dy = xb - xa, yb - ya
                    if np.hypot(dx, dy) > 1e-4:
                        todas_conectadas.append(np.arctan2(dy, dx))
            if todas_conectadas:
                todas_conectadas.sort(key=lambda a: abs(a))
                ang_candidatos.append(todas_conectadas[0])
        angulos[nid] = float(np.mean(ang_candidatos)) if ang_candidatos else 0.0
    return angulos

# -----------------------------------------------------------------------------
# 3. ESTADO DA SESSÃO
# -----------------------------------------------------------------------------
if 'dados_nos' not in st.session_state:
    st.session_state.dados_nos = []
if 'dados_barras' not in st.session_state:
    st.session_state.dados_barras = []
if 'sel_nos' not in st.session_state:
    st.session_state.sel_nos = [1]
if 'sel_barras' not in st.session_state:
    st.session_state.sel_barras = [1]
if 'last_processed_sig' not in st.session_state:
    st.session_state.last_processed_sig = None

# -----------------------------------------------------------------------------
# 4. UPLOAD DXF
# -----------------------------------------------------------------------------
st.subheader("1. Importar Geometria (DXF)")
arquivo_dxf = st.file_uploader("Arraste seu arquivo .dxf aqui", type=['dxf'])

if arquivo_dxf is not None and st.button("Processar DXF com Segmentação Automática"):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp:
            tmp.write(arquivo_dxf.getvalue())
            tmp_path = tmp.name

        doc = ezdxf.readfile(tmp_path)
        os.remove(tmp_path)
        msp = doc.modelspace()

        linhas_brutas = []
        nos_brutos = set()

        for linha in msp.query('LINE'):
            p1 = (round(linha.dxf.start.x, 3), round(linha.dxf.start.y, 3))
            p2 = (round(linha.dxf.end.x, 3), round(linha.dxf.end.y, 3))
            if p1 != p2:
                linhas_brutas.append((p1, p2))
                nos_brutos.update([p1, p2])

        for polyline in msp.query('LWPOLYLINE'):
            pts = [(round(p[0], 3), round(p[1], 3)) for p in polyline.get_points(format='xy')]
            for i in range(len(pts) - 1):
                if pts[i] != pts[i+1]:
                    linhas_brutas.append((pts[i], pts[i+1]))
                    nos_brutos.update([pts[i], pts[i+1]])

        for polyline in msp.query('POLYLINE'):
            try:
                pts = [(round(v.dxf.location.x, 3), round(v.dxf.location.y, 3)) for v in polyline.vertices]
                for i in range(len(pts) - 1):
                    if pts[i] != pts[i+1]:
                        linhas_brutas.append((pts[i], pts[i+1]))
                        nos_brutos.update([pts[i], pts[i+1]])
            except Exception:
                pass

        barras_dxf = segmentar_linhas_com_nos(linhas_brutas, nos_brutos, tol=0.005)

        nos_set_final = set()
        for b in barras_dxf:
            nos_set_final.update([b[0], b[1]])

        nos_lista = sorted(list(nos_set_final), key=lambda pt: (pt[0], pt[1]))
        no_map = {pt: i+1 for i, pt in enumerate(nos_lista)}

        st.session_state.dados_nos = [
            {"Nó": no_map[n], "X": n[0], "Y": n[1], "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0}
            for n in nos_lista
        ]
        st.session_state.dados_barras = [
            {"Barra": i+1, "Nó Inic.": no_map[b[0]], "Nó Final": no_map[b[1]], "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[0]}
            for i, b in enumerate(barras_dxf)
        ]
        st.session_state.sel_nos = [1]
        st.session_state.sel_barras = [1]
        st.session_state.last_processed_sig = None
        st.success(f"Geometria segmentada: {len(nos_lista)} nós e {len(barras_dxf)} barras individuais geradas.")
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")

if not st.session_state.dados_nos:
    st.session_state.dados_nos = [
        {"Nó": 1, "X": 0.0, "Y": 0.0, "Apoio X": True, "Apoio Y": True, "Apoio Rot": True, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
        {"Nó": 2, "X": 0.0, "Y": 4.0, "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 15.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
        {"Nó": 3, "X": 5.0, "Y": 4.0, "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": -20.0, "Mz (kNm)": 0.0},
        {"Nó": 4, "X": 5.0, "Y": 0.0, "Apoio X": True, "Apoio Y": True, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
    ]
    st.session_state.dados_barras = [
        {"Barra": 1, "Nó Inic.": 1, "Nó Final": 2, "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[0]},
        {"Barra": 2, "Nó Inic.": 2, "Nó Final": 3, "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[1]},
        {"Barra": 3, "Nó Inic.": 3, "Nó Final": 4, "Material": LISTA_MATERIAIS[0], "Seção": LISTA_SECOES[0]},
    ]

# -----------------------------------------------------------------------------
# 5. CONTROLES DE INTERAÇÃO E EXIBIÇÃO
# -----------------------------------------------------------------------------
st.subheader("2. Geometria Interativa")

col_ferramentas1, col_ferramentas2, col_ferramentas3 = st.columns([1.1, 1.1, 0.9])
with col_ferramentas1:
    modo_mouse = st.radio(
        "Ação ao Arrastar o Mouse:",
        ["📦 Seleção por Caixa (Retângulo)", "🖐️ Mover / Enquadrar (Pan)"],
        horizontal=False
    )
with col_ferramentas2:
    alvo_caixa = st.radio(
        "Ao arrastar a caixa, selecionar:",
        ["Ambos (Nós e Barras)", "Apenas Barras", "Apenas Nós"],
        horizontal=False
    )
with col_ferramentas3:
    modo_selecao = st.radio(
        "Modo de Seleção:",
        ["➕ Acumulativo", "🔄 Substituir"],
        horizontal=False
    )
    mostrar_ids = st.checkbox("Mostrar Rótulos dos Nós", value=True)
    mostrar_valores_cargas = st.checkbox("Mostrar Valores nas Cargas", value=True)

# -----------------------------------------------------------------------------
# 6. MONTAGEM DO GRÁFICO PLOTLY
# -----------------------------------------------------------------------------
coords_map = {n['Nó']: (n['X'], n['Y']) for n in st.session_state.dados_nos}
fig = go.Figure()

all_x = [n['X'] for n in st.session_state.dados_nos]
all_y = [n['Y'] for n in st.session_state.dados_nos]
span_x = max(all_x) - min(all_x) if all_x else 10.0
span_y = max(all_y) - min(all_y) if all_y else 2.0
s_dim = max(span_x, span_y, 1.0) * 0.025

# 6.1 Barras da Estrutura
x_norm, y_norm = [], []
x_sel, y_sel = [], []

for b in st.session_state.dados_barras:
    n1, n2 = b['Nó Inic.'], b['Nó Final']
    if n1 in coords_map and n2 in coords_map:
        x1, y1 = coords_map[n1]
        x2, y2 = coords_map[n2]
        if b['Barra'] in st.session_state.sel_barras:
            x_sel.extend([x1, x2, None])
            y_sel.extend([y1, y2, None])
        else:
            x_norm.extend([x1, x2, None])
            y_norm.extend([y1, y2, None])

if x_norm:
    fig.add_trace(go.Scatter(x=x_norm, y=y_norm, mode='lines', line=dict(color='#1f77b4', width=2), hoverinfo='skip', showlegend=False))
if x_sel:
    fig.add_trace(go.Scatter(x=x_sel, y=y_sel, mode='lines', line=dict(color='magenta', width=4.5), hoverinfo='skip', showlegend=False))

# 6.2 Marcadores Centrais de Barras (Losangos Clicáveis)
x_mid, y_mid, ids_barras, hover_barras = [], [], [], []
for b in st.session_state.dados_barras:
    n1, n2 = b['Nó Inic.'], b['Nó Final']
    if n1 in coords_map and n2 in coords_map:
        x1, y1 = coords_map[n1]
        x2, y2 = coords_map[n2]
        x_mid.append((x1 + x2) / 2)
        y_mid.append((y1 + y2) / 2)
        ids_barras.append(b['Barra'])
        hover_barras.append(f"<b>Barra {b['Barra']}</b><br>Nós: {n1} → {n2}<br>Seção: {b['Seção']}<br>Mat: {b['Material']}")

cores_barras = ['magenta' if bid in st.session_state.sel_barras else '#4682b4' for bid in ids_barras]
tamanhos_barras = [12 if bid in st.session_state.sel_barras else 8 for bid in ids_barras]

fig.add_trace(go.Scatter(
    x=x_mid,
    y=y_mid,
    mode='markers',
    marker=dict(size=tamanhos_barras, symbol='diamond', color=cores_barras, line=dict(width=1, color='white')),
    hoverinfo='text',
    hovertext=hover_barras,
    customdata=[f"barra_{bid}" for bid in ids_barras],
    name='Barras'
))

# 6.3 Símbolos de Apoios e Cargas
for n in st.session_state.dados_nos:
    x, y = n['X'], n['Y']
    ap_x, ap_y, ap_rot = n['Apoio X'], n['Apoio Y'], n['Apoio Rot']
    fx, fy, mz = n['Fx (kN)'], n['Fy (kN)'], n['Mz (kNm)']

    if ap_x and ap_y and ap_rot:
        fig.add_shape(type="rect", x0=x - 0.7*s_dim, y0=y - 0.7*s_dim, x1=x + 0.7*s_dim, y1=y, line=dict(color="#006400", width=1.5), fillcolor="rgba(0, 100, 0, 0.45)")
        fig.add_shape(type="line", x0=x - 0.9*s_dim, y0=y - 0.7*s_dim, x1=x + 0.9*s_dim, y1=y - 0.7*s_dim, line=dict(color="#006400", width=2.5))
    elif ap_x and ap_y and not ap_rot:
        fig.add_shape(type="path", path=f"M {x} {y} L {x - 0.75*s_dim} {y - 0.9*s_dim} L {x + 0.75*s_dim} {y - 0.9*s_dim} Z", line=dict(color="#006400", width=1.5), fillcolor="rgba(0, 100, 0, 0.35)")
        fig.add_shape(type="line", x0=x - 0.95*s_dim, y0=y - 0.9*s_dim, x1=x + 0.95*s_dim, y1=y - 0.9*s_dim, line=dict(color="#006400", width=2.5))
    elif not ap_x and ap_y:
        fig.add_shape(type="path", path=f"M {x} {y} L {x - 0.65*s_dim} {y - 0.75*s_dim} L {x + 0.65*s_dim} {y - 0.75*s_dim} Z", line=dict(color="#006400", width=1.5), fillcolor="rgba(0, 100, 0, 0.25)")
        fig.add_shape(type="line", x0=x - 0.85*s_dim, y0=y - 0.95*s_dim, x1=x + 0.85*s_dim, y1=y - 0.95*s_dim, line=dict(color="#006400", width=2))
    elif ap_x and not ap_y:
        fig.add_shape(type="path", path=f"M {x} {y} L {x - 0.75*s_dim} {y - 0.65*s_dim} L {x - 0.75*s_dim} {y + 0.65*s_dim} Z", line=dict(color="#006400", width=1.5), fillcolor="rgba(0, 100, 0, 0.25)")
        fig.add_shape(type="line", x0=x - 0.95*s_dim, y0=y - 0.85*s_dim, x1=x - 0.95*s_dim, y1=y + 0.85*s_dim, line=dict(color="#006400", width=2))

    if abs(fx) > 0.001 or abs(fy) > 0.001:
        f_mag = float(np.hypot(fx, fy))
        ux, uy = fx / f_mag, fy / f_mag
        texto_seta = f"{f_mag:.1f} kN" if mostrar_valores_cargas else ""
        fig.add_annotation(
            x=x, y=y, ax=-50 * ux, ay=50 * uy, xref="x", yref="y", axref="pixel", ayref="pixel",
            text=texto_seta, showarrow=True, arrowhead=2, arrowsize=1.6, arrowwidth=2.5,
            arrowcolor="red", font=dict(color="red", size=9, family="Arial", weight="bold"),
            bgcolor="rgba(255, 255, 255, 0.85)" if texto_seta else None,
            bordercolor="red" if texto_seta else None,
            borderwidth=1 if texto_seta else 0,
            borderpad=1
        )

    if abs(mz) > 0.001:
        simb = "↻" if mz < 0 else "↺"
        fig.add_annotation(
            x=x, y=y, text=f"{simb} {abs(mz):.1f} kNm", showarrow=False, yshift=18,
            font=dict(color="purple", size=10, weight="bold"), bgcolor="rgba(255, 255, 255, 0.85)",
            bordercolor="purple", borderwidth=1
        )

# 6.4 Nós da Estrutura
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
    
    f_res = np.hypot(n['Fx (kN)'], n['Fy (kN)'])
    txt_cargas = f"Carga: {f_res:.2f} kN (Fx: {n['Fx (kN)']:.2f}, Fy: {n['Fy (kN)']:.2f})" if f_res > 0.001 else "Sem carga"
    txt_hover.append(f"<b>Nó {n['Nó']}</b><br>Coord: ({n['X']:.3f}, {n['Y']:.3f})<br>{txt_ap}<br>{txt_cargas}")

cores_nos = ['yellow' if nid in st.session_state.sel_nos else 'red' for nid in nos_ids]
tamanhos_nos = [12 if nid in st.session_state.sel_nos else 8 for nid in nos_ids]

fig.add_trace(go.Scatter(
    x=x_pts,
    y=y_pts,
    mode='markers+text' if mostrar_ids else 'markers',
    marker=dict(size=tamanhos_nos, color=cores_nos, line=dict(width=1, color='black')),
    text=[str(nid) for nid in nos_ids],
    textposition="top center",
    textfont=dict(size=9, color='darkred'),
    hoverinfo='text',
    hovertext=txt_hover,
    customdata=[f"no_{nid}" for nid in nos_ids],
    name='Nós'
))

drag_val = "select" if "Caixa" in modo_mouse else "pan"

fig.update_layout(
    height=450,
    margin=dict(l=20, r=20, t=20, b=20),
    xaxis=dict(scaleanchor="y", scaleratio=1, showgrid=True, zeroline=False),
    yaxis=dict(showgrid=True, zeroline=False),
    dragmode=drag_val,
    clickmode="event+select",
    uirevision="persist_zoom"
)

config_grafico = {
    'scrollZoom': True,
    'displaylogo': False,
    'modeBarButtonsToAdd': ['select2d', 'pan2d']
}

event_chart = st.plotly_chart(
    fig, 
    use_container_width=True, 
    on_select="rerun", 
    key="main_plot", 
    config=config_grafico
)

# -----------------------------------------------------------------------------
# 7. PROCESSAMENTO GEOMÉTRICO DA SELEÇÃO
# -----------------------------------------------------------------------------
if event_chart and "selection" in event_chart:
    sel = event_chart["selection"]
    boxes = sel.get("box", [])
    pts = sel.get("points", [])

    if boxes or pts:
        sig = f"box:{boxes}|pts:{[p.get('customdata') for p in pts if 'customdata' in p]}"
        
        if sig != st.session_state.last_processed_sig:
            st.session_state.last_processed_sig = sig
            box_nos, box_barras = [], []

            if boxes:
                for b in boxes:
                    xb = b.get("x", [])
                    yb = b.get("y", [])
                    if len(xb) >= 2 and len(yb) >= 2:
                        xmin, xmax = min(xb), max(xb)
                        ymin, ymax = min(yb), max(yb)

                        if alvo_caixa in ["Ambos (Nós e Barras)", "Apenas Nós"]:
                            for n in st.session_state.dados_nos:
                                if xmin <= n['X'] <= xmax and ymin <= n['Y'] <= ymax:
                                    box_nos.append(n['Nó'])

                        if alvo_caixa in ["Ambos (Nós e Barras)", "Apenas Barras"]:
                            for bar in st.session_state.dados_barras:
                                n1, n2 = bar['Nó Inic.'], bar['Nó Final']
                                if n1 in coords_map and n2 in coords_map:
                                    x1, y1 = coords_map[n1]
                                    x2, y2 = coords_map[n2]
                                    if linha_intercepta_caixa(x1, y1, x2, y2, xmin, xmax, ymin, ymax):
                                        box_barras.append(bar['Barra'])

            elif pts:
                for p in pts:
                    cdata = str(p.get("customdata", ""))
                    if cdata.startswith("no_"):
                        box_nos.append(int(cdata.replace("no_", "")))
                    elif cdata.startswith("barra_"):
                        box_barras.append(int(cdata.replace("barra_", "")))

            if "Acumulativo" in modo_selecao:
                if not boxes and len(pts) == 1:
                    if box_barras:
                        bid = box_barras[0]
                        if bid in st.session_state.sel_barras:
                            st.session_state.sel_barras.remove(bid)
                        else:
                            st.session_state.sel_barras.append(bid)
                    if box_nos:
                        nid = box_nos[0]
                        if nid in st.session_state.sel_nos:
                            st.session_state.sel_nos.remove(nid)
                        else:
                            st.session_state.sel_nos.append(nid)
                else:
                    if box_barras:
                        st.session_state.sel_barras = sorted(list(set(st.session_state.sel_barras).union(box_barras)))
                    if box_nos:
                        st.session_state.sel_nos = sorted(list(set(st.session_state.sel_nos).union(box_nos)))
            else:
                if alvo_caixa in ["Ambos (Nós e Barras)", "Apenas Barras"]:
                    st.session_state.sel_barras = sorted(list(set(box_barras)))
                if alvo_caixa in ["Ambos (Nós e Barras)", "Apenas Nós"]:
                    st.session_state.sel_nos = sorted(list(set(box_nos)))

            st.rerun()

# -----------------------------------------------------------------------------
# 8. PAINEL DE ATRIBUIÇÃO EM LOTE: LOCAL VS GLOBAL
# -----------------------------------------------------------------------------
st.subheader("3. Painel de Atribuição em Lote")
col_p1, col_p2 = st.columns(2)

with col_p1:
    st.markdown("#### 📍 Configurar Nós Selecionados")
    todos_nos_ids = [n['Nó'] for n in st.session_state.dados_nos]
    nos_selecionados_validos = [nid for nid in st.session_state.sel_nos if nid in todos_nos_ids]

    sel_nos_input = st.multiselect(
        "Nós Selecionados (ou arraste uma caixa no desenho):",
        options=todos_nos_ids,
        default=nos_selecionados_validos
    )
    if set(sel_nos_input) != set(st.session_state.sel_nos):
        st.session_state.sel_nos = sel_nos_input
        st.session_state.last_processed_sig = "manual_nos"
        st.rerun()

    c_btn1, c_btn2 = st.columns(2)
    if c_btn1.button("Selecionar Todos os Nós"):
        st.session_state.sel_nos = todos_nos_ids
        st.session_state.last_processed_sig = "manual_all_nos"
        st.rerun()
    if c_btn2.button("Limpar Seleção de Nós"):
        st.session_state.sel_nos = []
        st.session_state.last_processed_sig = "manual_clear_nos"
        st.rerun()

    st.caption(f"**{len(st.session_state.sel_nos)} nó(s) selecionado(s)**")

    st.markdown("**Apoios / Condições de Contorno:**")
    c1, c2, c3 = st.columns(3)
    ap_x = c1.checkbox("Fixar X (Dx)", value=False)
    ap_y = c2.checkbox("Fixar Y (Dy)", value=False)
    ap_rot = c3.checkbox("Fixar Rotação (Rz)", value=False)

    st.markdown("**Cargas nos Nós:**")
    sistema_carga = st.radio(
        "Sistema de Direção das Cargas:",
        ["🌐 Global (Horizontal X / Vertical Y)", "📐 Local (Perpendicular ⟂ / Paralela ∥ ao Banzo)"],
        horizontal=False
    )

    angulos_locais_dict = calcular_angulos_locais_nos(st.session_state.sel_nos, st.session_state.dados_barras, coords_map)
    ang_medio_deg = float(np.degrees(np.mean(list(angulos_locais_dict.values())))) if angulos_locais_dict else 0.0

    if "Global" in sistema_carga:
        cf1, cf2, cf3 = st.columns(3)
        fx_in = cf1.number_input("Fx Global (kN)", value=0.0, help="+ Direita, - Esquerda")
        fy_in = cf2.number_input("Fy Global (kN)", value=0.0, help="+ Cima, - Baixo (Gravidade)")
        mz_in = cf3.number_input("Mz (kNm)", value=0.0)
    else:
        st.info(f"📐 Inclinação detectada para os nós selecionados: **{ang_medio_deg:.2f}°**")
        modo_ang = st.radio("Definição da Inclinação Local:", ["Automático (detectado pelo alinhamento das barras)", "Manual (digitar ângulo)"], horizontal=True)
        if "Manual" in modo_ang:
            ang_ref_deg = st.number_input("Ângulo de Referência (°):", value=round(ang_medio_deg, 2))
        else:
            ang_ref_deg = None

        cf1, cf2, cf3 = st.columns(3)
        f_perp = cf1.number_input("F⟂ Normal / Perpendicular (kN)", value=0.0, help="+ Para fora (Sucção), - Para dentro (Pressão/Sobrecarga)")
        f_par = cf2.number_input("F∥ Tangencial / Paralela (kN)", value=0.0, help="+ Ao longo da inclinação (+X), - Sentido oposto (-X)")
        mz_in = cf3.number_input("Mz (kNm)", value=0.0)
        st.caption("💡 *Exemplo de Vento: F⟂ positivo (+) = sucção perpendicular; F⟂ negativo (-) = sobrepressão perpendicular.*")

    if st.button("Salvar Condições nos Nós Selecionados", type="primary", use_container_width=True):
        if not st.session_state.sel_nos:
            st.warning("Nenhum nó selecionado.")
        else:
            for nid in st.session_state.sel_nos:
                idx = next((i for i, item in enumerate(st.session_state.dados_nos) if item["Nó"] == nid), None)
                if idx is not None:
                    st.session_state.dados_nos[idx]["Apoio X"] = ap_x
                    st.session_state.dados_nos[idx]["Apoio Y"] = ap_y
                    st.session_state.dados_nos[idx]["Apoio Rot"] = ap_rot
                    st.session_state.dados_nos[idx]["Mz (kNm)"] = mz_in

                    if "Global" in sistema_carga:
                        st.session_state.dados_nos[idx]["Fx (kN)"] = fx_in
                        st.session_state.dados_nos[idx]["Fy (kN)"] = fy_in
                    else:
                        theta = np.radians(ang_ref_deg) if ang_ref_deg is not None else angulos_locais_dict.get(nid, 0.0)
                        # Decomposição exata: Tangente = (cos θ, sin θ), Normal = (-sin θ, cos θ)
                        fx_calc = f_par * np.cos(theta) - f_perp * np.sin(theta)
                        fy_calc = f_par * np.sin(theta) + f_perp * np.cos(theta)
                        st.session_state.dados_nos[idx]["Fx (kN)"] = round(fx_calc, 4)
                        st.session_state.dados_nos[idx]["Fy (kN)"] = round(fy_calc, 4)

            st.success(f"Condições aplicadas a {len(st.session_state.sel_nos)} nó(s)!")
            st.rerun()

with col_p2:
    st.markdown("#### 📏 Configurar Barras Selecionadas")
    todas_barras_ids = [b['Barra'] for b in st.session_state.dados_barras]
    barras_selecionadas_validas = [bid for bid in st.session_state.sel_barras if bid in todas_barras_ids]

    sel_barras_input = st.multiselect(
        "Barras Selecionadas (ou arraste uma caixa no desenho):",
        options=todas_barras_ids,
        default=barras_selecionadas_validas
    )
    if set(sel_barras_input) != set(st.session_state.sel_barras):
        st.session_state.sel_barras = sel_barras_input
        st.session_state.last_processed_sig = "manual_barras"
        st.rerun()

    c_bar1, c_bar2 = st.columns(2)
    if c_bar1.button("Selecionar Todas as Barras"):
        st.session_state.sel_barras = todas_barras_ids
        st.session_state.last_processed_sig = "manual_all_barras"
        st.rerun()
    if c_bar2.button("Limpar Seleção de Barras"):
        st.session_state.sel_barras = []
        st.session_state.last_processed_sig = "manual_clear_barras"
        st.rerun()

    st.caption(f"**{len(st.session_state.sel_barras)} barra(s) selecionada(s)**")

    mat_escolhido = st.selectbox("Material:", LISTA_MATERIAIS)
    sec_escolhida = st.selectbox("Seção Perfil C / Comercial:", LISTA_SECOES)

    area_exib, inercia_exib = SECOES[sec_escolhida]
    st.caption(f"Propriedades: **Área = {area_exib} cm²** | **Ix = {inercia_exib} cm⁴**")

    c_ap1, c_ap2 = st.columns(2)
    if c_ap1.button("Salvar nas Barras Selecionadas", type="primary", use_container_width=True):
        if not st.session_state.sel_barras:
            st.warning("Nenhuma barra selecionada.")
        else:
            for bid in st.session_state.sel_barras:
                idx = next((i for i, item in enumerate(st.session_state.dados_barras) if item["Barra"] == bid), None)
                if idx is not None:
                    st.session_state.dados_barras[idx]["Material"] = mat_escolhido
                    st.session_state.dados_barras[idx]["Seção"] = sec_escolhida
            st.success(f"Perfil {sec_escolhida} aplicado a {len(st.session_state.sel_barras)} barra(s)!")
            st.rerun()

    if c_ap2.button("Aplicar a TODAS as Barras", use_container_width=True):
        for b in st.session_state.dados_barras:
            b["Material"] = mat_escolhido
            b["Seção"] = sec_escolhida
        st.success(f"Perfil {sec_escolhida} aplicado a todas as barras!")
        st.rerun()

    with st.expander("⚡ Carga Distribuída nas Barras (Converter para Nós)"):
        st.write("Aplica uma carga linear $q$ (kN/m) nas barras selecionadas e divide automaticamente entre os seus nós extremos.")
        tipo_q = st.radio("Direção da Carga Distribuída:", ["Local Perpendicular (q⟂ vento)", "Global Vertical (qy gravidade)"], horizontal=True)
        q_val = st.number_input("Valor de q (kN/m):", value=0.0)

        if st.button("Distribuir Carga nas Barras para os Nós"):
            if not st.session_state.sel_barras or abs(q_val) < 1e-4:
                st.warning("Selecione as barras e defina um valor não nulo de q.")
            else:
                for bid in st.session_state.sel_barras:
                    b_obj = next(b for b in st.session_state.dados_barras if b["Barra"] == bid)
                    n1, n2 = b_obj["Nó Inic."], b_obj["Nó Final"]
                    xa, ya = coords_map[n1]
                    xb, yb = coords_map[n2]
                    comp_barra = np.hypot(xb - xa, yb - ya)
                    f_total = q_val * comp_barra
                    f_no = f_total / 2.0

                    if "Local" in tipo_q:
                        ang_b = np.arctan2(yb - ya, xb - xa)
                        dfx = -f_no * np.sin(ang_b)
                        dfy = f_no * np.cos(ang_b)
                    else:
                        dfx = 0.0
                        dfy = f_no

                    for nid in (n1, n2):
                        idx_n = next(i for i, n in enumerate(st.session_state.dados_nos) if n["Nó"] == nid)
                        st.session_state.dados_nos[idx_n]["Fx (kN)"] += round(dfx, 4)
                        st.session_state.dados_nos[idx_n]["Fy (kN)"] += round(dfy, 4)

                st.success("Carga distribuída transferida com sucesso para os nós!")
                st.rerun()

# -----------------------------------------------------------------------------
# 9. MOTOR MATRICIAL E DIAGRAMAS
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
                if L == 0: continue
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
            fig_d.update_layout(
                height=400, 
                margin=dict(l=20,r=20,t=20,b=20), 
                xaxis=dict(scaleanchor="y", scaleratio=1),
                dragmode="pan",
                uirevision="diagramas"
            )
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
            fig_def.update_layout(
                height=400, 
                margin=dict(l=20,r=20,t=20,b=20), 
                xaxis=dict(scaleanchor="y", scaleratio=1),
                dragmode="pan",
                uirevision="deformada"
            )
            st.plotly_chart(fig_def, use_container_width=True, config={'scrollZoom': True})

        with t2:
            st.plotly_chart(plot_diagrama_plotly(esforcos, 'N'), use_container_width=True, config={'scrollZoom': True})
        with t3:
            st.plotly_chart(plot_diagrama_plotly(esforcos, 'V'), use_container_width=True, config={'scrollZoom': True})
        with t4:
            st.plotly_chart(plot_diagrama_plotly(esforcos, 'M'), use_container_width=True, config={'scrollZoom': True})

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
