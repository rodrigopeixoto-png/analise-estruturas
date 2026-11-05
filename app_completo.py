import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import ezdxf
import tempfile
import os

st.set_page_config(page_title="Ftool Engine - DXF", layout="wide")

st.title("🏗️ Motor Ftool: Importação DXF e Cálculo")

# --- Módulo de Importação DXF ---
st.subheader("1. Importar Geometria (DXF)")
arquivo_dxf = st.file_uploader("Selecione o arquivo .dxf gerado pelo seu CAD", type=['dxf'])

dados_nos = []
dados_barras = []

if arquivo_dxf is not None:
    try:
        # Salva o arquivo temporariamente para a biblioteca ezdxf conseguir ler
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp:
            tmp.write(arquivo_dxf.getvalue())
            tmp_path = tmp.name
            
        doc = ezdxf.readfile(tmp_path)
        os.remove(tmp_path) # Limpa o arquivo temporário
        msp = doc.modelspace()
        
        # Extrai todas as linhas do DXF
        linhas = msp.query('LINE')
        nos_set = set()
        barras_dxf = []
        
        for linha in linhas:
            # Arredondando coordenadas para evitar que o PC crie 2 nós por erro de dízimas
            start = (round(linha.dxf.start.x, 3), round(linha.dxf.start.y, 3))
            end = (round(linha.dxf.end.x, 3), round(linha.dxf.end.y, 3))
            nos_set.add(start)
            nos_set.add(end)
            barras_dxf.append((start, end))
            
        # Organiza os nós e cria um ID para cada um (1, 2, 3...)
        nos_lista = sorted(list(nos_set), key=lambda x: (x[0], x[1]))
        no_map = {no: i+1 for i, no in enumerate(nos_lista)}
        
        # Popula a tabela de nós automaticamente
        for no in nos_lista:
            dados_nos.append({"Nó": no_map[no], "X": no[0], "Y": no[1], "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0})
            
        # Popula a tabela de barras automaticamente conectando os IDs
        for i, barra in enumerate(barras_dxf):
            dados_barras.append({"Barra": i+1, "Nó Inic.": no_map[barra[0]], "Nó Final": no_map[barra[1]], "E (GPa)": 200.0, "A (cm²)": 50.0, "I (cm⁴)": 10000.0})
            
        st.success(f"DXF lido com sucesso! Encontrados {len(nos_lista)} nós e {len(barras_dxf)} barras. Edite os apoios abaixo.")
    except Exception as e:
        st.error(f"Erro ao ler DXF: {e}")

# Se nenhum DXF for enviado, exibe o pórtico padrão para a tela não ficar vazia
if not dados_nos:
    dados_nos = [
        {"Nó": 1, "X": 0.0, "Y": 0.0, "Apoio X": True, "Apoio Y": True, "Apoio Rot": True, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
        {"Nó": 2, "X": 0.0, "Y": 4.0, "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 20.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
        {"Nó": 3, "X": 5.0, "Y": 4.0, "Apoio X": False, "Apoio Y": False, "Apoio Rot": False, "Fx (kN)": 0.0, "Fy (kN)": -15.0, "Mz (kNm)": 0.0},
        {"Nó": 4, "X": 5.0, "Y": 0.0, "Apoio X": True, "Apoio Y": True, "Apoio Rot": True, "Fx (kN)": 0.0, "Fy (kN)": 0.0, "Mz (kNm)": 0.0},
    ]
    dados_barras = [
        {"Barra": 1, "Nó Inic.": 1, "Nó Final": 2, "E (GPa)": 200.0, "A (cm²)": 50.0, "I (cm⁴)": 10000.0},
        {"Barra": 2, "Nó Inic.": 2, "Nó Final": 3, "E (GPa)": 200.0, "A (cm²)": 50.0, "I (cm⁴)": 20000.0},
        {"Barra": 3, "Nó Inic.": 3, "Nó Final": 4, "E (GPa)": 200.0, "A (cm²)": 50.0, "I (cm⁴)": 10000.0},
    ]

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("2. Nós (Defina Apoios e Cargas)")
    tabela_nos = st.data_editor(pd.DataFrame(dados_nos), num_rows="dynamic", use_container_width=True)
    
    st.subheader("3. Barras (Propriedades dos Perfis)")
    tabela_barras = st.data_editor(pd.DataFrame(dados_barras), num_rows="dynamic", use_container_width=True)

# --- Motor Matemático ---
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

if st.button("▶️ Calcular Estrutura", use_container_width=True, type="primary"):
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
        
        with col2:
            st.success("✅ Estrutura calculada com sucesso!")
            st.subheader("4. Vista Deformada")
            fig, ax = plt.subplots(figsize=(6, 4))
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
                
                ax.plot([x1, x2], [y1, y2], color='gray', linestyle='--', linewidth=1, label="Original" if i==0 else "")
                ax.plot([x1_def, x2_def], [y1_def, y2_def], marker='o', color='red', linewidth=2, label="Deformada" if i==0 else "")
            
            ax.set_aspect('equal')
            ax.grid(True, linestyle=':')
            # Evita repetir legendas no loop
            handles, labels = ax.get_legend_handles_labels()
            by_label = dict(zip(labels, handles))
            ax.legend(by_label.values(), by_label.keys())
            st.pyplot(fig)

            st.subheader("5. Reações nos Apoios")
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
