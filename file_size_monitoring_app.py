import os
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Thread
import pyodbc
import re
import logging 

# Imports for Azure Key Vault
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# === SQL SERVER CONNECTION DETAILS ===

#TARGET_FILE_DETAILS
SQL_SERVER_NAME = "az-23242517.database.windows.net"
SQL_DATABASE_NAME = "Managed_DBA"
SQL_TABLE_NAME = "[Assurance].[DataCheckResults]"
# --- ADDED: Stored Procedure Name ---
SQL_SP_NAME = "[Assurance].[DataCheckResults_Merge_SP]"

# === CONFIGURATION ===
KEY_VAULT_URL = "https://InfKeyVault-KC-Dev.vault.azure.net/"
SQL_PASSWORD_SECRET_NAME = "XXXX-XXX"
CHECK_INTERVAL = 10
STABLE_CHECKS = 5

# Configure basic logging
# --- Log file path set to c:\temp\file_size_monitor.log ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='c:\\temp\\file_size_monitor.log', # <-- Log file name with absolute path
    filemode='a'                     
)

def fetch_watch_folders():
    """Dynamically fetches folders to watch from the SQL database."""
    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SQL_SERVER_NAME};"
        f"DATABASE={SQL_DATABASE_NAME};"
        f"Authentication=ActiveDirectoryIntegrated;"
    )

    folders = []
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        cursor.execute("SELECT ParameterValue FROM [Data_Assurance].[ParameterValue] WHERE ParameterValueKey = 87")
        rows = cursor.fetchall()
       
        folders = [row.ParameterValue.strip() for row in rows if row.ParameterValue]
        # --- END FIX ---
        print("Folders fetched from DB:", folders)
        conn.close()
    except Exception as ex:
        print(f"[SQL Error] Could not fetch watch folders: {ex}")
        logging.info(f"ERROR: Could not fetch watch folders: {ex}") # <-- MODIFIED TO logging.info
    return folders

WATCH_FOLDERS = fetch_watch_folders()

def get_secret_from_key_vault(secret_name, key_vault_url=KEY_VAULT_URL):
    """Retrieve a secret value from Azure Key Vault."""
    try:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True, exclude_cli_credential=True)
        client = SecretClient(vault_url=key_vault_url, credential=credential)
        print(f"[Azure] Retrieving secret '{secret_name}' from Key Vault '{key_vault_url}'...")
        secret = client.get_secret(secret_name)
        return secret.value
    except Exception as ex:
        print(f"[Azure Error] Failed to retrieve secret from Key Vault: {ex}")
        logging.info(f"ERROR: Failed to retrieve secret from Key Vault: {ex}") # <-- MODIFIED TO logging.info
        return None
    
#change the table to the dev table
#add another logic line to handle k+ filename

def standardize_filename(file_name: str) -> str:
    """
    Standardizes a filename by replacing various date and numeric patterns.
    
    Args:
        file_name (str): The original filename string.

    Returns:
        str: The new dynamic filename.
    """
    base, ext = os.path.splitext(file_name)
    processed_base = base
    
    # Check for the specific 'K' file format first 
    pattern_k_file = re.compile(r'^K\d+\.\d{8}T\d{6}\+\d{4}$')
    if pattern_k_file.match(processed_base):
        # Replace the number after 'K' with '*'
        processed_base = re.sub(r'K\d+\.', 'K*.', processed_base)
        # Replace the timestamp with '*'
        processed_base = re.sub(r'\d{8}T\d{6}\+\d{4}', '*', processed_base)
        
    # --- Updated logic for generic patterns ---
    
    # 1. Full T-timestamp (e.g., 20250905T000000+0000)
    elif re.search(r'\d{8}T\d{6}\+\d{4}', processed_base):
        processed_base = re.sub(r'\d{8}T\d{6}\+\d{4}', '*', processed_base)
    
    # 2. Specific date formats with separators (e.g., 2025-09-02, 27_08_23)
    elif re.search(r'(\d+[-_]\d+[-_]\d+)', processed_base):
        processed_base = re.sub(r'(\d+[-_]\d+[-_]\d+)', '*', processed_base)
    
    # 3. Pattern: <anyname>_<8digits|10digits> 
    elif re.search(r'^[a-zA-Z0-9_]+_(?:\d{8}|\d{10})$', processed_base):
        processed_base = re.sub(r'_(\d{8}|\d{10})$', '_*', processed_base)
    
    # 4. Pattern: <anyname>_<8digits>_<2digits> 
    elif re.search(r'^[a-zA-Z0-9_]+_\d{8}_\d{2}$', processed_base):
        processed_base = re.sub(r'_\d{8}_\d{2}', '_*_*', processed_base)
    
    # 5. Pattern: <anyname>-<8digits> (e.g., STL-AFP-20250906)
    elif re.search(r'^[a-zA-Z0-9-]+-\d{8}$', processed_base):
        processed_base = re.sub(r'-(\d{8})$', '-*', processed_base)
    
    elif re.search(r'^[a-zA-Z0-9-]+-\d{8}\.\d{2}\.\d{3}$', processed_base):
        processed_base = re.sub(r'-\d{8}\.\d{2}\.\d{3}', '-*.*.*', processed_base)
    
    elif re.search(r'^[a-zA-Z0-9_]+_\d{14}_\d{14}_([OD])_\d{2}$', processed_base):
        processed_base = re.sub(r'_\d{14}_\d{14}_([OD])_\d{2}', r'_*_*_\1_*', processed_base)
    
    elif re.search(r'^[a-zA-Z0-9_\.]+[a-zA-Z0-9]\.\d{8}$', processed_base):
        processed_base = re.sub(r'\.(\d{8})$', '.*', processed_base)
    
    elif re.search(r'^[a-zA-Z0-9_]+_\d{8}_\d{14}_complete$', processed_base):
        processed_base = re.sub(r'_\d{8}_\d{14}_complete', '_*_*_complete', processed_base)
    
    patterns_fixed_len = [
        re.compile(r'\d{16}'),
        re.compile(r'\d{14}'),
        re.compile(r'\d{12}'),
        re.compile(r'\d{8}')
    ]
    for pattern in patterns_fixed_len:
        if pattern.search(processed_base):
            processed_base = pattern.sub('*', processed_base)
            
    # 11. As a final step, handle any remaining standalone numbers preceded by a separator
        elif re.search(r'[._-]\d+', processed_base):
            processed_base = re.sub(r'[._-]\d+', '*', processed_base)

    return processed_base + ext


def record_metadata_to_sql(filepath, size, ParameterValue):
    """
    Connects to SQL Server and calls a Stored Procedure to perform the MERGE operation.
    """
    file_name = os.path.basename(filepath)
    folder_path = os.path.dirname(filepath)
    size_str = str(size)
    
    # Create the standardized filename, which is used for the CheckComment
    standardized_file_name = standardize_filename(file_name)
    
    full_folder_path = os.path.join(folder_path, standardized_file_name)
    
    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SQL_SERVER_NAME};"
        f"DATABASE={SQL_DATABASE_NAME};"
        f"Authentication=ActiveDirectoryIntegrated;"
    )

    conn = None
    try:
        print(f"[SQL] Attempting to connect to {SQL_SERVER_NAME} using token authentication...")
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        # --- MODIFIED: Call the Stored Procedure instead of inline MERGE ---
        # The stored procedure requires 4 parameters
        sql_sp_call = f"EXEC {SQL_SP_NAME} ?, ?, ?, ?"

        # Parameters for the stored procedure: CheckHeaderKey, PlanCode, CheckComment, CheckValue
        params = ('73', 'python_filesize_monitor', full_folder_path, size_str)
        
        cursor.execute(sql_sp_call, *params)
        conn.commit()

        print(f"[SQL] Successfully processed: '{file_name}' ({size_str} bytes) in {SQL_TABLE_NAME}")

    except pyodbc.Error as ex:
        print(f"[SQL Error] An error occurred: {ex}")
        logging.info(f"ERROR: SQL SP call error for file '{file_name}': {ex}") # <-- MODIFIED TO logging.info
    finally:
        if conn:
            conn.close()

# Scan all folders in WATCH_FOLDERS and log file entries into SQL
def initial_scan_all_folders(folders):
    for folder_path in folders:
        print(f"[Scanning] Initial scan of existing files in {folder_path}...")
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(filepath)
                    record_metadata_to_sql(filepath, size, folder_path)
                    print(f"  - Found: {os.path.basename(filepath)} ({size} bytes) in {os.path.dirname(filepath)}")
                except FileNotFoundError:
                    print(f"[Warning] File not found during scan: {filepath}")
                    logging.info(f"WARNING: File not found during initial scan: {filepath}") # <-- MODIFIED TO logging.info
        print("[Scanning] Initial scan complete.")
    print(f"[Summary] Initial scan completed for all {len(folders)} watch_folder_base folders.")

# === FILE MONITOR HANDLER ===
class FileMonitorHandler(FileSystemEventHandler):
    """Handles file system events (like file creation)."""
    def on_created(self, event):
        if event.is_directory:
            return
        
        print(f"[Detected] File created: {event.src_path}")
        Thread(target=self.monitor_file, args=(event.src_path,), daemon=True).start()

    def monitor_file(self, filepath):
        """Continuously checks a file's size until it becomes stable."""
        stable_count = 0
        last_size = -1
        print(f"[Monitoring] {filepath}")
        
        while True:
            try:
                current_size = os.path.getsize(filepath)
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= STABLE_CHECKS:
                        print(f"[✅ Complete] {filepath} ({current_size} bytes)")
                        watch_folder_base = self.get_watch_folder_base(filepath)
                        record_metadata_to_sql(filepath, current_size, watch_folder_base)
                        return
                else:
                    stable_count = 0
                    last_size = current_size
            except FileNotFoundError:
                print(f"[Warning] File not found: {filepath}")
                logging.info(f"WARNING: File not found during monitoring: {filepath}") # <-- MODIFIED TO logging.info
                return
            
            time.sleep(CHECK_INTERVAL)

    def get_watch_folder_base(self, filepath):
        for base in WATCH_FOLDERS:
            if filepath.startswith(base):
                return base
        return ''

# === START THE MONITORING OBSERVER ===
def start_monitoring():
    """Initializes and starts the observer to watch the specified folders."""
    observers = []
    initial_scan_all_folders(WATCH_FOLDERS)

    for folder in WATCH_FOLDERS:
        if not os.path.exists(folder):
            print(f"[Error] Folder not found: {folder}")
            logging.info(f"ERROR: Folder not found: {folder}") # <-- MODIFIED TO logging.info
            continue

        handler = FileMonitorHandler()
        observer = Observer()
        observer.schedule(handler, path=folder, recursive=True)
        observer.start()
        observers.append(observer)
        print(f"[Started] Watching: {folder}")

    if not observers:
        print("[Error] No valid folders to watch. Please check the network paths.")
        logging.info("ERROR: No valid folders to watch. Please check the network paths.") # <-- MODIFIED TO logging.info
        return

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Stopping] File monitoring...")
        for obs in observers:
            obs.stop()
        for obs in observers:
            obs.join()
    print("[Stopped] All watchers stopped.")

if __name__ == "__main__":
    start_monitoring()