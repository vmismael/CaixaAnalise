import streamlit as st
import pandas as pd
import io

def limpar_e_ler_extrato(uploaded_file):
    """
    Função para processar um único arquivo CSV de extrato.
    Lê a credencial na B9, limpa linhas de subtotal e formata valores.
    """
    try:
        # Lê o conteúdo do arquivo como texto para extrair metadados
        # Usamos latin1 pois sistemas brasileiros antigos costumam usar essa codificação
        stringio = io.StringIO(uploaded_file.getvalue().decode("latin1"))
        linhas = stringio.readlines()

        # 1. Extrair a Área (Credenciado)
        # O usuário informou que fica na B9. No Python (index 0), isso é linha 8, coluna 1.
        area_nome = "Desconhecido"
        if len(linhas) > 8:
            partes = linhas[8].split(';')
            if len(partes) > 1:
                area_nome = partes[1].strip()

        # 2. Encontrar onde começam os dados
        # Procuramos a linha que começa com "Data;Nome"
        linha_cabecalho = 10 # Padrão observado
        for i, linha in enumerate(linhas):
            if linha.startswith("Data;Nome"):
                linha_cabecalho = i
                break
        
        # Volta o ponteiro do arquivo para o início para o pandas ler
        uploaded_file.seek(0)
        
        # 3. Ler o CSV com o Pandas
        df = pd.read_csv(
            uploaded_file, 
            sep=';', 
            skiprows=linha_cabecalho, 
            encoding='latin1',
            # Força ler como string primeiro para evitar erros de conversão
            dtype={'Valor': str, 'CH': str} 
        )

        # 4. Limpeza de Dados
        if 'Data' in df.columns:
            # Remove linhas vazias ou linhas de 'Sub-total'
            df = df.dropna(subset=['Data'])
            df = df[df['Data'] != 'Sub-total']

            # Cria a coluna da Área
            df['Area'] = area_nome

            # Tratamento de Valores (R$ 1.250,00 -> 1250.00)
            if 'Valor' in df.columns:
                df['Valor'] = df['Valor'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')

            # Tratamento de Data
            df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')

            return df
        else:
            # Caso o arquivo não tenha a coluna Data (arquivo vazio ou formato errado)
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro ao processar arquivo {uploaded_file.name}: {e}")
        return pd.DataFrame()

# --- Interface do Streamlit ---
st.title("Conferência de Caixa 💰")
st.subheader("Etapa 1: Importação dos Extratos")

arquivos_extratos = st.file_uploader(
    "Faça upload dos arquivos CSV das áreas (quinzena)", 
    accept_multiple_files=True, 
    type=['csv']
)

if arquivos_extratos:
    lista_dfs = []
    
    for arquivo in arquivos_extratos:
        df_temp = limpar_e_ler_extrato(arquivo)
        
        if not df_temp.empty:
            lista_dfs.append(df_temp)
    
    if lista_dfs:
        # Junta todos os arquivos em um só
        df_extratos_consolidado = pd.concat(lista_dfs, ignore_index=True)
        
        st.success(f"{len(lista_dfs)} arquivos processados com sucesso!")
        
        # Mostra uma prévia dos dados
        st.dataframe(df_extratos_consolidado.head())
        
        # Mostra totais por área para conferência rápida
        st.write("Resumo por Área:")
        resumo = df_extratos_consolidado.groupby('Area')['Valor'].sum().reset_index()
        st.dataframe(resumo)
        
    else:
        st.warning("Nenhum dado válido encontrado nos arquivos enviados.")
