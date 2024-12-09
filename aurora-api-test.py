from aurora_pdf_generator import AuroraAPI
import json 
from datetime import datetime

def print_api_responses(api_key, tenant_id, design_id, project_id, output_file=None):
    api = AuroraAPI(api_key, tenant_id)
    
    if not api.validate_credentials():
        return "Failed to validate API credentials"
    
    responses = {
        "Design Summary": api.get_design_summary(design_id),
        "Design Pricing": api.get_design_pricing(design_id),
        "Design Assets": api.get_design_assets(design_id),
        "Project Data": api.get_project(project_id)
    }
    
    json_output = json.dumps(responses, indent=2)
    
    if output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_file}_{timestamp}.txt"
        with open(filename, 'w') as f:
            f.write(json_output)
        return f"API responses saved to {filename}"
    
    return json_output

if __name__ == "__main__":
    API_KEY = "rk_prod_75eafe223db3f63c30a0efad"
    TENANT_ID = "06a7ae68-5de3-42a6-968c-2f8fa4431a12"
    DESIGN_ID = "f9d4fbe6-39ee-46a8-b4bb-bb7ee879453e"
    PROJECT_ID = "2af907f0-62bc-4daf-a31a-c80e686824a5"
    
    print(print_api_responses(API_KEY, TENANT_ID, DESIGN_ID, PROJECT_ID, "aurora_api_responses"))
