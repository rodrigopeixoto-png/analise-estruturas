import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Motor Ftool em Python - Assemblagem", layout="wide")

st.title("🏗️ Motor Ftool: Montagem da Super Matriz Global")
st.write("Este módulo calcula a Rigidez Local de cada barra e monta a Matriz de Rigidez Global da estrutura inteira conectando os graus de liberdade.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Propriedades e Geometria")
    E = st.number_input("Módulo de Elasticidade (E) em Pa", value=2.05e11, format="%.2e")
    A = st.number_input("Área da Seção (A) em m²", value=0.01)
    I = st.number_input("Inércia (I) em m⁴", value=1e-5, format="%.2e")

    # Para montar a matriz global, precisamos de identificar os NÓS.
    # Em vez de apenas coordenadas X e Y, vamos dar IDs aos nós.
    dados_barras = pd.DataFrame([
        {"Nó Inicial": 1, "Nó Final": 2, "Comprimento (L)": 4.0, "Ângulo (graus)": 90},
        {"Nó Inicial": 2, "Nó Final": 3, "Comprimento (L)": 5.0, "Ângulo (graus)": 0},
        {"Nó Inicial": 3, "Nó Final": 4, "Comprimento (L)": 4.0, "Ângulo (graus)": 270},
    ])
    st.write("Tabela de Conectividade (Topologia):")
    tabela_barras = st.data_editor(dados_barras, num_rows="dynamic", use_container_width=True)

# ---------------------------------------------------------
# Motor Matemático
# ---------------------------------------------------------
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

def matriz_transformacao(angulo_graus):
    rad = np.radians(angulo_graus)
    c, s = np.cos(rad), np.sin(rad)
    T = np.zeros((6, 6))
    T[0,0] = c; T[0,1] = s; T[1,0] = -s; T[1,1] = c; T[2,2] = 1
    T[3,3] = c; T[3,4] = s; T[4,3] = -s; T[4,4] = c; T[5,5] = 1
    return T

# 1. Determinar o número total de nós
# (Pegamos o maior ID de nó mencionado na tabela)
max_no = int(max(tabela_barras['Nó Inicial'].max(), tabela_barras['Nó Final'].max()))

# Cada nó tem 3 Graus de Liberdade (GDL): dx, dy, rotação
num_gdl_total = max_no * 3

# Inicializar a Super Matriz Global com zeros
K_global_estrutura = np.zeros((num_gdl_total, num_gdl_total))

with col2:
    st.subheader(f"2. Matriz Global da Estrutura ({num_gdl_total} x {num_gdl_total})")
    
    for index, row in tabela_barras.iterrows():
        n1 = int(row['Nó Inicial'])
        n2 = int(row['Nó Final'])
        L = row['Comprimento (L)']
        angulo = row['Ângulo (graus)']
        
        if L > 0:
            # Matrizes da barra
            K_loc = matriz_rigidez_local(E, A, I, L)
            T = matriz_transformacao(angulo)
            K_glob_barra = np.transpose(T) @ K_loc @ T
            
            # --- O ALGORITMO DE ASSEMBLAGEM ---
            # Identificar os índices dos Graus de Liberdade na Super Matriz
            # Como Python começa a contar do 0, o Nó 1 ocupa os índices 0, 1 e 2.
            idx_n1 = (n1 - 1) * 3
            idx_n2 = (n2 - 1) * 3
            
            # Mapeamento: os 3 primeiros valores de K_glob_barra vão para as posições do Nó 1,
            # os 3 últimos vão para o Nó 2.
            indices = [idx_n1, idx_n1+1, idx_n1+2, idx_n2, idx_n2+1, idx_n2+2]
            
            # Sobreposição (soma) na Super Matriz
            for i in range(6):
                for j in range(6):
                    K_global_estrutura[indices[i], indices[j]] += K_glob_barra[i, j]

    # Exibindo a matriz gigantesca no ecrã
    df_k_global = pd.DataFrame(K_global_estrutura)
    
    # Criando rótulos bonitos para as colunas/linhas
    rotulos = []
    for n in range(1, max_no + 1):
        rotulos.extend([f"Nó{n}_dx", f"Nó{n}_dy", f"Nó{n}_rot"])
    
    df_k_global.columns = rotulos
    df_k_global.index = rotulos

    st.dataframe(df_k_global.style.format("{:.2e}"))
    
    st.info(f"O sistema montou uma Matriz de {num_gdl_total}x{num_gdl_total} pois detetou {max_no} nós, cada um com 3 graus de liberdade.")
