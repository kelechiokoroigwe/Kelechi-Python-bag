# smart_replenishment_agent.py

# This file contains the main SmartReplenishmentAgent class.
# This version is reconfigured to work with Azure Data Lake Storage (ADLS).
# NOTE: This script is designed for a Databricks environment and will not run locally.

try:
    from openai import OpenAI
except ModuleNotFoundError:
    print("Warning: 'openai' module is not installed. Please install it to enable AI functionalities.")

import os
import json
import re
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from pyspark.sql import SparkSession
from pyspark.dbutils import DBUtils
from utils import get_adl_file_content

# --- Azure Configuration --- (Ensure these are correctly set or fetched securely)
scope_name = 'InfKeyVault-Dev'
secret_key = 'SendGridAPIKey'
STORAGE_ACCOUNT_NAME = 'datalakedev'
CONTAINER_NAME = 'raw'
STORAGE_ACCOUNT_KEY = 'XXXXXXXXX'

# Assuming these are set up correctly in the Databricks notebook environment
spark = SparkSession.builder.appName('Smart_Replenishment_Agent').getOrCreate()
dbutils = DBUtils(spark)

class SmartReplenishmentAgent:
    def __init__(self, config_path: str):
        self.dbutils = dbutils
        self.databricks_token = self.dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
        self.send_grid_api_key = self.dbutils.secrets.get(scope=scope_name, key=secret_key)
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.datasets_info = self.config.get("datasets", [])
        if not self.datasets_info:
            print("Warning: 'datasets' list not found or is empty in the config file.")

    def _load_config(self, config_file_path: str) -> dict:
        """Loads the configuration from the specified ADLS JSON file."""
        print(f"Loading config from ADLS: {config_file_path}")
        json_content = get_adl_file_content(config_file_path)
        if json_content:
            try:
                config_data = json.loads(json_content)
                if not isinstance(config_data, dict):
                    raise ValueError("Config file content is not a JSON dictionary as expected.")
                print("Successfully loaded config.json from ADLS.")
                return config_data
            except json.JSONDecodeError as e:
                print(f"Error decoding config JSON from ADLS: {e}")
                raise
        else:
            raise FileNotFoundError(f"Could not retrieve content for config file from ADLS: {config_file_path}")

    def _send_email(self, subject, body, recipient_email):
        """Sends an email notification."""
        if not recipient_email:
            print("Warning: No recipient email specified for notification.")
            return

        print(f"\n--- Sending Email to {recipient_email} ---")
        message = Mail(
            from_email='Kcnwamaryxx@gmail.com',
            to_emails=recipient_email,
            subject=subject,
            html_content=body
        )
        try:
            sg = SendGridAPIClient(self.send_grid_api_key)
            response = sg.send(message)
            print(f"Email sent. Status Code: {response.status_code}")
        except Exception as e:
            print(f"Error sending email: {e}")

    def get_stock_report_with_ai(self, inventory_data: str) -> str:
        """
        Uses an LLM agent to analyze inventory data and generate a stock report.
        """
        client = OpenAI(
            api_key=self.databricks_token,
            base_url="https://adb-669.azuredatabricks.net/serving-endpoints"
        )
        
        system_prompt = """
        You are an intelligent inventory management agent. Your task is to analyze raw inventory data
        from a CSV file. Identify products where the 'current_stock' is at or below the 'reorder_point'.
        For each such product, generate a detailed replenishment report in JSON format. The report
        should contain all relevant information for a manager to take action.
        
        The JSON structure should be:
        {
            "replenishment_actions": [
                {
                    "product_id": "SKU123",
                    "product_name": "Product Name",
                    "store_id": "Store1",
                    "current_stock": 5,
                    "reorder_point": 10,
                    "breach_type": "ReplenishmentNeeded",
                    "recommendation": "Based on sales history, recommend placing a replenishment order for 20 units."
                },
                // ... more products
            ]
        }
        
        If no breaches are found, return an empty list: `{"replenishment_actions": []}`.
        Do not include any additional text or commentary outside the JSON block.
        """
        
        user_prompt_content = f"""
        Analyze the following inventory data and identify any products that need replenishment.
        Only consider products where the 'current_stock' is less than or equal to the 'reorder_point'.
        
        Inventory Data:
        ```csv
        {inventory_data}
        ```
        """
        try:
            response = client.chat.completions.create(
                model="databricks-claude-3-7-sonnet",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt_content}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error during LLM call for stock analysis: {e}")
            return json.dumps({"replenishment_actions": [], "error": str(e)})

    def run_replenishment_check(self, dataset_config: dict):
        """
        Main function to orchestrate the replenishment check for a single dataset.
        """
        dataset_name = dataset_config.get("dataset_name")
        inventory_file_url = dataset_config.get("inventory_file_location")
        email_recipient = dataset_config.get("alert_email") or self.config.get("email_recipient")
        
        if not (dataset_name and inventory_file_url):
            print(f"Skipping dataset '{dataset_name}' due to missing file location or name.")
            return

        print(f"\nProcessing smart replenishment check for: {dataset_name}")
        
        # 1. Get inventory data from ADLS
        inventory_content_bytes = get_adl_file_content(inventory_file_url)
        if not inventory_content_bytes:
            print(f"Could not read inventory file from {inventory_file_url}. Exiting.")
            return
        
        inventory_content_str = inventory_content_bytes.decode('utf-8')
        
        # 2. Use LLM to analyze data and generate a report
        llm_response = self.get_stock_report_with_ai(inventory_content_str)
        
        # 3. Parse the LLM's JSON response
        try:
            # Use regex to find the JSON block and parse it
            json_match = re.search(r"\{.*\}", llm_response, re.DOTALL)
            if json_match:
                replenishment_report = json.loads(json_match.group(0))
            else:
                raise ValueError("LLM response did not contain a valid JSON object.")
                
            replenishment_actions = replenishment_report.get("replenishment_actions", [])

            # 4. Take action based on the report
            if replenishment_actions:
                print(f"--- Replenishment needed for {len(replenishment_actions)} products. ---")
                email_subject = f"Urgent Stock Alert for {dataset_name}"
                email_body = f"""
                <h1 style="color:#FF4500;">Urgent Stock Replenishment Required</h1>
                <p>The following products have breached their reorder points and require your immediate attention:</p>
                <pre>{json.dumps(replenishment_actions, indent=2)}</pre>
                <p>Please review the details and initiate replenishment actions.</p>
                """
                self._send_email(email_subject, email_body, email_recipient)
            else:
                print(f"--- No replenishment actions needed for {dataset_name}. Stock levels are healthy. ---")
                # Optional: Send a success email or just log the result
                email_subject = f"Smart Replenishment Check Successful: {dataset_name}"
                email_body = f"The automated stock check for {dataset_name} completed successfully. No stock breaches were detected."
                self._send_email(email_subject, email_body, email_recipient)

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing LLM response JSON: {e}")
            email_subject = f"Smart Replenishment Check Failed: {dataset_name}"
            email_body = f"An error occurred while processing the smart replenishment check for {dataset_name}: {e}"
            self._send_email(email_subject, email_body, email_recipient)
