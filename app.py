import streamlit as st
import pandas as pd

def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.set_page_config(page_title="Conferência de Totais", layout="wide")
st.title("📊 Conferência de Totais: Convênio vs. Caixas")

# 1. Upload do Arquivo
uploaded_file = st.file_uploader("Carregue sua planilha (Excel)", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        st.success("Arquivo carregado com sucesso!")
        
        st.divider()
        
        # 2. Mapeamento de Colunas (Para o código saber onde buscar os dados)
        st.subheader("1. Mapeamento de Colunas")
        cols = df.columns.tolist()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            col_valor = st.selectbox("Qual coluna tem o VALOR (Preço)?", cols, index=0)
        with col2:
            col_tipo = st.selectbox("Qual coluna diz o TIPO (Convênio/Particular)?", cols, index=1 if len(cols) > 1 else 0)
        with col3:
            col_caixa = st.selectbox("Qual coluna identifica o CAIXA / USUÁRIO?", cols, index=2 if len(cols) > 2 else 0)

        st.divider()

        # 3. Definição do Filtro de Convênio
        st.subheader("2. Definição de Convênio")
        
        # Pegamos todos os valores únicos da coluna de Tipo para você escolher o que é "Convênio"
        tipos_disponiveis = df[col_tipo].unique().tolist()
        
        # O usuário seleciona o que deve ser somado como "Total do Sistema"
        tipos_selecionados = st.multiselect(
            "Selecione quais tipos somar (ex: CONVENIO, UNIMED, BRADESCO):", 
            options=tipos_disponiveis,
            default=tipos_disponiveis[0] if len(tipos_disponiveis) > 0 else None
        )

        if tipos_selecionados:
            # --- CÁLCULOS ---
            
            # A) Total do Sistema (Apenas os tipos selecionados)
            df_convenio = df[df[col_tipo].isin(tipos_selecionados)]
            total_sistema = df_convenio[col_valor].sum()

            # B) Total por Caixa (Agrupado por caixa, somando tudo que tem lá)
            # Nota: Aqui somamos tudo do caixa. Se o caixa tiver particular misturado, vai aparecer aqui.
            df_caixas = df.groupby(col_caixa)[col_valor].sum().reset_index()
            df_caixas.columns = ['Caixa / Usuário', 'Valor Total']
            
            # Total geral somando todos os caixas
            total_caixas_geral = df_caixas['Valor Total'].sum()
            
            diferenca = total_caixas_geral - total_sistema

            # --- EXIBIÇÃO DOS RESULTADOS ---
            st.divider()
            st.subheader("3. Resultados Consolidados")

            # Métricas lado a lado
            m1, m2, m3 = st.columns(3)
            
            with m1:
                st.metric(label="Total Esperado (Convênios Selecionados)", value=format_currency(total_sistema))
            
            with m2:
                st.metric(
                    label="Total Somado dos Caixas", 
                    value=format_currency(total_caixas_geral),
                    delta=format_currency(diferenca) # Mostra a diferença em verde/vermelho
                )
            
            with m3:
                if diferenca == 0:
                    st.success("✅ Valores Batem Perfeitamente!")
                elif diferenca > 0:
                    st.info("ℹ️ Caixas têm MAIS valor que os convênios (Provável Particular incluso).")
                else:
                    st.error("⚠️ Atenção: Caixas têm MENOS valor que o esperado.")

            st.divider()
            
            # Detalhamento por Caixa
            st.subheader("Detalhamento por Caixa")
            
            # Formatação visual da tabela
            df_caixas['Valor Formatado'] = df_caixas['Valor Total'].apply(format_currency)
            st.dataframe(df_caixas[['Caixa / Usuário', 'Valor Formatado']], use_container_width=True)

        else:
            st.warning("Por favor, selecione pelo menos um tipo de atendimento acima para calcular.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o arquivo: {e}")
