import pandas as pd
import os

def get_boxplot_statistics(filepath, group_col='Operation', value_col='Result'):
    # Verificar si el archivo existe
    if not os.path.exists(filepath):
        print(f"Error: El archivo en la ruta '{filepath}' no existe.")
        return None

    # Leer el CSV
    df = pd.read_csv(filepath)
    
    # 1. Filtrar filas que contengan 'ERROR' en la columna Result
    mask_error = df['Result'].astype(str).str.upper().str.contains('ERROR', na=False)
    df = df[~mask_error]

    # 2. Asegurar que la columna de valores sea numérica y limpiar NaNs
    df[value_col] = pd.to_numeric(df[value_col], errors='coerce')
    df = df.dropna(subset=[value_col])

    results = []
    
    # Agrupamos por la columna de operación
    grouped = df.groupby(group_col)[value_col]
    
    for name, group in grouped:
        # Filtro: Ignorar operaciones que contengan 'Satisfiable' (como en tu script)
        #if 'Satisfiable' not in name:
        data = group.sort_values()
        
        if data.empty:
            continue
        
        # --- CÁLCULOS ESTADÍSTICOS ---
        total_sum = data.sum()  # <--- NUEVA SUMA TOTAL
        sample_size = len(data)
        
        q1 = data.quantile(0.25)
        median = data.quantile(0.50)
        q3 = data.quantile(0.75)
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        lower_whisker = data[data >= lower_bound].min()
        upper_whisker = data[data <= upper_bound].max()
        
        outliers = data[(data < lower_bound) | (data > upper_bound)].tolist()
        
        # Añadimos todos los campos al resultado
        results.append({
            'Operation': name,
            'Sample Size': sample_size,
            'Total Sum': total_sum,  # <--- AGREGADO A LA TABLA
            'Lower Whisker': lower_whisker,
            'Lower Quartile': q1,
            'Median': median,
            'Upper Quartile': q3,
            'Upper Whisker': upper_whisker,
            'Outliers': outliers
        })
    
    return pd.DataFrame(results)

# --- CONFIGURACIÓN ---
mi_archivo = 'sat_benchmark_results.csv'

# Ejecución
stats_df = get_boxplot_statistics(mi_archivo)

if stats_df is not None:
    print("Estadísticas para Boxplot y Suma Total por Operación:")
    print("-" * 100)
    # Mostramos la tabla (ajusta el ancho de consola si es necesario)
    print(stats_df.to_string(index=False))