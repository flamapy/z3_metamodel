files <- c(
  "z3_benchmark_results_tactics1.csv",
  "z3_benchmark_results_tactics2.csv",
  "z3_benchmark_results_tactics3.csv",
  "z3_benchmark_results_tactics4.csv",
  "z3_benchmark_results_tactics5.csv",
  "z3_benchmark_results_tactics6.csv",
  "z3_benchmark_results_tactics7.csv"
)

df_times <- lapply(files, function(f) {
  read_csv(f) %>%
    mutate(Serie = tools::file_path_sans_ext(basename(f)))
}) %>%
  bind_rows()

df_times <- df_times %>%
  rename(
    Model_Name = `Model Name`,
    Result = `Result`
  ) %>%
  filter(!grepl("ERROR", as.character(Result), ignore.case = TRUE))

unsat_models <- df_times %>%
  filter(
    Operation == "Z3Satisfiable",
    tolower(trimws(as.character(Result))) %in% c("false", "f", "0", "no", "n")
  ) %>%
  pull(Model_Name) %>%
  unique()

df_times <- df_times %>%
  filter(!(Model_Name %in% unsat_models))

df_times <- df_times %>%
  filter(
    Operation != "Z3Satisfiable",
    Operation != "Z3ConfigurationsNumber",
    Operation != "Z3AttributeOptimization"
  )

ordered_ops <- c("Z3CoreFeatures", "Z3DeadFeatures", "Z3FalseOptionalFeatures")

df_times <- df_times %>%
  filter(Operation %in% ordered_ops)

df_times <- df_times %>%
  mutate(Result_num = as.numeric(as.character(Result))) %>%
  filter(!is.na(Result_num))

df_times$Operation <- factor(df_times$Operation, levels = ordered_ops)

ggplot(df_times, aes(x = Operation, y = Result_num, fill = Serie)) +
  geom_boxplot(
    position = position_dodge(width = 0.8),
    outlier.size = 2,
    alpha = 0.8,
    color = "black"
  ) +
  theme_minimal(base_size = 14) +
  theme(
    legend.position = "top",
    axis.text.x = element_text(color = "black", size = 12, face = "bold"),
    axis.text.y = element_text(color = "black", size = 12)
  ) +
  labs(
    x = NULL,
    y = "Features (Result)",
    fill = "Serie"
  )