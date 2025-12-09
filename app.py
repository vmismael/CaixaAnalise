import streamlit as st
import pandas as pd
from io import StringIO

def clean_currency(x):
    """Converte strings de moeda (ex: '1.234,56') para float."""
    if isinstance(x, str):
        return float(x.replace('.', '').replace(',', '.'))
    return float(x)

st.set_page_config(page_title="Conferência de Caixa", layout="wide")
st.title("Conferência de Caixa - Consolidação de Extratos")

uploaded_files = st.file_uploader(
    "Faça o upload dos arquivos CSV (Extratos)", 
    accept_multiple_files=True, 
    type="csv"
)

if uploaded_files:
    all_data = []
    
    for uploaded_file in uploaded_files:
        try:
            # Ler o conteúdo do arquivo com encoding 'latin1' (comum nesses relatórios)
            stringio = StringIO(uploaded_file.getvalue().decode("latin1"))
            lines = stringio.readlines()
            
            # Pula arquivos que não têm cabeçalho suficiente (linhas insuficientes)
            if len(lines) < 11:
                continue

            # 1. Extrair Credencial (Célula B9 -> Linha índice 8, Coluna índice 1)
            try:
                line_b9 = lines[8].strip().split(';')
                # Verifica se existe a coluna B
                if len(line_b9) > 1:
                    credencial = line_b9[1]
                else:
                    credencial = "Desconhecido"
            except Exception:
                credencial = "Erro Leitura"

            # 2. Ler os dados (Cabeçalho está na linha 11 -> índice 10)
            # Juntamos as linhas a partir do cabeçalho para o pandas ler
            data_content = "".join(lines[10:])
            df = pd.read_csv(StringIO(data_content), sep=';')
            
            # Se o dataframe estiver vazio, pula
            if df.empty:
                continue

            # 3. Limpeza de Dados
            # Remover linhas de 'Sub-total'
            if 'Data' in df.columns:
                df = df[df['Data'] != 'Sub-total']
            
            # Remover linhas onde 'Cod O.S.' é nulo (linhas vazias)
            if 'Cod O.S.' in df.columns:
                df = df.dropna(subset=['Cod O.S.'])

            # Adicionar a coluna da Credencial/Área
            df['Credencial'] = credencial
            
            # Converter Valor para número
            if 'Valor' in df.columns:
                df['Valor'] = df['Valor'].apply(clean_currency)
            
            all_data.append(df)
            
        except Exception as e:
            st.error(f"Erro ao processar arquivo {uploaded_file.name}: {e}")

    if all_data:
        # Juntar todos os dataframes
        df_final = pd.concat(all_data, ignore_index=True)

        # 4. Agrupar por Credencial e OS (Somar Valor)
        # Mantemos o 'Nome' pegando o primeiro encontrado para aquela OS, para referência
        df_grouped = df_final.groupby(['Credencial', 'Cod O.S.', 'Nome'])['Valor'].sum().reset_index()

        st.success(f"{len(uploaded_files)} arquivos processados com sucesso!")
        
        # Exibir Totais por Área
        st.subheader("Resumo por Área (Credencial)")
        resumo_area = df_grouped.groupby('Credencial')['Valor'].sum().reset_index()
        st.dataframe(resumo_area.style.format({"Valor": "R$ {:,.2f}"}))

        # Exibir Tabela Detalhada
        st.subheader("Detalhamento por OS")
        st.dataframe(df_grouped.style.format({"Valor": "R$ {:,.2f}"}))
        
        # Botão para baixar o CSV consolidado
        csv = df_grouped.to_csv(index=False, sep=';', decimal=',').encode('latin1')
        st.download_button(
            label="Baixar Planilha Consolidada",
            data=csv,
            file_name="extratos_consolidados.csv",
            mime="text/csv",
        )
        
        # Guardar no session state para a próxima etapa (comparação)
        st.session_state['df_extratos'] = df_grouped
        
    else:
        st.warning("Nenhum dado válido foi encontrado nos arquivos enviados.")
