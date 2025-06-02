import tomllib
import logging
import os
from datetime import datetime
from typing import Optional

from src.servicenow import ServiceNowClient, ServiceNowIntegrationClient


class TicketTemplate:
    def __init__(self, template_path: str):
        self.template_path = template_path

        # Initialize attributes to represent the loaded data's structure
        self.assignment_group = None
        self.short_description = None
        self.description = None
        self.integration_helper = None
        self.schedule = {}  # Default to empty dict for the schedule
        self.attachments = []  # Default to empty list for the files

        self.validation_errors = []  # For storing validation messages

    def _create_via_integration_helper(self, sn_integration_client: ServiceNowIntegrationClient) -> Optional[dict]:
        """Creates a base RITM using the ServiceNowIntegrationClient."""
        logging.info(f"Attempting RITM creation via integration helper for template '{self.template_path}'.")
        
        ritm_data = sn_integration_client.create_requested_item(
            assignment_group=self.assignment_group,
            short_description="Scheduled ticket",
            description="Scheduled ticket"
        )
        
        if not ritm_data:
            logging.error(f"RITM creation via integration helper FAILED for template '{self.template_path}'.")
            return None
        
        sys_id = ritm_data.get("sys_id")
        ritm_number = ritm_data.get("number", "N/A")
        logging.info(f"Base RITM {ritm_number} (SysID: {sys_id}) created via integration helper for '{self.template_path}'.")
        return ritm_data

    def _create_via_api(self, sn_api_client: ServiceNowClient) -> Optional[dict]:
        """Creates a base RITM using the ServiceNow API client."""
        logging.info(f"Attempting RITM creation via primary API for template '{self.template_path}'.")

        ritm_data = sn_api_client.create_requested_item(
            assignment_group=self.assignment_group,
            short_description="Scheduled ticket",
            description="Scheduled ticket"
        )

        if not ritm_data:
            logging.error(f"RITM creation via primary API FAILED for template '{self.template_path}'.")
            return None

        sys_id = ritm_data.get("sys_id")
        ritm_number = ritm_data.get("number", "N/A")
        logging.info(f"Base RITM {ritm_number} (SysID: {sys_id}) created via primary API for '{self.template_path}'.")
        return ritm_data

    def _finalize_details(self, sn_api_client: ServiceNowClient, ticket_sys_id: str) -> None:
        """
        Updates the created RITM with short_description, description, and adds attachments using the API client.
        Returns True if all steps were attempted, False otherwise (though critical failures handled by client).
        """

        # --- Update with Short Description and Description ---
        payload = {
            "short_description": self.short_description,
            "description": self.description        }

        sn_api_client.update_ticket(
            table_name="sc_req_item", sys_id=ticket_sys_id, payload=payload
        )

        # --- Add Attachments ---
        if self.attachments:
            logging.info(f"Adding {len(self.attachments)} attachment(s).")
            for attachment_info in self.attachments:
                file_path = attachment_info.get("path")
                sn_api_client.add_attachment(
                    table_name="sc_req_item", sys_id=ticket_sys_id, file_path=file_path
                )


    def load(self) -> bool:
        """Loads the TOML template file and extracts the 'ticket' section."""

        try:
            with open(self.template_path, "rb") as f:
                template = tomllib.load(f)

            if "ticket" not in template:
                msg = f"'ticket' section not found in template {self.template_path}."
                logging.error(f"Error: {msg}")
                self.validation_errors.append(msg)
                return False

            ticket_data = template["ticket"]

            self.assignment_group = ticket_data.get("assignment_group")
            self.short_description = ticket_data.get("short_description")
            self.description = ticket_data.get("description")
            self.integration_helper = ticket_data.get("integration_helper")
            self.schedule = ticket_data.get("schedule", {})

            attachments_data = ticket_data.get("attachments", {})
            self.attachments = attachments_data.get("files", [])

            logging.debug(self.__dict__)
            return True

        except FileNotFoundError:
            logging.error(f"Error: Template file {self.template_path} not found.")
            self.validation_errors.append(f"File not found: {self.template_path}")
            return False

        except tomllib.TOMLDecodeError as e:
            logging.error(f"Error decoding TOML from {self.template_path}: {e}")
            self.validation_errors.append(f"TOML decode error: {e}")
            return False

        except Exception as e:
            logging.error(
                f"Unexpected error while loading template {self.template_path}: {e}"
            )
            self.validation_errors.append(f"Unexpected loading error: {e}")
            return False

    def validate_structure(self) -> bool:
        """Validates the structure and basic fields of the loaded template data.
        Returns True if the structure is valid, False otherwise.
        This method should be called after load() to ensure the template is loaded first.
        """

        current_errors = []

        # --- Validate top-level fields ---
        required_fields_map = {
            "short_description": self.short_description,
            "description": self.description,
            "assignment_group": self.assignment_group,
        }
        for field_name, field_value in required_fields_map.items():
            if field_value is None:
                current_errors.append(f"'{field_name}' is missing or null.")
            elif not isinstance(field_value, str):
                current_errors.append(
                    f"'{field_name}' must be a string (found: {type(field_value)})."
                )

        # --- Validate integration_helper field ---
        if self.integration_helper is not None and not isinstance(self.integration_helper, bool):
            current_errors.append(
                f"'integration_helper' must be a boolean when provided. Found type: {type(self.integration_helper)} for value: '{self.integration_helper}'."
            )

        # --- Validate 'schedule' ---
        if not self.schedule:
            current_errors.append("'schedule' dictionary is empty or was missing.")
        else:
            frequency = self.schedule.get("frequency")
            if frequency is None:
                current_errors.append("'frequency' is missing in [ticket.schedule].")
            else:
                allowed_frequencies = ["daily", "weekly", "monthly", "quarterly"]
                if frequency not in allowed_frequencies:
                    current_errors.append(
                        f"Invalid 'frequency' value '{frequency}'. Allowed: {allowed_frequencies}"
                    )

                if frequency == "weekly" and self.schedule.get("day_of_week") is None:
                    current_errors.append(
                        "'day_of_week' (integer) is missing for weekly frequency."
                    )
                elif (
                    frequency == "monthly" and self.schedule.get("day_of_month") is None
                ):
                    current_errors.append(
                        "'day_of_month' (integer) is missing for monthly frequency."
                    )
                elif frequency == "quarterly" and (
                    self.schedule.get("months") is None
                    or self.schedule.get("day_of_month") is None
                ):
                    current_errors.append(
                        "'months' (list of int) or 'day_of_month' (int) is missing for quarterly frequency."
                    )

        # --- Validate 'attachments' ---
        processed_attachments = []
        for index, file_item in enumerate(self.attachments):
            if not isinstance(file_item, dict):
                        current_errors.append(f"Attachment item at index {index} is not a dictionary.")
                        continue

            file_path = file_item.get("path")
            is_file_required = file_item.get("required")

            # Validate path and required 
            valid_file_path_str = isinstance(file_path, str) and file_path
            valid_is_file_required_bool = isinstance(is_file_required, bool)


            if file_path is None:
                current_errors.append(f"'path' is missing or null in attachment item at index {index}.")
            elif not valid_file_path_str:
                current_errors.append(f"'path' in attachment item at index {index} must be a non-empty string.")

            if is_file_required is None:
                current_errors.append(f"'required' is missing or null in attachment item at index {index}.")
            elif not valid_is_file_required_bool:
                current_errors.append(f"'required' in attachment item at index {index} must be a boolean (true/false).")


            # If basic structure of path/required is invalid for this item, skip
            # This item is structurally flawed
            if not (valid_file_path_str and valid_is_file_required_bool):
                continue

            file_exists = os.path.isfile(file_path)

            if is_file_required is True:
                if not file_exists:
                    current_errors.append(
                        f"Required attachment file '{file_path}' (item at index {index}) does not exist."
                    )
                else:
                    processed_attachments.append(file_item)
            else:
                if not file_exists:
                    logging.warning(
                        f"Optional attachment file '{file_path}' (item at index {index}) does not exist for template '{self.template_path}'. It will be skipped."
                    )
                else:
                    processed_attachments.append(file_item)

        self.attachments = processed_attachments

        # --- Finish ---
        if current_errors:
            self.validation_errors.extend(current_errors)
            for err in current_errors:
                logging.error(f"Validation error in {self.template_path}: {err}")
            return False

        logging.debug(
            f"Template structure validation successful for {self.template_path}."
        )
        return True

    def is_due(self, today: datetime) -> bool:
        """Checks if the loaded ticket template is due to be created today."""

        frequency = self.schedule.get("frequency")
        if frequency == "daily":
            return today.weekday() < 5  # Monday to Friday
        elif frequency == "weekly":
            day_of_week = self.schedule.get("day_of_week")
            return isinstance(day_of_week, int) and today.weekday() == day_of_week
        elif frequency == "monthly":
            day_of_month = self.schedule.get("day_of_month")
            return isinstance(day_of_month, int) and today.day == day_of_month
        elif frequency == "quarterly":
            months = self.schedule.get("months")
            day_of_month = self.schedule.get("day_of_month")
            return (
                isinstance(months, list)
                and isinstance(day_of_month, int)
                and today.month in months
                and today.day == day_of_month
            )
        return False

    def create_ticket(self, sn_api_client: ServiceNowClient, sn_integration_client: Optional[ServiceNowIntegrationClient] = None) -> bool:
        """
        Orchestrates the creation of a single scheduled ticket.
        Decides whether to use the integration helper or standard API for initial creation, then always uses the standard API for updates and attachments.
        Returns True if the ticket creation and finalization process was successfully initiated, False on critical creation failure.
        """
        ticket_base: Optional[dict] = None

        if self.integration_helper:
            if sn_integration_client:
                ticket_base = self._create_via_integration_helper(sn_integration_client)
            else:
                logging.error(
                    f"Template '{self.template_path}' requires an integration client (integration_helper is true), but no integration client is configured/available. Skipping ticket creation."
                )
                return False
        else:
            ticket_base = self._create_via_api(sn_api_client)

        if not ticket_base:
            return False

        ticket_sys_id = ticket_base.get("sys_id")
        return self._finalize_details(sn_api_client, ticket_sys_id)

