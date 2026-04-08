# Run Replenishment Check.py

# Databricks notebook source
# MAGIC %pip install openai databricks-sdk>=0.53.0 pandas azure-storage-blob azure-identity sendgrid httplib2

# COMMAND ----------

import os
import sys
from pyspark.sql import SparkSession
from pyspark.dbutils import DBUtils
from smart_replenishment_agent import SmartReplenishmentAgent # Import the new custom class

html_content = """
<h1 style="color: #0077B6; text-align: center; font-family: Arial, sans-serif;">
    Smart Replenishment and Allocation Agent
</h1>
<p style="color: #555555; text-align: center; font-family: Arial, sans-serif; font-size: 18px;">
    An AI-powered system for intelligent stock management.
</p>
"""

from IPython.display import display, HTML
display(HTML(html_content))

# COMMAND ----------

# IMPORTANT: Restart Python to ensure the new imports are available
dbutils.library.restartPython()

# COMMAND ----------

if __name__ == "__main__":
    # --- Configuration file path in Azure Data Lake Storage ---
    config_file_path = "abfss://raw@datalakedev.dfs.core.windows.net/raw/mnt/raw/Replenishment/replenishment_mapping.json"

    try:
        # Initialize the agent. It will load the config.json.
        agent = SmartReplenishmentAgent(config_path=config_file_path)

        if not agent.datasets_info:
            print("No datasets found in config.json to process. Exiting.")
        else:
            print(f"Found {len(agent.datasets_info)} datasets to process.")
            for dataset_config in agent.datasets_info:
                # Run the replenishment check for each configured dataset
                agent.run_replenishment_check(dataset_config)

    except Exception as e:
        print(f"\nAn error occurred during agent execution: {e}")
    finally:
        print("\n--- All replenishment checks finished ---")
        print("\nSmart Replenishment Agent execution finished.")
