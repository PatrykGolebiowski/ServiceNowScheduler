import logging
import tomllib
import glob
import os
import sys
from datetime import datetime
from typing import Optional

from src.servicenow import ServiceNowClient, ServiceNowIntegrationClient
from src.template import TicketTemplate


# --- Default Log Config (if config.toml is missing or incomplete) ---
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILENAME_TEMPLATE = "app_%Y_%m_%d.log"


def setup_logging(log_config: dict):
    """
    Configures logging with separate formats for file and console.
    File logs will be detailed, while console logs will show only the message.
    """
    log_level_str = log_config.get("level", DEFAULT_LOG_LEVEL).upper()
    log_dir = log_config.get("dir", DEFAULT_LOG_DIR)
    filename_template = log_config.get("filename_template", DEFAULT_LOG_FILENAME_TEMPLATE)

    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    numeric_log_level = level_map.get(log_level_str, logging.INFO)

    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
    except OSError as e:
        print(f"Warning: Could not create log directory {log_dir}: {e}. Logging to current directory.")
        log_dir = "."

    # Format the filename with the current date
    log_filename = datetime.now().strftime(filename_template)
    log_file_path = os.path.join(log_dir, log_filename)

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_log_level)

    # Remove any existing handlers from the root logger to avoid duplicate messages
    if root_logger.hasHandlers():
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

    # --- Configure File Handler (detailed logging) ---
    file_handler = logging.FileHandler(log_file_path)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # --- Configure Console Handler (message only) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    logging.info(f"Logging configured. Level: {log_level_str}. Log file: {log_file_path}")


def load_app_config(config_path="config.toml"):
    app_config = None

    try:
        with open(config_path, "rb") as f:
            app_config = tomllib.load(f)

        if "log" not in app_config:
            print(f"WARNING: Log configuration ('log' section) not found in {config_path} - Using default logging settings.")

        if "templates" not in app_config:
            print(f"ERROR: Templates configuration ('templates' section) not found in {config_path} - Exiting.")
            sys.exit(1)
        if "servicenow" not in app_config:
            print(f"ERROR: ServiceNow configuration ('servicenow' section) not found in {config_path} - Exiting.")
            sys.exit(1)

    except FileNotFoundError:
        print(f"ERROR: Configuration file {config_path} not found - Exiting.")
        sys.exit(1)
    except tomllib.TOMLDecodeError as e:
        print(f"ERROR: Error decoding TOML from {config_path}: {e} - Exiting.")
        sys.exit(1)
    except Exception as e:  # Catch any other unexpected errors during loading
        print(f"ERROR: An unexpected error occurred while loading configuration from {config_path}: {e} - Exiting.")
        sys.exit(1)

    return app_config


def main():
    # --- Get ServiceNow credentials from environment variables ---
    sn_api_user = os.environ.get("SN_API_USER")
    sn_api_pass = os.environ.get("SN_API_PASSWORD")

    if not sn_api_user or not sn_api_pass:
        print("ERROR: SN_API_USER or SN_API_PASSWORD environment variables not set. Exiting.")
        sys.exit(1)
    
    # --- Get ServiceNow integration credentials from environment variables ---
    sn_integration_user = os.environ.get("SN_INTEGRATION_USER")
    sn_integration_pass = os.environ.get("SN_INTEGRATION_PASSWORD")

    if not sn_integration_user or not sn_integration_pass:
        print("WARNING: SN_INTEGRATION_USER or SN_INTEGRATION_PASSWORD not set. The ServiceNow integration will use the primary API credentials (SN_API_USER/SN_API_PASSWORD) as a fallback.")
        sn_integration_user = sn_api_user
        sn_integration_pass = sn_api_pass

    # --- Load application configuration ---
    config = load_app_config("config.toml")
    sn_config = config.get("servicenow", {})
    templates_config = config.get("templates", {})

    setup_logging(config.get("log", {}))
    templates = glob.glob(templates_config.get("path"))
    logging.debug(f"Found templates: {templates}")

    today = datetime.now()
    logging.debug(f"Today's date: {today}.")

    # --- ServiceNow clients ---
    try:
        sn_client = ServiceNowClient(
            url=sn_config.get("instance_url"),
            username=sn_api_user,
            password=sn_api_pass,
        )
    except Exception as e:
        logging.error(f"Error initializing ServiceNow client: {e}")
        sys.exit(1)
    
    sn_integration_client = None 
    if sn_config.get("integration_url", "").strip():
        try:
            sn_integration_client = ServiceNowIntegrationClient(
                url=sn_config.get("instance_url"),
                integration_path=sn_config.get("integration_url"),
                username=sn_integration_user,
                password=sn_integration_pass,
            )
        except Exception as e:
            logging.error(f"Error initializing ServiceNow integration client: {e}")
            return

    # --- Process each template file ---
    for file in templates:
        logging.debug(f"Processing template: {file}")
        template = TicketTemplate(template_path=file)
        if not template.load():
            continue

        if template.validate_structure():
            if template.is_due(today):
                logging.info(f"Creating ticket based on template {file}.")
                template.create_ticket(sn_api_client=sn_client, sn_integration_client=sn_integration_client)
            else:
                logging.debug(f"Schedule conditions not met for template. No ticket created.")


if __name__ == "__main__":
    main()
