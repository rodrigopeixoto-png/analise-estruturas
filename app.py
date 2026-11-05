import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Motor Ftool em Python", layout="wide")

st.title("🏗️ Análise de Pórticos Planos (Método dos Deslocamentos)")
st.write("Insira as coordenadas das barras e as propriedades físicas. O sistema montará as matrizes de rigidez local e global.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Propriedades Físicas")
    E = st.number_input("Módulo de Elasticidade (E) em Pa", value=2.05e11, format="%.2e")
    A = st.number_input("Área da Seção (A) em m²", value=0.01)
    I = st.number_input("Inércia (I) em m⁴", value=1e-5, format="%.2e")

    st.subheader("2. Geometria (Nós e Barras)")
    dados_iniciais = pd.DataFrame([
        {"X_Inicial": 0.0, "Y_Inicial": 0.0, "X_Final": 0.0, "Y_Final": 4.0},
        {"X_Inicial": 0.0, "Y_Inicial": 4.0, "X_Final": 5.0, "Y_Final": 4.0},
        {"X_Inicial": 5.0, "Y_Inicial": 4.0, "X_Final": 5.0, "Y_Final": 0.0},
    ])
    tabela_barras = st.data_editor(dados_iniciais, num_rows="dynamic", use_container_width=True)

def matriz_rigidez_local(E, A, I, L):
    k = np.zeros((6, 6))
    EA_L = (E * A) / L; EI_L = (E * I) / L
    EI_L2 = (E * I) / (L**2); EI_L3 = (E * I) / (L**3)
    
    k[0, 0] =  EA_L; k[0, 3] = -EA_L
    k[3, 0] = -EA_L; k[3, 3] =  EA_L
    
    k[1, 1] =  12 * EI_L3; k[1, 4] = -12 * EI_L3
    k[4, 1] = -12 * EI_L3; k[4, 4] =  12 * EI_L3
    
    k[1, 2] = k[2, 1] =  6 * EI_L2; k[1, 5] = k[5, 1] =  6 * EI_L2
    k[2, 4] = k[4, 2] = -6 * EI_L2; k[4, 5] = k[5, 4] = -6 * EI_L2
    
    k[2, 2] =  4 * EI_L; k[5, 5] =  4 * EI_L
    k[2, 5] =  2 * EI_L; k[5, 2] =  2 * EI_L
    return k

def matriz_transformacao(c, s):
    T = np.zeros((6, 6))
    T[0, 0] =  c; T[0, 1] = s
    T[1, 0] = -s; T[1, 1] = c
    T[2, 2] =  1
    T[3, 3] =  c; T[3, 4] = s
    T[4, 3] = -s; T[4, 4] = c
    T[5, 5] =  1
    return T

with col2:
    st.subheader("3. Visualização da Estrutura")
    fig, ax = plt.subplots(figsize=(6, 4))
    matrizes_globais = []
    
    for index, row in tabela_barras.iterrows():
        x1, y1 = row['X_Inicial'], row['Y_Inicial']
        x2, y2 = row['X_Final'], row['Y_Final']
        ax.plot([x1, x2], [y1, y2], marker='o', color='blue', linewidth=2, markersize=5)
        
        dx = x2 - x1
        dy = y2 - y1
        L = np.sqrt(dx**2 + dy**2)
        
        if L > 0:
            c = dx / L
            s = dy / L
            K_loc = matriz_rigidez_local(E, A, I, L)
            T = matriz_transformacao(c, s)
            K_glob = np.transpose(T) @ K_loc @ T
            matrizes_globais.append((f"Barra {index+1}", K_glob))

    ax.set_aspect('equal')
    ax.grid(True)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    st.pyplot(fig)

    st.subheader("4. Matrizes de Rigidez Global (K)")
    if matrizes_globais:
        barra_selecionada = st.selectbox("Selecione a barra:", [m[0] for m in matrizes_globais])
        for nome, matriz in matrizes_globais:
            if nome == barra_selecionada:
                st.dataframe(pd.DataFrame(matriz).style.format("{:.2e}"))
