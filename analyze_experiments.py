#!/usr/bin/env python3

# This script analyzes experiment runs and does statistical tests.
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import json
import pandas as pd
from scipy.stats import mannwhitneyu, tmean, tstd
from pathlib import Path

# Define the paths and parameters
targets = ['cgi_decode', 'json', 'mjs', 'tinyc', 'calc', 'yxml', 'calcrs', 'jsonrs', 'calccpp', 'jsoncpp', 'xmlcpp']
miners = ['mimid', 'gdbminer', 'arvada', 'treevada']
test_miners = ['arvada', 'treevada']  # Exclude mimid from the Mann-Whitney U test
no_trials = 50

# Initialize an empty list to store the data
data = []

# Loop through each output folder, target, and miner to load the data

def output_folder(i) -> Path:
    return Path(f"output_{i}")

seed_lengths = {}
for target in targets:
    
	seed_lengths[target] = []

	for i in range(1, no_trials + 1):
		for miner in miners:
			file_path = output_folder(i) / f'{target}.20.{miner}.result'
			if file_path.exists():
				with open(file_path, 'r') as file:
					result = json.load(file)
					precision = result.get('precision')
					recall = result.get('recall')
					f1 = result.get('f1')
					duration = result.get('execution_duration')
					
					if duration is not None:
						data.append([i, target, miner, 'duration', duration])
					if precision is not None:
						data.append([i, target, miner, 'precision', precision])
					if recall is not None:
						data.append([i, target, miner, 'recall', recall])
					if f1 is not None:
						data.append([i, target, miner, 'f1', f1])
					elif precision is not None and recall is not None:
							f1 = 2 * (precision * recall) / (precision + recall)
							data.append([i, target, miner, 'f1', f1])
					else:
						print(f"Error: Missing precision and recall for {target} in trial {i} with {miner}")
		

		# Get seed properties
		seeds_folder = output_folder(i) / target / "seeds"
		if seeds_folder.exists():
			# Get average length of seeds
			for seed_file in seeds_folder.iterdir():
				if seed_file.is_file():
					with open(seed_file, 'r') as file:
						seed  = file.read()
						seed_lengths[target].append(len(seed))
      

    


# Step 2: Prepare the Data
df = pd.DataFrame(data, columns=['trial', 'target', 'miner', 'metric', 'value'])


# Step 3: Get Timing and Seed Statistics
latex_table = []
preambel = "\\begin{table}[t]\n\\centering\n"
preambel += f"\\caption{{Timing and seed statistics averaged from {no_trials} runs.}}\n"
preambel += f"\\label{{tab:eval_time_seed}}\n"
preambel += "\\begin{tabular}{l" + "D{;}{{\\color{gray}\\pm}}{5.5}" * (len(miners)+1) + "}\n"
latex_table.append(preambel)
header = "Target & \\multicolumn{1}{c}{ Seed Lengths }  & " + " & ".join([f"\\multicolumn{{1}}{{c}}{{ {miner.capitalize()} }} " for miner in miners]) + " \\\\ \n\\hline"
latex_table.append(header)
for target in targets:

	line = f"{target.replace('_', '')} "
	if seed_lengths[target]:
		line += f" & {tmean(seed_lengths[target]):.2f} ; {tstd(seed_lengths[target]):.2f} "
  
	metric_df = df[(df['metric'] == 'duration') & (df['target'] == target)]
	for miner in miners:
		duration = pd.to_timedelta(metric_df[metric_df['miner'] == miner]['value'].mean(), unit='s').round('s')
		duration_std = metric_df[metric_df['miner'] == miner]['value'].std()
		if not pd.isna(duration):
			line += f" & {duration.seconds}s ; {duration_std:.0f}"
		else :
			line += " & \\multicolumn{1}{c}{ N/A }"
	latex_table.append(line + " \\\\")
  
latex_table.append("\\hline\n\\end{tabular}\n\\end{table}\n\n")
# Print the LaTeX table
for line in latex_table:
	print(line)

# Step 4: Identify the Top Miner and Perform the Mann-Whitney U Test
results = []

for metric in ['precision', 'recall', 'f1']:
	for target in targets:
		metric_df = df[(df['metric'] == metric) & (df['target'] == target)]
		
		# Calculate the mean and standard deviation for each miner
		stats_df = metric_df[metric_df['miner'].isin(test_miners)].groupby('miner')['value'].agg(['mean', 'std']).sort_values(by='mean', ascending=False)
		
		
		
		if len(stats_df) > 1:
			# Identify the top miner
			top_miner = stats_df.index[0]
			#miner1 = 'gdbminer'
			#miner2 = top_miner
			top_values = metric_df[metric_df['miner'] == top_miner]['value']
			gdbminer_values = metric_df[metric_df['miner'] == 'gdbminer']['value']

			if top_values.agg('mean') > gdbminer_values.agg('mean'):
				miner1 = top_miner
				miner2 = 'gdbminer'
				values1 = metric_df[metric_df['miner'] == top_miner]['value']
				values2 = metric_df[metric_df['miner'] == 'gdbminer']['value']
			else:
				miner1 = 'gdbminer'
				miner2 = top_miner
				values1 = metric_df[metric_df['miner'] == 'gdbminer']['value']
				values2 = metric_df[metric_df['miner'] == top_miner]['value']
	
			
			# Check if there are enough values to perform the test
			if len(top_values) > 0 and len(gdbminer_values) > 0:
				# Perform the Mann-Whitney U test
				stat, p = mannwhitneyu(values1, values2, alternative='two-sided')
				results.append([target, metric, miner1, miner2, stat, p])
			else:
				results.append([target, metric, miner1, miner2, None, None])

# Convert results to DataFrame for better readability
results_df = pd.DataFrame(results, columns=['target', 'metric', 'miner1', 'miner2', 'stat', 'p_value'])

# Step 5: Format the Results for LaTeX
latex_table = []

for metric in ['precision', 'recall', 'f1']:
	preambel = "\\begin{table}[t]\n\\centering\n"
	preambel += f"\\caption{{{metric.capitalize()}-scores in percentage averaged from {no_trials} runs. Bold values show significant improvement to second-best approach (excluding Mimid).}}\n"
	preambel += f"\\label{{tab:eval_{metric}}}\n"
	preambel += "\\begin{tabular}{l" + "D{:}{{\\color{gray}\\pm}}{5.5}" * len(miners) + "}\n"
	latex_table.append(preambel)
	header = "Target & " + " & ".join([f"\\multicolumn{{1}}{{c}}{{ {miner.capitalize()} }} " for miner in miners]) + " \\\\ \n\\hline"
	latex_table.append(header)
	
	for target in targets:
		row = [target.replace('_', '')]
		for miner in miners:
			mean_value = df[(df['metric'] == metric) & (df['target'] == target) & (df['miner'] == miner)]['value'].mean()
			std_value = df[(df['metric'] == metric) & (df['target'] == target) & (df['miner'] == miner)]['value'].std()
			if pd.isna(mean_value) or pd.isna(std_value):
				row.append("\\multicolumn{1}{c}{ N/A }")
			else:
				mean_value *= 100  # Convert to percentage
				std_value *= 100  # Convert to percentage
				# Check if the result is significant
				significant = False
				for _, result in results_df[(results_df['target'] == target) & (results_df['metric'] == metric)].iterrows():
					if (result['miner1'] == miner ) and result['p_value'] is not None and result['p_value'] < 0.05:
						significant = True
						break
				if significant:
					row.append(f"\\textbf{{{mean_value:.2f}}}:{std_value:.2f}")
				else:
					row.append(f"{mean_value:.2f}:\t{std_value:.2f}\t")
		latex_table.append(" & ".join(row) + " \\\\")
	

	latex_table.append("\\hline\n\\end{tabular}\n\\end{table}\n\n")

# Print the LaTeX table
for line in latex_table:
	print(line)
 