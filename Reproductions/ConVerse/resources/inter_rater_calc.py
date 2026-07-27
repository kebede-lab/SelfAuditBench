import json
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import mean_absolute_error
import os
from pathlib import Path
import sys
from io import StringIO

class OutputCapture:
    """Class to capture print output for saving to files"""
    def __init__(self):
        self.contents = []
        self.original_stdout = sys.stdout
        
    def write(self, txt):
        self.contents.append(txt)
        self.original_stdout.write(txt)
        
    def flush(self):
        self.original_stdout.flush()
        
    def get_contents(self):
        return ''.join(self.contents)

def parse_ratings_from_json(json_file_path):
    """
    Parse ratings from a JSON file and extract all option ratings dynamically
    
    Parameters:
    json_file_path: str, path to JSON file
    
    Returns:
    dict: dictionary with option names as keys and ratings as values
    """
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_ratings = {}
    
    # Dynamically extract ratings from all categories (skip persona info)
    for key, value in data.items():
        if key != 'persona' and isinstance(value, dict):
            extract_category_ratings(value, all_ratings, key)
    
    return all_ratings

def extract_category_ratings(category_data, all_ratings, category_name, parent_key=""):
    """
    Recursively extract ratings from nested category structure
    Options are one level higher than the rating key
    """
    if isinstance(category_data, dict):
        for key, value in category_data.items():
            current_path = f"{parent_key}_{key}" if parent_key else key
            
            if isinstance(value, dict):
                if 'rating' in value and isinstance(value['rating'], (int, float)):
                    # The option name is the current key, which is one level higher than rating
                    option_key = f"{category_name}_{current_path}"
                    all_ratings[option_key] = value['rating']
                else:
                    # Continue recursing
                    extract_category_ratings(value, all_ratings, category_name, current_path)

def calculate_inter_rater_reliability(ratings_list, comparison_name=""):
    """
    Calculate comprehensive inter-rater reliability metrics for continuous ratings (0-10)
    
    Parameters:
    ratings_list: list of arrays/lists, each containing ratings from one annotator
    comparison_name: str, name for the comparison being performed
    
    Returns:
    dict: comprehensive reliability metrics
    """
    
    # Convert to numpy arrays
    ratings_array = np.array(ratings_list).T  # transpose so rows=items, cols=raters
    n_items, n_raters = ratings_array.shape
    
    header = f"INTER-RATER RELIABILITY ANALYSIS: {comparison_name}" if comparison_name else "INTER-RATER RELIABILITY ANALYSIS (0-10 Scale)"
    print("=" * len(header))
    print(header)
    print("=" * len(header))
    
    print(f"\nDataset Information:")
    print(f"Number of items rated: {n_items}")
    print(f"Number of raters: {n_raters}")
    print(f"Rating scale: 0-10")
    
    # 1. Descriptive Statistics
    print(f"\n1. DESCRIPTIVE STATISTICS")
    print("-" * 40)
    
    rater_means = np.mean(ratings_array, axis=0)
    rater_stds = np.std(ratings_array, axis=0)
    
    for i in range(n_raters):
        print(f"Rater {i+1} - Mean: {rater_means[i]:.2f}, Std: {rater_stds[i]:.2f}")
    
    # 2. Pairwise Correlations
    print(f"\n2. PAIRWISE CORRELATIONS")
    print("-" * 40)
    
    pearson_correlations = []
    spearman_correlations = []
    
    for i in range(n_raters):
        for j in range(i+1, n_raters):
            pearson_corr, _ = pearsonr(ratings_array[:, i], ratings_array[:, j])
            spearman_corr, _ = spearmanr(ratings_array[:, i], ratings_array[:, j])
            
            pearson_correlations.append(pearson_corr)
            spearman_correlations.append(spearman_corr)
            
            print(f"Rater {i+1} vs Rater {j+1}:")
            print(f"  Pearson r: {pearson_corr:.3f}")
            print(f"  Spearman ρ: {spearman_corr:.3f}")
    
    avg_pearson = np.mean(pearson_correlations)
    avg_spearman = np.mean(spearman_correlations)
    
    print(f"\nAverage Pearson correlation: {avg_pearson:.3f}")
    print(f"Average Spearman correlation: {avg_spearman:.3f}")
    
    # 3. Mean Absolute Differences
    print(f"\n3. MEAN ABSOLUTE DIFFERENCES")
    print("-" * 40)
    
    mad_values = []
    for i in range(n_raters):
        for j in range(i+1, n_raters):
            mad = mean_absolute_error(ratings_array[:, i], ratings_array[:, j])
            mad_values.append(mad)
            print(f"Rater {i+1} vs Rater {j+1}: {mad:.2f}")
    
    avg_mad = np.mean(mad_values)
    print(f"Average Mean Absolute Difference: {avg_mad:.2f}")
    
    # 4. Intraclass Correlation (approximated)
    print(f"\n4. RELIABILITY ESTIMATES")
    print("-" * 40)
    
    # Calculate ICC approximation using one-way ANOVA approach
    # Between-groups variance (items)
    item_means = np.mean(ratings_array, axis=1)
    grand_mean = np.mean(ratings_array)
    
    mse_between = n_raters * np.var(item_means, ddof=1)
    mse_within = np.mean([np.var(ratings_array[i, :], ddof=1) for i in range(n_items)])
    
    # ICC approximation (consistency)
    if mse_within > 0:
        icc_approx = (mse_between - mse_within) / (mse_between + (n_raters - 1) * mse_within)
    else:
        icc_approx = 1.0
    
    print(f"ICC approximation (consistency): {icc_approx:.3f}")
    
    # 5. Agreement Classification
    print(f"\n5. RELIABILITY INTERPRETATION")
    print("-" * 40)
    
    def interpret_correlation(corr):
        if corr >= 0.90:
            return "Excellent"
        elif corr >= 0.75:
            return "Good"
        elif corr >= 0.50:
            return "Moderate"
        elif corr >= 0.25:
            return "Fair"
        else:
            return "Poor"
    
    print(f"Average Pearson correlation: {interpret_correlation(avg_pearson)}")
    print(f"Average Spearman correlation: {interpret_correlation(avg_spearman)}")
    
    if avg_mad <= 1.0:
        mad_interp = "Excellent (≤ 1 point difference)"
    elif avg_mad <= 2.0:
        mad_interp = "Good (≤ 2 points difference)"
    elif avg_mad <= 3.0:
        mad_interp = "Moderate (≤ 3 points difference)"
    else:
        mad_interp = "Poor (> 3 points difference)"
    
    print(f"Mean Absolute Difference: {mad_interp}")
    
    # Return results
    results = {
        'n_items': n_items,
        'n_raters': n_raters,
        'avg_pearson_correlation': avg_pearson,
        'avg_spearman_correlation': avg_spearman,
        'avg_mean_absolute_difference': avg_mad,
        'icc_approximation': icc_approx,
        'pearson_correlations': pearson_correlations,
        'spearman_correlations': spearman_correlations,
        'mad_values': mad_values,
        'rater_statistics': {
            'means': rater_means,
            'stds': rater_stds
        }
    }
    
    return results

def create_detailed_comparison_table(ratings_list, item_names=None, rater_names=None):
    """
    Create a detailed comparison table showing all ratings side by side
    """
    ratings_df = pd.DataFrame(np.array(ratings_list).T)
    
    if rater_names:
        ratings_df.columns = rater_names
    else:
        ratings_df.columns = [f'Rater_{i+1}' for i in range(len(ratings_list))]
    
    if item_names:
        ratings_df['Item'] = item_names
        column_order = ['Item'] + list(ratings_df.columns[:-1])
        ratings_df = ratings_df[column_order]
    
    # Add difference columns
    n_raters = len(ratings_list)
    if n_raters >= 2:
        rating_columns = ratings_df.columns[-n_raters:] if item_names else ratings_df.columns
        ratings_df['Max_Diff'] = ratings_df[rating_columns].max(axis=1) - ratings_df[rating_columns].min(axis=1)
        ratings_df['Std_Dev'] = ratings_df[rating_columns].std(axis=1)
    
    return ratings_df

def interpret_correlation(corr):
    """Interpret correlation coefficient values"""
    if corr >= 0.90:
        return "Excellent"
    elif corr >= 0.75:
        return "Good"
    elif corr >= 0.50:
        return "Moderate"
    elif corr >= 0.25:
        return "Fair"
    else:
        return "Poor"

def interpret_mad(mad):
    """Interpret Mean Absolute Difference values"""
    if mad <= 1.0:
        return "Excellent"
    elif mad <= 2.0:
        return "Good"
    elif mad <= 3.0:
        return "Moderate"
    else:
        return "Poor"

def interpret_icc(icc):
    """Interpret ICC (Intraclass Correlation Coefficient) values"""
    if icc >= 0.90:
        return "Excellent"
    elif icc >= 0.75:
        return "Good"
    elif icc >= 0.50:
        return "Moderate"
    elif icc >= 0.25:
        return "Fair"
    else:
        return "Poor"

def calculate_averaged_results(all_results):
    """
    Calculate averaged results across personas for each model and use case
    
    Returns:
    dict: averaged results organized by model -> use_case -> averaged_metrics
    """
    averaged_results = {}
    
    # Collect all models
    all_models = set()
    for use_case_results in all_results.values():
        for persona_results in use_case_results.values():
            all_models.update(persona_results.keys())
    
    all_models = sorted(list(all_models))
    
    for model in all_models:
        averaged_results[model] = {}
        
        for use_case_name, use_case_results in all_results.items():
            # Collect all metrics for this model and use case across personas
            pearson_values = []
            spearman_values = []
            mad_values = []
            icc_values = []
            
            for persona_name, persona_results in use_case_results.items():
                if model in persona_results:
                    metrics = persona_results[model]['reliability_metrics']
                    pearson_values.append(metrics['avg_pearson_correlation'])
                    spearman_values.append(metrics['avg_spearman_correlation'])
                    mad_values.append(metrics['avg_mean_absolute_difference'])
                    icc_values.append(metrics['icc_approximation'])
            
            # Calculate averages if we have data
            if pearson_values:
                averaged_results[model][use_case_name] = {
                    'avg_pearson_correlation': np.mean(pearson_values),
                    'avg_spearman_correlation': np.mean(spearman_values),
                    'avg_mean_absolute_difference': np.mean(mad_values),
                    'icc_approximation': np.mean(icc_values),
                    'n_personas': len(pearson_values)
                }
    
    return averaged_results

def interpretation_to_score(interpretation):
    """Convert interpretation category to numerical score for averaging"""
    score_map = {
        "Excellent": 5,
        "Good": 4, 
        "Moderate": 3,
        "Fair": 2,
        "Poor": 1
    }
    return score_map.get(interpretation, 3)  # Default to Moderate if unknown

def score_to_interpretation(score):
    """Convert averaged numerical score back to interpretation category"""
    if score >= 4.5:
        return "Excellent"
    elif score >= 3.5:
        return "Good"
    elif score >= 2.5:
        return "Moderate" 
    elif score >= 1.5:
        return "Fair"
    else:
        return "Poor"

def calculate_categorical_averaged_results(all_results):
    """
    Calculate averaged interpretation categories across personas for each model and use case
    
    Returns:
    dict: averaged categorical results organized by model -> use_case -> averaged_interpretations
    """
    categorical_results = {}
    
    # Collect all models
    all_models = set()
    for use_case_results in all_results.values():
        for persona_results in use_case_results.values():
            all_models.update(persona_results.keys())
    
    all_models = sorted(list(all_models))
    
    for model in all_models:
        categorical_results[model] = {}
        
        for use_case_name, use_case_results in all_results.items():
            # Collect all interpretation scores for this model and use case across personas
            pearson_scores = []
            spearman_scores = []
            mad_scores = []
            icc_scores = []
            
            for persona_name, persona_results in use_case_results.items():
                if model in persona_results:
                    metrics = persona_results[model]['reliability_metrics']
                    
                    # Convert interpretations to scores
                    pearson_interp = interpret_correlation(metrics['avg_pearson_correlation'])
                    spearman_interp = interpret_correlation(metrics['avg_spearman_correlation'])
                    mad_interp = interpret_mad(metrics['avg_mean_absolute_difference'])
                    icc_interp = interpret_icc(metrics['icc_approximation'])
                    
                    pearson_scores.append(interpretation_to_score(pearson_interp))
                    spearman_scores.append(interpretation_to_score(spearman_interp))
                    mad_scores.append(interpretation_to_score(mad_interp))
                    icc_scores.append(interpretation_to_score(icc_interp))
            
            # Calculate averaged scores and convert back to interpretations
            if pearson_scores:
                categorical_results[model][use_case_name] = {
                    'pearson_interpretation': score_to_interpretation(np.mean(pearson_scores)),
                    'spearman_interpretation': score_to_interpretation(np.mean(spearman_scores)),
                    'mad_interpretation': score_to_interpretation(np.mean(mad_scores)),
                    'icc_interpretation': score_to_interpretation(np.mean(icc_scores)),
                    'n_personas': len(pearson_scores)
                }
    
    return categorical_results

# MAIN ANALYSIS FUNCTION FOR ALL USE CASES
def analyze_all_use_cases():
    """
    Main function to analyze inter-rater reliability across all use cases dynamically
    """
    # Get the resources directory (current script location)
    resources_dir = Path(__file__).parent
    
    # Find all use case directories (those ending with '_usecase')
    use_case_dirs = [d for d in resources_dir.iterdir() 
                     if d.is_dir() and d.name.endswith('_usecase')]
    
    print(f"Found {len(use_case_dirs)} use cases: {[d.name for d in use_case_dirs]}")
    
    all_results = {}
    
    for use_case_dir in use_case_dirs:
        use_case_name = use_case_dir.name
        print(f"\n{'='*80}")
        print(f"PROCESSING USE CASE: {use_case_name.upper()}")
        print(f"{'='*80}")
        
        ratings_dir = use_case_dir / 'ratings'
        study_dir = ratings_dir / 'study'
        
        if not ratings_dir.exists() or not study_dir.exists():
            print(f"Skipping {use_case_name}: Missing ratings or study directory")
            continue
            
        use_case_results = analyze_use_case_ratings(ratings_dir, study_dir, use_case_name)
        all_results[use_case_name] = use_case_results
    
    return all_results

def analyze_use_case_ratings(ratings_dir, study_dir, use_case_name):
    """
    Analyze ratings for a specific use case, comparing main ratings with study ratings
    """
    use_case_results = {}
    
    # Process personas 1-4 only
    for persona_num in range(1, 5):
        persona_name = f"persona{persona_num}"
        main_ratings_file = ratings_dir / f"ratings_{persona_name}.json"
        
        if not main_ratings_file.exists():
            print(f"Skipping {persona_name}: Main ratings file not found")
            continue
            
        print(f"\n{'-'*60}")
        print(f"PROCESSING {persona_name.upper()} in {use_case_name}")
        print(f"{'-'*60}")
        
        # Load main ratings
        try:
            main_ratings = parse_ratings_from_json(main_ratings_file)
            option_names = list(main_ratings.keys())
            main_ratings_list = [main_ratings[option] for option in option_names]
            
            print(f"Loaded {len(option_names)} options from main ratings file")
            
        except Exception as e:
            print(f"Error loading main ratings for {persona_name}: {e}")
            continue
        
        # Find all study files for this persona (with model suffixes)
        study_pattern = f"template_ratings_{persona_name}_*.json"
        study_files = list(study_dir.glob(study_pattern))
        
        # Filter out the base template file without suffix
        study_files = [f for f in study_files if not f.name.endswith(f"_{persona_name}.json")]
        
        if not study_files:
            print(f"No study files found for {persona_name}")
            continue
            
        print(f"Found {len(study_files)} study files for comparison")
        
        persona_results = {}
        
        for study_file in study_files:
            # Extract model suffix from filename
            filename = study_file.stem  # removes .json
            # Extract suffix after last underscore
            model_suffix = filename.split('_')[-1]
            
            if model_suffix == persona_name:  # Skip base template files
                continue
                
            print(f"\nComparing with model: {model_suffix}")
            
            try:
                # Load study ratings
                study_ratings = parse_ratings_from_json(study_file)
                
                # Ensure consistent ordering with main ratings
                study_ratings_list = [study_ratings.get(option, 0) for option in option_names]
                
                # Calculate pairwise reliability
                reliability_results = calculate_inter_rater_reliability(
                    [main_ratings_list, study_ratings_list], 
                    comparison_name=f"{persona_name} vs {model_suffix}"
                )
                
                # Create comparison table
                comparison_df = create_detailed_comparison_table(
                    [main_ratings_list, study_ratings_list], 
                    option_names,
                    rater_names=[f"{persona_name}_main", f"{persona_name}_{model_suffix}"]
                )
                
                persona_results[model_suffix] = {
                    'reliability_metrics': reliability_results,
                    'comparison_table': comparison_df
                }
                
            except Exception as e:
                print(f"Error processing {model_suffix}: {e}")
                continue
        
        use_case_results[persona_name] = persona_results
    
    return use_case_results

# DEMO WITH NEW STRUCTURE
def demo_with_new_structure():
    """
    Demo function using the new dynamic structure across all use cases
    """
    return analyze_all_use_cases()

def print_summary_results_by_model(all_results):
    """
    Print a summary of all results organized by model first, then persona
    """
    print("\n" + "="*100)
    print("SUMMARY REPORT - INTER-RATER RELIABILITY ACROSS ALL USE CASES")
    print("="*100)
    
    # Collect all models across all use cases
    all_models = set()
    for use_case_results in all_results.values():
        for persona_results in use_case_results.values():
            all_models.update(persona_results.keys())
    
    all_models = sorted(list(all_models))
    
    print(f"\nRESULTS BY MODEL:")
    print("="*60)
    
    for model in all_models:
        print(f"\n{model.upper()}:")
        print("-" * 60)
        
        for use_case_name, use_case_results in all_results.items():
            print(f"\n  {use_case_name.upper()}:")
            
            for persona_name in sorted(use_case_results.keys()):
                persona_results = use_case_results[persona_name]
                
                if model in persona_results:
                    metrics = persona_results[model]['reliability_metrics']
                    pearson_r = metrics['avg_pearson_correlation']
                    spearman_rho = metrics['avg_spearman_correlation']
                    mad = metrics['avg_mean_absolute_difference']
                    icc = metrics['icc_approximation']
                    
                    print(f"    {persona_name}:")
                    print(f"      Pearson r: {pearson_r:.3f} ({interpret_correlation(pearson_r)})")
                    print(f"      Spearman ρ: {spearman_rho:.3f} ({interpret_correlation(spearman_rho)})")
                    print(f"      Mean Abs Diff: {mad:.2f} ({interpret_mad(mad)})")
                    print(f"      ICC approx: {icc:.3f} ({interpret_icc(icc)})")
                else:
                    print(f"    {persona_name}: No data available")

def print_averaged_summary_by_model(averaged_results):
    """
    Print averaged summary results organized by model first, then use case
    """
    print("\n" + "="*100)
    print("AVERAGED SUMMARY REPORT - INTER-RATER RELIABILITY ACROSS ALL USE CASES")
    print("(Averaged across all personas for each model and use case)")
    print("="*100)
    
    print(f"\nRESULTS BY MODEL (AVERAGED ACROSS PERSONAS):")
    print("="*60)
    
    for model, model_results in averaged_results.items():
        print(f"\n{model.upper()}:")
        print("-" * 60)
        
        for use_case_name, metrics in model_results.items():
            pearson_r = metrics['avg_pearson_correlation']
            spearman_rho = metrics['avg_spearman_correlation']
            mad = metrics['avg_mean_absolute_difference']
            icc = metrics['icc_approximation']
            n_personas = metrics['n_personas']
            
            print(f"\n  {use_case_name.upper()} (n={n_personas} personas):")
            print(f"    Pearson r: {pearson_r:.3f} ({interpret_correlation(pearson_r)})")
            print(f"    Spearman ρ: {spearman_rho:.3f} ({interpret_correlation(spearman_rho)})")
            print(f"    Mean Abs Diff: {mad:.2f} ({interpret_mad(mad)})")
            print(f"    ICC approx: {icc:.3f} ({interpret_icc(icc)})")

def save_averaged_summary_to_file(all_results, filename="IRR_results_summary_averaged.txt"):
    """
    Save averaged summary results to a file
    """
    # Calculate averaged results
    averaged_results = calculate_averaged_results(all_results)
    
    # Capture the averaged summary output
    summary_capture = OutputCapture()
    original_stdout = sys.stdout
    sys.stdout = summary_capture
    
    try:
        print_averaged_summary_by_model(averaged_results)
        summary_content = summary_capture.get_contents()
    finally:
        sys.stdout = original_stdout
    
    # Save to file
    resources_dir = Path(__file__).parent
    summary_file = resources_dir / filename
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    print(f"Averaged summary results saved to: {summary_file}")
    return summary_content

def print_categorical_summary_by_model(categorical_results):
    """
    Print categorical interpretation summary organized by model first, then use case
    """
    print("\n" + "="*100)
    print("CATEGORICAL INTERPRETATION SUMMARY - INTER-RATER RELIABILITY ACROSS ALL USE CASES")
    print("(Averaged interpretation categories across all personas for each model and use case)")
    print("="*100)
    
    print(f"\nRESULTS BY MODEL (CATEGORICAL INTERPRETATIONS ONLY):")
    print("="*60)
    
    for model, model_results in categorical_results.items():
        print(f"\n{model.upper()}:")
        print("-" * 60)
        
        for use_case_name, interpretations in model_results.items():
            n_personas = interpretations['n_personas']
            
            print(f"\n  {use_case_name.upper()} (n={n_personas} personas):")
            print(f"    Pearson r: {interpretations['pearson_interpretation']}")
            print(f"    Spearman ρ: {interpretations['spearman_interpretation']}")
            print(f"    Mean Abs Diff: {interpretations['mad_interpretation']}")
            print(f"    ICC approx: {interpretations['icc_interpretation']}")

def save_categorical_summary_to_file(all_results, filename="IRR_results_summary_averaged_categorical_interpretability.txt"):
    """
    Save categorical interpretation summary to a file
    """
    # Calculate categorical results
    categorical_results = calculate_categorical_averaged_results(all_results)
    
    # Capture the categorical summary output
    summary_capture = OutputCapture()
    original_stdout = sys.stdout
    sys.stdout = summary_capture
    
    try:
        print_categorical_summary_by_model(categorical_results)
        summary_content = summary_capture.get_contents()
    finally:
        sys.stdout = original_stdout
    
    # Save to file
    resources_dir = Path(__file__).parent
    summary_file = resources_dir / filename
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    print(f"Categorical interpretation summary saved to: {summary_file}")
    return summary_content

def save_summary_results_to_file(all_results, filename="IRR_results_summary.txt"):
    """
    Save summary results to a file with model-first organization
    """
    # Capture the summary output
    summary_capture = OutputCapture()
    original_stdout = sys.stdout
    sys.stdout = summary_capture
    
    try:
        print_summary_results_by_model(all_results)
        summary_content = summary_capture.get_contents()
    finally:
        sys.stdout = original_stdout
    
    # Save to file
    resources_dir = Path(__file__).parent
    summary_file = resources_dir / filename
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    print(f"\nSummary results saved to: {summary_file}")
    return summary_content

# DEMO WITH NEW STRUCTURE
def demo_with_new_structure():
    """
    Demo function using the new dynamic structure across all use cases
    """
    # Capture all output
    output_capture = OutputCapture()
    sys.stdout = output_capture
    
    try:
        # Print interpretation guidelines at the beginning of full results
        print("=" * 100)
        print("INTER-RATER RELIABILITY ANALYSIS - INTERPRETATION GUIDELINES")
        print("=" * 100)
        print("\nCORRELATION COEFFICIENTS (Pearson r & Spearman ρ):")
        print("  • Excellent: ≥ 0.90")
        print("  • Good: 0.75 - 0.89")
        print("  • Moderate: 0.50 - 0.74")
        print("  • Fair: 0.25 - 0.49") 
        print("  • Poor: < 0.25")
        print("\nMEAN ABSOLUTE DIFFERENCE (0-10 scale):")
        print("  • Excellent: ≤ 1.0 points")
        print("  • Good: 1.1 - 2.0 points")
        print("  • Moderate: 2.1 - 3.0 points")
        print("  • Poor: > 3.0 points")
        print("\nICC (INTRACLASS CORRELATION COEFFICIENT):")
        print("  • Excellent: ≥ 0.90")
        print("  • Good: 0.75 - 0.89")
        print("  • Moderate: 0.50 - 0.74")
        print("  • Fair: 0.25 - 0.49")
        print("  • Poor: < 0.25")
        print("\n" + "=" * 100)
        print("DETAILED ANALYSIS RESULTS")
        print("=" * 100)
        
        results = analyze_all_use_cases()
        # Print the old-style summary to capture it in full output
        print("\n" + "="*100)
        print("SUMMARY REPORT - INTER-RATER RELIABILITY ACROSS ALL USE CASES (Original Format)")
        print("="*100)
        
        for use_case_name, use_case_results in results.items():
            print(f"\n{use_case_name.upper()}:")
            print("-" * 60)
            
            for persona_name, persona_results in use_case_results.items():
                print(f"\n  {persona_name.upper()}:")
                
                for model_suffix, model_results in persona_results.items():
                    metrics = model_results['reliability_metrics']
                    print(f"    {model_suffix}:")
                    print(f"      Pearson r: {metrics['avg_pearson_correlation']:.3f}")
                    print(f"      Spearman ρ: {metrics['avg_spearman_correlation']:.3f}")  
                    print(f"      Mean Abs Diff: {metrics['avg_mean_absolute_difference']:.2f}")
                    print(f"      ICC approx: {metrics['icc_approximation']:.3f}")
        
    finally:
        # Restore stdout
        sys.stdout = output_capture.original_stdout
    
    # Save full output to IRR_results.txt
    resources_dir = Path(__file__).parent
    full_output_file = resources_dir / "IRR_results.txt"
    full_output_content = output_capture.get_contents()
    
    # with open(full_output_file, 'w', encoding='utf-8') as f:
    #     f.write(full_output_content)
    
    # print(f"Full results saved to: {full_output_file}")
    
    # Save reorganized summary to IRR_results_summary.txt
    # save_summary_results_to_file(results)
    
    # Save averaged summary to IRR_results_summary_averaged.txt
    save_averaged_summary_to_file(results)
    
    # Save categorical interpretation summary to IRR_results_summary_averaged_categorical_interpretability.txt
    # save_categorical_summary_to_file(results)
    
    return results

# Run the demo
if __name__ == "__main__":
    results = demo_with_new_structure()
