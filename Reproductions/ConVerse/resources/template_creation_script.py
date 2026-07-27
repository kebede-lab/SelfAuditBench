import json
import os
import glob

def replace_keys(obj):
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if k == "rating":
                new_obj[k] = "<generate_rating_value_from_0_to_10_here>"
            elif k == "reasons":
                new_obj[k] = "<generate_reasons_as_a_list_of_strings_here>"
            else:
                new_obj[k] = replace_keys(v)
        return new_obj
    elif isinstance(obj, list):
        return [replace_keys(item) for item in obj]
    else:
        return obj

# Find all use case directories
resources_dir = "resources"
use_case_dirs = [d for d in os.listdir(resources_dir) 
                 if os.path.isdir(os.path.join(resources_dir, d)) and d.endswith("_usecase")]

print(f"Found use case directories: {use_case_dirs}")

# Process all ratings files in each use case
for use_case_dir in use_case_dirs:
    ratings_dir = os.path.join(resources_dir, use_case_dir, "ratings")
    
    if not os.path.exists(ratings_dir):
        print(f"Ratings directory not found: {ratings_dir}")
        continue
    
    # Find all JSON files in the ratings directory (exclude existing template files)
    ratings_files = [f for f in glob.glob(os.path.join(ratings_dir, "*.json")) 
                     if not os.path.basename(f).startswith("template_")]
    
    print(f"\nProcessing {use_case_dir}:")
    for file_path in ratings_files:
        try:
            # Read the original file
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Apply the replacements
            new_data = replace_keys(data)
            
            # Create the template filename
            file_dir = os.path.dirname(file_path)
            file_name = os.path.basename(file_path)
            name_without_ext = os.path.splitext(file_name)[0]
            template_file_path = os.path.join(file_dir, f"template_{name_without_ext}.json")
            
            # Save to the new template file
            with open(template_file_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)
            
            print(f"  Created template: {template_file_path}")
            
        except Exception as e:
            print(f"  Error processing {file_path}: {e}")

print("\nTemplate generation completed!")