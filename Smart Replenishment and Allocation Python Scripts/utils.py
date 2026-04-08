# utils.py

# This file contains reusable helper functions for the Smart Replenishment Agent.
# It is separated from the main agent class to promote code reusability and clarity.
# NOTE: This version is reconfigured for a Databricks environment and will not run locally.

import os
import io
import pandas as pd
from azure.storage.filedatalake import DataLakeServiceClient
from pyspark.sql import SparkSession
from pyspark.dbutils import DBUtils

# --- ADLS Configuration (from your original script) ---
STORAGE_ACCOUNT_NAME = 'datalakedev'
CONTAINER_NAME = 'raw'
STORAGE_ACCOUNT_KEY = 'XXXXX-XX'

def get_adl_file_content(file_path_in_adls):
    """
    Connects to Azure Data Lake Storage Gen2 and retrieves the content of a specified file.
    """
    try:
        adl_url = f"https://{STORAGE_ACCOUNT_NAME}.dfs.core.windows.net"
        service_client = DataLakeServiceClient(account_url=adl_url, credential=STORAGE_ACCOUNT_KEY)
        path_segments = file_path_in_adls.split(f"/{CONTAINER_NAME}/", 1)
        if len(path_segments) > 1:
            file_path_in_filesystem = path_segments[1]
        else:
            file_path_in_filesystem = file_path_in_adls.replace(f"https://{STORAGE_ACCOUNT_NAME}.dfs.core.windows.net/{CONTAINER_NAME}/", "")

        file_system_client = service_client.get_file_system_client(file_system=CONTAINER_NAME)
        file_client = file_system_client.get_file_client(file_path_in_filesystem)

        print(f"Attempting to download: adl://{CONTAINER_NAME}/{file_path_in_filesystem}")
        download = file_client.download_file()
        file_content = download.readall()
        return file_content
    except Exception as e:
        print(f"Error accessing file {file_path_in_adls} from ADLS: {e}")
        return None

def read_file_into_dataframe(file_path_in_adls, file_content):
    """
    Reads file content into a Pandas DataFrame based on file extension.
    """
    if file_content is None:
        return None
    file_extension = os.path.splitext(file_path_in_adls)[1].lower()
    df = None
    try:
        if file_extension == '.csv':
            df = pd.read_csv(io.StringIO(file_content.decode('utf-8')))
        else:
            print(f"Warning: Unsupported file type: {file_extension} for {file_path_in_adls}")
            return None
    except pd.errors.EmptyDataError:
        print(f"Warning: File {file_path_in_adls} is empty or has no columns.")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error reading {file_extension} content for {file_path_in_adls}: {e}")
        return None
    return df
