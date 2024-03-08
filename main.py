import re
import json
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import requests


# Function to create the directory that will contain the exported files
def create_export_directories(subdomain):
    """
    Create directories for exporting files.

    Parameters:
    - subdomain (str): The subdomain for the dApp.

    Returns:
    - str: Path to the created subdomain directory.
    """

    exports_directory = "exports"
    subdomain_directory = os.path.join(exports_directory, subdomain)
    os.makedirs(subdomain_directory, exist_ok=True)
    return subdomain_directory


# Function to export the ABI JSON to a file
def export_abi_json(abi_json, name_field, subdomain_directory):
    """
    Export the ABI JSON to a file.

    Parameters:
    - abi_json (dict): The ABI JSON data.
    - name_field (str): The name for the ABI.
    - subdomain_directory (str): Directory to save the ABI file.

    Returns:
    - str: Path to the saved ABI JSON file.
    """
    # Creating a filename based on the "name" field, ensuring uniqueness
    filename_base = name_field.replace(" ", "_")
    filename = filename_base + ".json"
    file_path = os.path.join(subdomain_directory, filename)
    unique_path = file_path
    os.path.join(subdomain_directory, f"{filename_base}.json")

    # Writing the ABI JSON to the file
    with open(unique_path, 'w') as file:
        json.dump(abi_json, file, indent=4)

    return unique_path


def repair_json(s):
    """
    Repairs a JSON-like string by adding necessary formatting.

    Parameters:
    - s (str): The JSON-like string to be repaired.

    Returns:
    - str: Repaired JSON-like string.
    """
    # Adding quotes around keys
    s = re.sub(r'(\b[a-zA-Z_]\w*\b)(?=\s*[:])', r'"\1"', s)
    # Replacing single quotes with double quotes
    s = s.replace("'", '"')
    # Escaping any unescaped backslashes
    s = s.replace("\\", "\\\\")
    # Replacing !0 with true and !1 with false
    s = s.replace('!0', 'true')
    s = s.replace('!1', 'false')
    return json.loads(s)


def find_literal_jsons(js_code):
    # Pattern to find JSON.parse calls with a basic JSON structure
    # This pattern assumes the JSON string is well-formed and doesn't contain nested objects
    # Adjust the pattern if your JSON strings can contain nested quotes or other complexities
    pattern = r'JSON.parse\(\'({.*?})\'\)'

    # Find all JSON strings within JSON.parse calls
    json_strings = re.findall(pattern, js_code)

    # Filter and extract JSONs that have the specified fields in the required order
    matching_jsons = []
    for json_str in json_strings:
        try:
            # Convert JSON string into a Python dictionary
            parsed_json = json.loads(json_str)

            # Check for the presence and order of 'version', 'name', 'bytecode'
            keys = list(parsed_json.keys())
            if ('version' in keys and 'name' in keys and 'bytecode' in keys and
                    keys.index('version') < keys.index('name') < keys.index('bytecode')):
                matching_jsons.append(parsed_json)

        except json.JSONDecodeError:
            # Handle cases where the JSON string is not well-formed
            print("Found a malformed JSON string.")
    return matching_jsons


def find_if_abi(js_code):
    main_abi_regex = re.compile(r'\{version:\s*(\w+),\s*name:\s*(\w+),\s*bytecode:\s*(\w+),\s*codeHash:\s*(\w+),\s*fieldsSig:\s*(\w+),\s*eventsSig:\s*(\w+),\s*functions:\s*(\w+),\s*constants:\s*(\w+),\s*enums:\s*(\w+)\s*')
    match = main_abi_regex.search(js_code)
    if not match:
        return None
    version_var, name_var, bytecode_var, codeHash_var, fieldsSig_var, eventsSig_var, functions_var, constants_var, enums_var = match.groups()
    return version_var, name_var, bytecode_var, codeHash_var, fieldsSig_var, eventsSig_var, functions_var, constants_var, enums_var


def extract_var_value(var_name, js_code):
    regex = re.compile(var_name + r'\s*=\s*([^;]+),', re.DOTALL)
    var_match = regex.search(js_code)

    output = None
    if var_match:
        output = var_match.group(1).strip().split('=')[0]
        output = output[0:output.rfind(',')]
    return output


def break_js_code_to_variables(js_code, groups):
    pieces = js_code.replace(' = ', '=').split('=')
    output = {}
    index = 0
    while index < len(pieces):
        s = pieces[index + 1]
        if ',' in s:
            if s.split(',')[1] in groups:
                s = s.split(',')[0]

        output[pieces[index]] = s
        index += 2
    return output


# Function to get JS URLs from the given URL
def get_js_urls(url):
    """
    Retrieves JavaScript URLs from the given web page URL.

    Parameters:
    - url (str): URL of the web page to retrieve JS URLs from.

    Returns:
    - List[str]: List of JavaScript URLs found in the web page.
    """
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    js_urls = [urljoin(url, script['src']) for script in soup.find_all('script') if
               'src' in script.attrs and ('index' in script['src'] or 'main' in script['src']) and script['src'].endswith('.js')]
    return js_urls


def find_abis(js_code, url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    subdomain_directory = create_export_directories(domain)
    consts = js_code.split("const ")
    files = find_literal_jsons(js_code)
    for file in files:
        name_field = file["name"]
        abi_json_path = export_abi_json(file, name_field, subdomain_directory)
        print(f"Saved file to: {abi_json_path}")
    for const in consts:
        groups = find_if_abi(const)
        if groups is not None:

            version_var, name_var, bytecode_var, codeHash_var, fieldsSig_var, eventsSig_var, functions_var, constants_var, enums_var = groups

            abi_components = {
                "version": json.loads(extract_var_value(version_var, const)),
                "name": json.loads(extract_var_value(name_var, const)),
                "bytecode": json.loads(extract_var_value(bytecode_var, const)),
                "codeHash": json.loads(extract_var_value(codeHash_var, const)),
                "fieldsSig": repair_json(extract_var_value(fieldsSig_var, const)),
                "eventsSig": repair_json(extract_var_value(eventsSig_var, const)),
                "functions": repair_json(extract_var_value(functions_var, const)),
                "constants": repair_json(extract_var_value(constants_var, const)),
                "enums": repair_json(extract_var_value(enums_var, const))
            }
            name_field = abi_components["name"]
            abi_json_path = export_abi_json(abi_components, name_field, subdomain_directory)
            print(f"Saved file to: {abi_json_path}")
            files.append(abi_components)

    return files


# Function to process JS URL and extract ABI JSONs
def process_js_url(js_url):
    """
    Processes a JavaScript URL to extract ABI JSONs.

    Parameters:
    - js_url (str): JavaScript URL to process.

    Returns:
    - List[str]: List of extracted ABI JSONs from the JavaScript.
    """
    # Send a request to get JS code
    response = requests.get(js_url)
    js_code = response.text

    find_abis(js_code, js_url)


# Main function to accept URL and process it
def main():
    """
    Main function to accept a URL from the user, process it, and extract ABI JSONs.
    The function prompts the user for a dApp URL, extracts JavaScript URLs, processes each JS URL,
    and extracts ABI JSONs from them.

    Returns:
    - None
    """
    url = input("Please enter the URL of the dApp to process: ")
    js_urls = get_js_urls(url)
    for js_url in js_urls:
        print(f"Processing JavaScript URL: {js_url}")
        process_js_url(js_url)


if __name__ == '__main__':
    asciiart = """

           ____ _____   ______      _                  _             
     /\   |  _ \_   _| |  ____|    | |                | |            
    /  \  | |_) || |   | |__  __  _| |_ _ __ __ _  ___| |_ ___  _ __ 
   / /\ \ |  _ < | |   |  __| \ \/ / __| '__/ _` |/ __| __/ _ \| '__|
  / ____ \| |_) || |_  | |____ >  <| |_| | | (_| | (__| || (_) | |   
 /_/    \_\____/_____| |______/_/\_\\__|_|  \__,_|\___|\__\___/|_|   

  ___        ___ _        _ _ ___ _  __ 
 | _ )_  _  / __| |___  _| | | __| |/ _|
 | _ \ || | \__ \ / / || | | | _|| |  _|
 |___/\_, | |___/_\_\\_,_|_|_|___|_|_|  
      |__/                              

    """

    print(asciiart)
    main()
