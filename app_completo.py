import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import ezdxf
import tempfile
import os

st.set_page_config(page_title="Ftool Engine - Visual", layout="wide")

st.title("🏗️ Motor Ftool: Importação DXF e Cálculo")

st.subheader("1. Importar Geometria (DXF)")
arquivo_dxf = st.file_uploader("Selecione o arquivo .dxf gerado pelo seu CAD", type=['dxf'])

dados_nos_iniciais = []
dados_barras_iniciais = []
nos_lista = []
coords_nos = {}

if arquivo_dxf is not None:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp:
            tmp.write(arquivo_dxf.getvalue())
            tmp_path = tmp.name
            
        doc = ezdxf.readfile(tmp_path)
        os.remove(tmp_path)
        msp = doc.modelspace()
        
        nos_set = set()
        barras_dxf = []
        
        # Lê elementos do tipo LINE
        for linha in msp.query('LINE'):
            start = (round(linha.dxf.start.x, 3), round(linha.dxf.start.y, 3))
            end = (round(linha.dxf.end.x, 3), round(linha.dxf.end.y, 3))
            nos_set.update([start, end])
            barras_dxf.append((start, end))
            
        # Lê elementos do tipo LWPOLYLINE (linhas contínuas)
        for polyline in msp.query('LWPOLYLINE'):
            points = [(round(p[0], 3), round(p[1], 3)) for p in polyline.get_points(format='xy')]
            for i in range(len(points) - 1):
                start, end = points[i], points[i+1]
                nos_set.update([start, end])
                barras_dxf.append((start, end))
            
        nos_lista = sorted(list(nos_set), key=lambda x: (x[0], x[1]))
        no_map = {no: i+1 for i, no in enumerate(nos_lista)}
        
        for no in nos_lista:
            dados_nos_iniciais.append({"Nó": no_map[no], "X": no[0], "Y": no[1], "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0})
            
        for i, barra in enumerate(barras_dxf):
            dados_barras_iniciais.append({"Barra": i+1, "Nó Inic.": no_map[barra[0]], "Nó Final": no_map[barra[1]], "E (GPa)": 200.0, "A (cm²)": 50.0, "I (cm⁴)": 10000.0})
            
        st.success(f"DXF lido com sucesso! Encontrados {len(nos_lista)} nós e {len(barras_dxf)} barras.")
        
        coords_nos = {no_map[no]: no for no in nos_lista}
    except Exception as e:
        st.error(f"Erro ao ler DXF: {e}")

# Pré-visualização em largura total
if dados_nos_iniciais:
    st.subheader("Pré-visualização da Estrutura")
    mostrar_ids = st.checkbox("Mostrar IDs dos Nós", value=False)
    
    fig_preview, ax_preview = plt.subplots(figsize=(16, 4)) 
    
    for row in dados_barras_iniciais:
        n1, n2 = row['Nó Inic.'], row['Nó Final']
        if n1 in coords_nos and n2 in coords_nos:
            x1, y1 = coords_nos[n1]
            x2, y2 = coords_nos[n2]
            ax_preview.plot([x1, x2], [y1, y2], color='blue', linewidth=1.5, zorder=1)
            
    for no_id, (x, y) in coords_nos.items():
        ax_preview.scatter(x, y, color='red', s=20, zorder=2)
        if mostrar_ids:
            ax_preview.annotate(f"{int(no_id)}", (x, y), textcoords="offset points", xytext=(3,3), ha='left', fontsize=8, color='darkred')

    ax_preview.set_aspect('equal')
    ax_preview.grid(True, linestyle=':', alpha=0.6)
    ax_preview.set_xlabel("X (m)")
    ax_preview.set_ylabel("Y (m)")
    st.pyplot(fig_preview)

st.divider()

col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("2. Edição de Nós")
    tabela_nos = st.data_editor(pd.DataFrame(dados_nos_iniciais), num_rows="dynamic", use_container_width=True)
with col2:
    st.subheader("3. Edição de Barras")
    tabela_barras = st.data_editor(pd.DataFrame(dados_barras_iniciais), num_rows="dynamic", use_container_width=True)

# Motor Matemático
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
if st.button("▶️ Calcular Estrutura", use_container_width=True, type="primary") and not tabela_nos.empty:
    num_nos = len(tabela_nos)
    num_gdl = num_nos * 3
    K_global = np.zeros((num_gdl, num_gdl))
    F_global = np.zeros(num_gdl)
    restricoes = np.zeros(num_gdl, dtype=bool)
    
    no_to_idx = {int(row['Nó']): i for i, row in tabela_nos.iterrows()}
    
    for i, row in tabela_nos.iterrows():
        idx = no_to_idx[row['Nó']] * 3
        F_global[idx]   = row['Fx (kN)'] * 1000
        F_global[idx+1] = row['Fy (kN)'] * 1000
        F_global[idx+2] = row['Mz (kNm)'] * 1000
        restricoes[idx]   = row['Apoio X']
        restricoes[idx+1] = row['Apoio Y']
        restricoes[idx+2] = row['Apoio Rot']

    for i, row in tabela_barras.iterrows():
        n1, n2 = int(row['Nó Inic.']), int(row['Nó Final'])
        E = row['E (GPa)'] * 1e9
        A = row['A (cm²)'] * 1e-4
        I = row['I (cm⁴)'] * 1e-8
        
        x1, y1 = tabela_nos[tabela_nos['Nó']==n1][['X', 'Y']].values[0]
        x2, y2 = tabela_nos[tabela_nos['Nó']==n2][['X', 'Y']].values[0]
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

    gdl_livres = np.where(~restricoes)[0]
    U_global = np.zeros(num_gdl)
    try:
        if len(gdl_livres) > 0:
            K_livre = K_global[np.ix_(gdl_livres, gdl_livres)]
            F_livre = F_global[gdl_livres]
            U_livre = np.linalg.solve(K_livre, F_livre)
            U_global[gdl_livres] = U_livre
            
        Reacoes = K_global @ U_global - F_global
        
        st.success("✅ Estrutura calculada com sucesso!")
        
        st.subheader("Deformada")
        fig_def, ax_def = plt.subplots(figsize=(16, 4))
        escala = 30
        
        for i, row in tabela_barras.iterrows():
            n1, n2 = int(row['Nó Inic.']), int(row['Nó Final'])
            x1, y1 = tabela_nos[tabela_nos['Nó']==n1][['X', 'Y']].values[0]
            x2, y2 = tabela_nos[tabela_nos['Nó']==n2][['X', 'Y']].values[0]
            
            idx1 = no_to_idx[n1] * 3
            idx2 = no_to_idx[n2] * 3
            
            x1_def = x1 + U_global[idx1] * escala
            y1_def = y1 + U_global[idx1+1] * escala
            x2_def = x2 + U_global[idx2] * escala
            y2_def = y2 + U_global[idx2+1] * escala
            
            ax_def.plot([x1, x2], [y1, y2], color='gray', linestyle='--', linewidth=1)
            ax_def.plot([x1_def, x2_def], [y1_def, y2_def], marker='o', markersize=3, color='red', linewidth=1.5)
        
        ax_def.set_aspect('equal')
        ax_def.grid(True, linestyle=':', alpha=0.6)
        st.pyplot(fig_def)

        st.subheader("Reações nos Apoios")
        res_reacoes = []
        for i, row in tabela_nos.iterrows():
            no_id = int(row['Nó'])
            idx = no_to_idx[no_id] * 3
            if row['Apoio X'] or row['Apoio Y'] or row['Apoio Rot']:
                res_reacoes.append({
                    "Nó": no_id,
                    "Rx (kN)": round(Reacoes[idx] / 1000, 2),
                    "Ry (kN)": round(Reacoes[idx+1] / 1000, 2),
                    "R_Momento (kNm)": round(Reacoes[idx+2] / 1000, 2)
                })
        if res_reacoes:
            st.dataframe(pd.DataFrame(res_reacoes), use_container_width=True)

    except np.linalg.LinAlgError:
        st.error("Erro na matriz: A estrutura é instável (hipostática). Verifique os apoios!")
