import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import ezdxf
import tempfile
import os

st.set_page_config(page_title="Ftool Engine - Interativo", layout="wide")
st.title("🏗️ Motor Ftool: Geometria Interativa e Perfis")

# --- BIBLIOTECAS DE MATERIAIS E SEÇÕES ---
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
