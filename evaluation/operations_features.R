library(readr)
library(dplyr)
library(ggplot2)

# 1) Leer CSV y renombrar columnas inmediatamente
df_times <- read_csv("z3_benchmark_results_tactics1.csv") %>%
  rename(
    Model_Name = `Model Name`,
    Result = `Result`
  )

# 2) Eliminar filas cuyo Result contenga "ERROR" (case-insensitive)
df_times <- df_times %>%
  filter(!grepl("ERROR", as.character(Result), ignore.case = TRUE))

# 3) Detectar modelos no-satisfiables: Operation == "Z3Satisfiable" y Result textual == FALSE
#    Soportamos variantes "false","False","FALSE","0","FALSE\n", etc.
unsat_models <- df_times %>%
  filter(
    Operation == "Z3Satisfiable",
    tolower(trimws(as.character(Result))) %in% c("false", "f", "0", "no", "n")
  ) %>%
  pull(Model_Name) %>%
  unique()

# 4) Eliminar todas las filas de esos modelos
df_times <- df_times %>%
  filter(!(Model_Name %in% unsat_models))

# 5) Eliminar operaciones que no queremos mostrar
df_times <- df_times %>%
  filter(
    Operation != "Z3Satisfiable",
    Operation != "Z3ConfigurationsNumber",
    Operation != "Z3AttributeOptimization"
  )

# 6) (Opcional) mantener solo las operaciones que te interesan
ordered_ops <- c("Z3CoreFeatures", "Z3DeadFeatures", "Z3FalseOptionalFeatures")
df_times <- df_times %>% filter(Operation %in% ordered_ops)

# 7) Convertir Result a numérico en una columna nueva Result_num
#    (as.numeric devuelve NA si no se puede convertir; no override original Result)
df_times <- df_times %>%
  mutate(Result_num = as.numeric(as.character(Result)))

# 8) Quitar filas que no tienen valor numérico en Result_num
df_times <- df_times %>% filter(!is.na(Result_num))

# 9) Fijar orden de factores para la visualización
df_times$Operation <- factor(df_times$Operation, levels = ordered_ops)

# 10) Dibujar boxplot usando Result_num
ggplot(df_times, aes(x = Operation, y = Result_num, fill = Operation)) +
  geom_boxplot(outlier.size = 2, alpha = 0.8, color = "black") +
  theme_minimal(base_size = 14) +
  theme(
    legend.position = "none",
    axis.text.x = element_text(color = "black", size = 12, face = "bold"),
    axis.text.y = element_text(color = "black", size = 12)
  ) +
  labs(x = NULL, y = "Features (Result)") 