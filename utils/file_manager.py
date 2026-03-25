import csv
from pathlib import Path

from utils.benchmark_utils import KEY_MODEL_NAME


def get_filepaths(directory: str, extensions_filter: list[str] = None) -> list[str]:
    """
    Obtains all filepaths of files with the given extensions from the specified 
    directory and its subdirectories.

    :param directory: The root directory as a string or Path object.
    :param extensions_filter: Optional list of file extensions (e.g., ['.uvl', '.json']).
    :return: List of filepaths as strings.
    """
    root_path = Path(directory)
    filepaths = []
    
    if extensions_filter is None:
        extensions_filter = []
    
    norm_filters = [ext.lower() for ext in extensions_filter]
    for path in root_path.rglob('*'):
        if path.is_file():
            if not norm_filters or any(path.name.lower().endswith(ext) for ext in norm_filters):
                filepaths.append(str(path))
    return filepaths


def get_models_to_run(models_dir: str, output_csv: str) -> list[str]:
    all_model_paths = get_filepaths(models_dir, ['.uvl'])
    if not all_model_paths:
        print(f"🛑 No models found in directory: {models_dir}")
        return []
    processed_model_names = get_processed_model_names(output_csv)
    model_paths_to_run = []
    for path in all_model_paths:
        model_name = Path(path).stem
        if model_name not in processed_model_names:
            model_paths_to_run.append(path)
    num_total = len(all_model_paths)
    num_to_run = len(model_paths_to_run)
    num_skipped = num_total - num_to_run

    print(f"🔎 Found {num_total} models to analyze in total.")
    if num_skipped > 0:
        print(f"⏩ Skipping {num_skipped} models already processed and found in '{output_csv}'.")
    if not model_paths_to_run:
        print(f"✅ All models already processed. Nothing new to run.")
        return []
    return model_paths_to_run


def get_processed_model_names(filename: str) -> set[str]:
    """
    Reads the existing CSV file and returns a set of model names already processed.
    Returns an empty set if the file does not exist or is empty/corrupt.
    """
    file_path = Path(filename)
    if not file_path.exists():
        return set()

    processed_models: set[str] = set()
    try:
        with file_path.open('r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Ensure the required header for model name exists
            if KEY_MODEL_NAME not in reader.fieldnames:
                print(f"⚠️ Warning: CSV file '{filename}' exists but lacks the required header '{KEY_MODEL_NAME}'. Rerunning all models.")
                return set()

            for row in reader:
                # We collect all model names found in the file
                if row.get(KEY_MODEL_NAME):
                    processed_models.add(row[KEY_MODEL_NAME])
    except Exception as e:
        print(f"⚠️ Warning: Could not read existing CSV '{filename}' for processed models. Rerunning all models. Error: {e}")
        return set()
    
    return processed_models