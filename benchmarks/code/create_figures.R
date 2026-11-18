# Only run once
# install.packages(c("tidyverse"))

library(tidyverse)

# Optional:
#   Rscript code/create_figures.R results/PREFIX.tsv results/PREFIX.pdf
#   Rscript code/create_figures.R --speed results/PREFIX.tsv results/PREFIX.pdf
# With those arguments, only the requested chart is written.
args <- commandArgs(trailingOnly = TRUE)
accuracy_results_path <- "results/accuracy-results-20261102.tsv"
accuracy_pdf_path <- "results/accuracy-barplot.pdf"
speed_results_path <- "results/speed-results-20261102.tsv"
speed_pdf_path <- "results/speed-barplot.pdf"
plot_accuracy <- TRUE
plot_speed <- TRUE
if (length(args) >= 1 && args[[1]] == "--speed") {
  plot_accuracy <- FALSE
  speed_results_path <- args[[2]]
  speed_pdf_path <- args[[3]]
} else if (length(args) >= 1) {
  plot_speed <- FALSE
  accuracy_results_path <- args[[1]]
  if (length(args) >= 2) {
    accuracy_pdf_path <- args[[2]]
  }
}

# Colorblind-friendly Okabe–Ito (subset)
okabe_ito <- c(
  "#0072B2",  # blue
  "#E69F00",  # orange
  "#009E73",  # bluish green
  "#CC79A7",  # reddish purple
  "#56B4E9",  # sky blue
  "#D55E00"   # vermillion
)

if (plot_accuracy) {
accuracy_results <- read_tsv(accuracy_results_path, show_col_types = FALSE)

# Keep a stable, readable method order for accuracy plots
method_levels <- c("A", "B2", "E1", "E2", "E12", "T")
method_labels <- c(
  A = "A: Original Maptology",
  B2 = "B2: + exact-match priority",
  E1 = "E1: + separate names/synonyms",
  E2 = "E2: + 3-character search",
  E12 = "E12: combined (proposed)",
  T = "T: text2term"
)

# ---------------------------------------------------------------------------
# Accuracy: Top-1 and Top-5 as grouped horizontal bars, one panel per dataset
# ---------------------------------------------------------------------------
accuracy_long <- accuracy_results %>%
  mutate(
    method_id = factor(method_id, levels = method_levels),
    method_label = factor(method_labels[as.character(method_id)],
                          levels = method_labels[method_levels]),
    dataset = factor(dataset, levels = c("UKBB-EFO", "Biomappings", "OLS-EFO"))
  ) %>%
  pivot_longer(
    cols = c(top1_percent, top5_percent),
    names_to = "metric",
    values_to = "percent"
  ) %>%
  mutate(
    metric = recode(metric,
                    top1_percent = "Top-1 accuracy",
                    top5_percent = "Top-5 accuracy"),
    metric = factor(metric, levels = c("Top-1 accuracy", "Top-5 accuracy"))
  )

accuracy_plot <- ggplot(accuracy_long, aes(x = percent, y = method_label, fill = metric)) +
  geom_col(position = position_dodge(width = 0.75), width = 0.7) +
  geom_text(
    aes(label = sprintf("%.1f", percent)),
    position = position_dodge(width = 0.75),
    hjust = -0.15,
    size = 3,
    color = "grey20"
  ) +
  facet_wrap(~ dataset, ncol = 1) +
  scale_x_continuous(
    limits = c(0, 110),
    breaks = seq(0, 100, 20),
    expand = expansion(mult = c(0, 0.02))
  ) +
  scale_y_discrete(limits = rev) +
  scale_fill_manual(values = okabe_ito[1:2], name = NULL) +
  labs(
    title = "Mapping accuracy by method and dataset",
    x = "Correct suggestions (%)",
    y = NULL
  ) +
  theme_minimal(base_size = 12) +
  theme(
    legend.position = "top",
    panel.grid.major.y = element_blank(),
    panel.grid.minor = element_blank(),
    strip.text = element_text(face = "bold"),
    plot.title = element_text(face = "bold", hjust = 0.5)
  )

ggsave(accuracy_pdf_path, accuracy_plot, width = 8, height = 9)
message("Wrote ", accuracy_pdf_path)
}

workload_levels <- function(labels) {
  labels <- unique(as.character(labels))
  sample_labels <- grep("^N=[0-9]+ sample$", labels, value = TRUE)
  sample_sizes <- as.integer(sub("^N=([0-9]+) sample$", "\\1", sample_labels))
  sample_labels <- sample_labels[order(sample_sizes)]
  other_labels <- setdiff(labels, c(sample_labels, "All evaluation rows"))
  c(sample_labels, other_labels, intersect("All evaluation rows", labels))
}

if (plot_speed) {

# ---------------------------------------------------------------------------
# Speed: E12 versus text2term, horizontal bars
# ---------------------------------------------------------------------------
speed_results <- read_tsv(speed_results_path, show_col_types = FALSE)
if ("mean_request_seconds" %in% names(speed_results)) {
  round_count <- unique(speed_results$complete_repeats)
  speed_title <- if (length(round_count) == 1 && !is.na(round_count)) {
    if (round_count == 1) {
      "Search speed (1 round)"
    } else {
      sprintf("Search speed (mean of %d rounds)", round_count)
    }
  } else {
    "Search speed"
  }

  speed_plot_data <- speed_results %>%
    mutate(
      method_short = case_when(
        method_id == "E12" ~ "E12 (Maptology)",
        method_id == "T" ~ "text2term",
        TRUE ~ method_id
      ),
      method_short = factor(method_short, levels = c("E12 (Maptology)", "text2term")),
      dataset = factor(dataset, levels = c("UKBB-EFO", "Biomappings", "OLS-EFO")),
      workload = factor(workload, levels = workload_levels(workload)),
      seconds = mean_request_seconds,
      seconds_label = if_else(seconds < 1, sprintf("%.4f s", seconds), sprintf("%.2f s", seconds))
    )

  speed_plot <- ggplot(speed_plot_data, aes(x = seconds, y = method_short, fill = method_short)) +
    geom_col(width = 0.7, show.legend = FALSE) +
    geom_text(
      aes(label = seconds_label),
      hjust = -0.15,
      size = 3,
      color = "grey20"
    ) +
    facet_grid(dataset ~ workload, scales = "free_x") +
    scale_x_continuous(expand = expansion(mult = c(0, 0.28))) +
    scale_fill_manual(values = okabe_ito[c(1, 2)]) +
    labs(
      title = speed_title,
      subtitle = "",
      x = "Average time per search (seconds)",
      y = NULL
    ) +
    theme_minimal(base_size = 12) +
    theme(
      panel.grid.major.y = element_blank(),
      panel.grid.minor = element_blank(),
      strip.text = element_text(face = "bold"),
      plot.title = element_text(face = "bold", hjust = 0.5),
      plot.subtitle = element_text(hjust = 0.5)
    )

  ggsave(speed_pdf_path, speed_plot, width = 8, height = 7)
  message("Wrote ", speed_pdf_path)
} else {
speed_plot_data <- speed_results %>%
  filter(primary_comparison == "yes") %>%
  mutate(
    method_short = case_when(
      method_id == "T" ~ "text2term",
      method_id == "batch32_dedup" ~ "E12 (Maptology)",
      TRUE ~ method_id
    ),
    method_short = factor(method_short, levels = c("E12 (Maptology)", "text2term")),
    dataset = factor(dataset, levels = c("UKBB-EFO", "Biomappings", "OLS-EFO")),
    workload = factor(workload, levels = workload_levels(workload))
  )

speed_plot <- ggplot(speed_plot_data, aes(x = median_seconds, y = method_short, fill = method_short)) +
  geom_col(width = 0.7, show.legend = FALSE) +
  geom_text(
    aes(label = sprintf("%.2f s", median_seconds)),
    hjust = -0.15,
    size = 3,
    color = "grey20"
  ) +
  facet_grid(dataset ~ workload, scales = "free_x") +
  scale_x_continuous(
    expand = expansion(mult = c(0, 0.25))
  ) +
  scale_fill_manual(values = okabe_ito[c(1, 2)]) +
  labs(
    title = "Search speed (median of 5 runs)",
    subtitle = "Lower is faster; index/cache load time excluded",
    x = "Median time (seconds)",
    y = NULL
  ) +
  theme_minimal(base_size = 12) +
  theme(
    panel.grid.major.y = element_blank(),
    panel.grid.minor = element_blank(),
    strip.text = element_text(face = "bold"),
    plot.title = element_text(face = "bold", hjust = 0.5),
    plot.subtitle = element_text(hjust = 0.5)
  )

ggsave(speed_pdf_path, speed_plot, width = 9, height = 7)
message("Wrote ", speed_pdf_path)

print(accuracy_plot)
print(speed_plot)
}
}
