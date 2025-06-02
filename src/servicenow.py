import os
import mimetypes  # For guessing MIME type
import logging
import json
import requests
from requests.auth import HTTPBasicAuth


module_logger = logging.getLogger(__name__)


class ServiceNowClient:
    def __init__(self, url: str, username: str, password: str):
        """Initializes the ServiceNowClient for standard API interactions.

        The client sets up a requests session with HTTP Basic Authentication and
        default headers for JSON content type and acceptance.

        Args:
            url (str): The base URL of the ServiceNow instance (e.g., "https://instance.service-now.com").
                       The trailing slash will be removed if present.
            username (str): ServiceNow username for API authentication.
            password (str): ServiceNow password for API authentication.

        Raises:
            ValueError: If 'url', 'username', or 'password' are empty or not provided.
        """
        if not url:
            logging.error("ServiceNow instance URL cannot be empty.")
            raise ValueError("ServiceNow instance URL cannot be empty.")
        if not username or not password:
            logging.error("ServiceNow username and password cannot be empty.")
            raise ValueError("ServiceNow username and password cannot be empty.")

        self.username = username
        self.url = url.rstrip("/")
        self.api_path = "/api/now"  # Standard ServiceNow API path

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

        logging.info(f"ServiceNowClient initialized for instance: {self.url}")

    def _build_api_url(self, endpoint_segment: str) -> str:
        """Constructs the full URL for standard '/api/now' ServiceNow API endpoints.

        Args:
            endpoint_segment (str): The specific path segment to append to the
                                    base API path (e.g., "table/incident", "attachment").
                                    Leading slashes will be removed if present.

        Returns:
            str: The fully constructed API URL.
        """
        return f"{self.url}{self.api_path}/{endpoint_segment.lstrip('/')}"

    def _execute_http_request(
        self,
        method: str,
        request_url: str,
        params: dict = None,
        payload: dict = None,
        data=None,
        files=None,
        headers: dict = None,
    ) -> dict | None:
        """Executes an HTTP request and handles common responses and errors.

        This internal method forms the core of HTTP communication, managing
        request execution, status code checking (raising for HTTP errors),
        and basic parsing of JSON responses or handling of no-content responses.
        It's designed to be a shared utility for various API calls.

        Args:
            method (str): The HTTP method (e.g., "GET", "POST", "PUT", "DELETE").
            request_url (str): The complete URL for the HTTP request.
            params (Optional[Dict[str, Any]], optional): Dictionary of URL parameters
                to append to the request_url. Defaults to None.
            payload (Optional[Dict[str, Any]], optional): Dictionary to be sent as
                a JSON payload in the request body. Defaults to None.
            data (Optional[Any], optional): Data to be sent in the request body,
                typically for form-encoded data. Defaults to None.
            files (Optional[Dict[str, Any]], optional): Dictionary of 'filename': file-like-objects
                for multipart encoding upload. Defaults to None.
            headers (Optional[Dict[str, str]], optional): Dictionary of HTTP Headers to
                send with the request, potentially overriding session defaults.
                Defaults to None.

        Returns:
           self (Optional[Dict[str, Any]], optional): The JSON response parsed into a Python dictionary.
            For 204 (No Content) or other successful responses with no body,
            a dictionary with a "status" and "message" key is returned.
            Returns None if a request exception (HTTPError, ConnectionError, Timeout, etc.)
            occurs and is handled. Detailed error information is logged.
        """
        try:
            response = self.session.request(
                method=method,
                url=request_url,
                params=params,
                json=payload,
                data=data,
                headers=headers,
                files=files,
                timeout=30,
            )
            response.raise_for_status()
            if response.status_code == 204:
                return {
                    "status": "success",
                    "message": "Operation successful with no content returned.",
                }
            if not response.content:
                return {
                    "status": "success",
                    "message": f"Operation successful with status {response.status_code} and no content.",
                }
            return response.json()
        except requests.exceptions.HTTPError as errh:
            logging.error(f"HTTP Error: {errh}")
            if errh.response is not None:
                logging.error(f"Response Content: {errh.response.content}")
                try:
                    error_details = errh.response.json()
                    logging.error(f"Error Details: {error_details}")
                except json.JSONDecodeError:
                    logging.error(f"Error Response (non-JSON): {errh.response.text}")
        except requests.exceptions.ConnectionError as errc:
            logging.error(f"Connection Error: {errc}")
        except requests.exceptions.Timeout as errt:
            logging.error(f"Timeout Error: {errt}")
        except requests.exceptions.RequestException as err:
            logging.error(f"Request Exception: {err}")

        return None

    def _make_request(
        self,
        method: str,
        endpoint_segment: str,
        params: dict = None,
        payload: dict = None,
        data=None,
        files=None,
    ) -> dict | None:
        """Makes an HTTP request to a standard ServiceNow API endpoint (under /api/now).

        This method is a convenience wrapper around `_execute_http_request` that
        automatically constructs the full URL using `_build_api_url` for endpoints
        residing under the standard `/api/now` path.

        Args:
            method (str): The HTTP method (e.g., "GET", "POST").
            endpoint_segment (str): The API path segment relative to `/api/now`
                                    (e.g., "table/incident").
            params (Optional[Dict[str, Any]], optional): URL parameters. Defaults to None.
            payload (Optional[Dict[str, Any]], optional): JSON payload for the request body.
                Defaults to None.
            data (Optional[Any], optional): Data for form-encoded request body.
                Defaults to None.
            files (Optional[Dict[str, Any]], optional): Files for multipart upload.
                Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): The JSON response parsed into a Python dictionary,
            a success message dictionary, or None if an error occurred.
        """
        api_url = self._build_api_url(endpoint_segment)
        return self._execute_http_request(method, api_url, params, payload, data, files)

    def _get_record(
        self,
        table_name: str,
        sys_id: str = None,
        query: str = None,
        fields: list[str] = None,
        limit: int = None,
    ) -> dict | list | None:
        """Performs a GET request to the ServiceNow Table API to retrieve records.

        Fetches one or more records from a specified table. Records can be targeted
        by their unique `sys_id` or filtered using an encoded `query` string.
        This method interacts directly with the `/api/now/table/{table_name}` endpoint.

        Args:
            table_name (str): The name of the ServiceNow table to query (e.g., "incident").
            sys_id (Optional[str], optional): The sys_id of a specific record.
                If provided, 'query' is ignored. Defaults to None.
            query (Optional[str], optional): An encoded ServiceNow query string
                (e.g., "active=true^priority=1"). Used if 'sys_id' is not provided.
                Defaults to None.
            fields (Optional[List[str]], optional): A list of field names to include
                in the response (maps to 'sysparm_fields'). If None, all fields
                are returned by default by ServiceNow. Defaults to None.
            limit (Optional[int], optional): The maximum number of records to return
                (maps to 'sysparm_limit'). If None, ServiceNow's instance default
                is used. Defaults to None.

        Returns:
            self (Union[Dict[str, Any], List[Dict[str, Any]], None]):
            - If fetching by 'sys_id' and a single record is found, returns a
              dictionary representing that record (extracted from "result" if present,
              or the direct response if "result" is not the top-level key).
            - If fetching by 'query', returns a list of dictionaries, where each
              dictionary represents a found record (extracted from "result").
              Returns an empty list if the query is valid but yields no matches.
            - Returns None if an API error occurs (e.g., connection error,
              non-2xx status, invalid table name after error handling).

        Raises:
            ValueError: If 'table_name' is empty, or if neither 'sys_id' nor
                        'query' is provided.
        """
        if not table_name:
            logging.error("Table name is required for _get_record.")
            raise ValueError("Table name must be provided.")

        endpoint_segment = f"table/{table_name}"
        params_for_request = {}

        if sys_id:
            endpoint_segment += f"/{sys_id}"
        elif query:
            params_for_request["sysparm_query"] = query
        else:
            logging.error("Neither sys_id nor query provided for _get_record.")
            raise ValueError("Either sys_id or query must be provided to _get_record.")

        if fields:
            params_for_request["sysparm_fields"] = ",".join(fields)
        if limit is not None:
            params_for_request["sysparm_limit"] = limit

        response_data = self._make_request(
            "GET", endpoint_segment, params=params_for_request
        )

        if response_data:
            if sys_id and "result" not in response_data:  # Direct record for sys_id
                logging.debug(
                    f"Direct record data received for sys_id '{sys_id}' from '{table_name}'."
                )
                return response_data
            elif "result" in response_data:  # Queries
                logging.debug(
                    f"'result' found in response from '{table_name}'. Type: {type(response_data['result'])}"
                )
                return response_data["result"]
            else:
                logging.warning(
                    f"Response received for _get_record from '{endpoint_segment}' but structure is unexpected: {response_data}"
                )
                return response_data

        logging.debug(
            f"No data returned or error occurred in _get_record for '{endpoint_segment}' with params {params_for_request}"
        )
        return None

    def _find_record(
        self,
        table_name: str,
        sys_id: str = None,
        number: str = None,
        fields: list[str] = None,
    ) -> dict | None:
        """Finds a single record in a ServiceNow table by sys_id or 'number' field.

        This convenience method builds upon `_get_record` to retrieve exactly one
        record. It prioritizes lookup by `sys_id`. If `sys_id` is not provided,
        it queries for a record matching the `number` field, expecting a unique result
        (by requesting `limit=1`).

        Args:
            table_name (str): The name of the ServiceNow table (e.g., "incident").
            sys_id (Optional[str], optional): The sys_id of the record. Takes precedence
                over 'number'. Defaults to None.
            number (Optional[str], optional): The value of the 'number' field (or similar
                unique identifier field) to search for. Used only if 'sys_id'
                is not provided. Defaults to None.
            fields (Optional[List[str]], optional): A list of field names to retrieve.
                Defaults to None (all fields).

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the single record found,
            or None if no record is found or an API error occurred.

        Raises:
            ValueError: If 'table_name' is empty, or if neither 'sys_id' nor 'number'
                        is provided.
        """
        record_data = None

        if not sys_id and not number:
            logging.error("Either sys_id or number must be provided to _find_record.")
            raise ValueError(
                "Either sys_id or number must be provided to find a record."
            )

        if sys_id:
            logging.debug(f"Fetching record from '{table_name}' by sys_id: '{sys_id}'")
            record_data = self._get_record(
                table_name=table_name, sys_id=sys_id, fields=fields
            )
        else:
            logging.debug(f"Fetching record from '{table_name}' by number: '{number}'")
            query = f"number={number}"
            records_list = self._get_record(
                table_name=table_name, query=query, fields=fields, limit=1
            )
            if (
                records_list and isinstance(records_list, list) and records_list
            ):  # Check if list is not empty
                record_data = records_list[0]
            elif records_list and not isinstance(records_list, list):
                logging.warning(
                    f"Expected list from _get_record for number '{number}' in '{table_name}', received {type(records_list)}."
                )

        if record_data:
            logging.debug(f"Record found in '{table_name}'")
        else:
            logging.debug(f"No record found in '{table_name}'")

        return record_data

    def get_catalog_task(
        self, number: str = None, sys_id: str = None, fields: list[str] = None
    ) -> dict | None:
        """Retrieves a single Catalog Task (SCTASK) record from the 'sc_task' table.

        This method finds a specific catalog task by its unique 'number' field
        or its 'sys_id'. If both are provided, 'sys_id' takes precedence.

        Args:
            number (Optional[str], optional): The task number (e.g., "SCTASK0010001").
                Used if 'sys_id' is not provided. Defaults to None.
            sys_id (Optional[str], optional): The unique system ID of the catalog task.
                Takes precedence over 'number'. Defaults to None.
            fields (Optional[List[str]], optional): A list of field names to be
                returned for the catalog task. If None, all fields are returned.
                Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the catalog task record
            if found, otherwise None.
        """
        return self._find_record(
            table_name="sc_task", sys_id=sys_id, number=number, fields=fields
        )

    def get_organization(
        self, name: str = None, sys_id: str = None, extra_fields: list[str] = None
    ) -> dict | None:
        """Retrieves a single organization record from the 'u_organization' table.

        This method finds an organization by its 'name' or 'sys_id'. If both
        are provided, 'sys_id' takes precedence. Default fields 'sys_id' and 'name'
        are always fetched, and 'extra_fields' can be specified to retrieve more.

        Args:
            name (Optional[str], optional): The name of the organization.
                Used if 'sys_id' is not provided. Defaults to None.
            sys_id (Optional[str], optional): The unique system ID of the organization.
                Takes precedence over 'name'. Defaults to None.
            extra_fields (Optional[List[str]], optional): A list of additional field names
                to retrieve for the organization. Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the organization record
            if found, including default and any specified extra fields.
            Returns None if no matching organization is found or an error occurs.

        Raises:
            ValueError: If neither 'name' nor 'sys_id' is provided.
        """
        if not name and not sys_id:
            logging.error(
                "Either name or sys_id must be provided to get organization details."
            )
            raise ValueError(
                "Either name or sys_id must be provided to get organization details."
            )

        table_name = "u_organization"
        fields_to_fetch = {"sys_id", "name"}

        if extra_fields:
            fields_to_fetch.update(extra_fields)

        fields_list = list(fields_to_fetch)

        record_data = None
        if sys_id:
            logging.debug(
                f"Fetching organization from '{table_name}' by sys_id: '{sys_id}'"
            )
            record_data = self._get_record(
                table_name=table_name, sys_id=sys_id, fields=fields_list
            )
        else:
            logging.debug(
                f"Fetching organization from '{table_name}' by name: '{name}'"
            )
            query = f"name={name}"
            records_list = self._get_record(
                table_name=table_name, query=query, fields=fields_list, limit=1
            )
            if records_list and isinstance(records_list, list):
                record_data = records_list[0]
            elif records_list and not isinstance(records_list, list):
                logging.warning(
                    f"Expected list from _get_record for name '{name}' in '{table_name}', received {type(records_list)}. Data: {records_list}"
                )

        if record_data:
            team_info = {
                key: record_data.get(key)
                for key in fields_list
                if record_data.get(key) is not None
            }
            team_info.setdefault("sys_id", record_data.get("sys_id"))
            team_info.setdefault("name", record_data.get("name"))
            logging.debug(f"Team found in '{table_name}': {team_info}")
            return team_info
        else:
            logging.debug(f"No organization found in '{table_name}'")
            return None

    def create_incident(
        self,
        area: str,
        assignment_group: str,
        business_service: str,
        category: str,
        description: str,
        organization: str,
        service_group: str,
        short_description: str,
        subcategory: str,
        impact: int = 3,
        urgency: int = 3,
    ) -> dict | None:
        """Creates a new incident record in the ServiceNow 'incident' table.

        Args:
            short_description (str): A concise summary of the incident.
            description (str): A detailed description of the incident.
            assignment_group (str): The name or sys_id of the group to assign the incident to.
            category (str): The category of the incident.
            subcategory (str): The subcategory of the incident.
            organization (str): The identifier (e.g., name or sys_id) for the custom
                                'u_kot_organization' field.
            area (Optional[str], optional): Value for the custom 'u_area' field.
                                            Defaults to None.
            service_group (Optional[str], optional): Value for the custom 'u_service_group' field.
                                                     Defaults to None.
            business_service (Optional[str], optional): The name or sys_id of the related
                                                        business service. Defaults to None.
            impact (int, optional): The impact level of the incident (e.g., 1-High, 2-Medium, 3-Low).
                                    Defaults to 3 (Low).
            urgency (int, optional): The urgency level of the incident (e.g., 1-High, 2-Medium, 3-Low).
                                     Defaults to 3 (Low).
            caller_id (Optional[str], optional): The user ID (e.g., username or sys_id)
                                                 of the person reporting the incident.
                                                 Defaults to the client's authenticated username.
            requested_for (Optional[str], optional): The user ID (e.g., username or sys_id)
                                                     of the person affected by the incident.
                                                     Defaults to the client's authenticated username.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the created incident's data
            (extracted from the 'result' field of the response), or None if creation failed
            or the API response was unexpected.
        """
        endpoint_segment = f"table/incident"
        payload = {
            "caller_id": self.username,
            "contact_type": "Interface",
            "requested_for": self.username,
            "u_kot_organization": organization,
            "u_area": area,
            "u_service_group": service_group,
            "business_service": business_service,
            "category": category,
            "subcategory": subcategory,
            "assignment_group": assignment_group,
            "impact": impact,
            "urgency": urgency,
            "short_description": short_description,
            "description": description,
        }
        logging.info(f"Attempting to create incident")
        logging.debug(f"Payload: {payload}")

        response_data = self._make_request(
            method="POST", endpoint_segment=endpoint_segment, payload=payload
        )

        if (
            response_data
            and "result" in response_data
            and isinstance(response_data["result"], dict)
        ):
            created_record = response_data["result"]
            record_identifier = created_record.get(
                "sys_id", created_record.get("number", "N/A")
            )
            logging.info(
                f"Successfully created incident."
                f"Identifier (sys_id/number): {record_identifier}"
            )
            return created_record
        elif response_data:
            # The API call returned data, but not in the expected format.
            logging.warning(
                f"ServiceNow record creation in table 'incident' returned an unexpected response format. "
                f"Expected 'result' key with a dictionary. Response: {response_data}"
            )
            return None
        else:
            # _make_standard_request returned None, implying an issue handled within it
            # (HTTPError, ConnectionError, Timeout, or non-JSON response)
            logging.error(
                f"Failed to create ServiceNow record in table 'incident'. "
                "The API request did not yield expected data (likely an API or connection error)."
            )
            return None

    def create_requested_item(
        self,
        assignment_group: str,
        description: str,
        short_description: str,
        area: str = None,
        business_service: str = None,
        organization: str = None,
        subcategory: str = None,
        service_group: str = None,
        category: str = None
    ) -> dict | None:
        """Creates a new ritm record in the ServiceNow 'sc_req_item' table.

        Args:
            short_description (str): A concise summary of the ritm.
            description (str): A detailed description of the ritm.
            assignment_group (str): The name or sys_id of the group to assign the ritm to.
            category (str): The category of the ritm.
            subcategory (str): The subcategory of the ritm.
            organization (str): The identifier (e.g., name or sys_id) for the custom
                                'u_kot_organization' field.
            area (Optional[str], optional): Value for the custom 'u_area' field.
                                            Defaults to None.
            service_group (Optional[str], optional): Value for the custom 'u_service_group' field.
                                                     Defaults to None.
            business_service (Optional[str], optional): The name or sys_id of the related
                                                        business service. Defaults to None.
            caller_id (Optional[str], optional): The user ID (e.g., username or sys_id)
                                                 of the person reporting the ritm.
                                                 Defaults to the client's authenticated username.
            requested_for (Optional[str], optional): The user ID (e.g., username or sys_id)
                                                     of the person affected by the ritm.
                                                     Defaults to the client's authenticated username.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the created ritm's data
            (extracted from the 'result' field of the response), or None if creation failed
            or the API response was unexpected.
        """
        endpoint_segment = f"table/sc_req_item"
        payload = {
            "caller_id": self.username,
            "contact_type": "Interface",
            "requested_for": self.username,
            "u_kot_organization": organization,
            "u_area": area,
            "u_service_group": service_group,
            "business_service": business_service,
            "category": category,
            "subcategory": subcategory,
            "assignment_group": assignment_group,
            "short_description": short_description,
            "description": description,
        }
        logging.info(f"Attempting to create ritm")
        logging.debug(f"Payload: {payload}")

        response_data = self._make_request(
            method="POST", endpoint_segment=endpoint_segment, payload=payload
        )

        if (
            response_data
            and "result" in response_data
            and isinstance(response_data["result"], dict)
        ):
            created_record = response_data["result"]
            record_identifier = created_record.get(
                "sys_id", created_record.get("number", "N/A")
            )
            logging.info(
                f"Successfully created ritm."
                f"Identifier (sys_id/number): {record_identifier}"
            )
            return created_record
        elif response_data:
            logging.warning(
                f"ServiceNow record creation in table 'ritm' returned an unexpected response format. "
                f"Expected 'result' key with a dictionary. Response: {response_data}"
            )
            return None
        else:

            logging.error(
                f"Failed to create ServiceNow record in table 'sc_req_item'. "
                "The API request did not yield expected data (likely an API or connection error)."
            )
            return None

    def get_incident(
        self, number: str = None, sys_id: str = None, fields: list[str] = None
    ) -> dict | None:
        """Retrieves a single Incident record from the 'incident' table.

        This method finds a specific incident by its unique 'number' field
        (e.g., "INC0010001") or its 'sys_id'. If both are provided,
        'sys_id' takes precedence.

        Args:
            number (Optional[str], optional): The incident number. Used if 'sys_id'
                is not provided. Defaults to None.
            sys_id (Optional[str], optional): The unique system ID of the incident.
                Takes precedence over 'number'. Defaults to None.
            fields (Optional[List[str]], optional): A list of field names to be
                returned for the incident. If None, all fields are returned.
                Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the incident record
            if found, otherwise None.
        """
        return self._find_record(
            table_name="incident", sys_id=sys_id, number=number, fields=fields
        )

    def get_requested_item(
        self, number: str = None, sys_id: str = None, fields: list[str] = None
    ) -> dict | None:
        """Retrieves a single Requested Item (RITM) record from the 'sc_req_item' table.

        This method finds a specific RITM by its unique 'number' field
        (e.g., "RITM0010001") or its 'sys_id'. If both are provided,
        'sys_id' takes precedence.

        Args:
            number (Optional[str], optional): The RITM number. Used if 'sys_id'
                is not provided. Defaults to None.
            sys_id (Optional[str], optional): The unique system ID of the RITM.
                Takes precedence over 'number'. Defaults to None.
            fields (Optional[List[str]], optional): A list of field names to be
                returned for the RITM. If None, all fields are returned.
                Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the RITM record
            if found, otherwise None.
        """
        return self._find_record(
            table_name="sc_req_item", sys_id=sys_id, number=number, fields=fields
        )

    def get_service_request(
        self, number: str = None, sys_id: str = None, fields: list[str] = None
    ) -> dict | None:
        """Retrieves a single Service Request (REQ) record from the 'sc_request' table.

        This method finds a specific request by its unique 'number' field
        (e.g., "REQ0010001") or its 'sys_id'. If both are provided,
        'sys_id' takes precedence.

        Args:
            number (Optional[str], optional): The request number. Used if 'sys_id'
                is not provided. Defaults to None.
            sys_id (Optional[str], optional): The unique system ID of the request.
                Takes precedence over 'number'. Defaults to None.
            fields (Optional[List[str]], optional): A list of field names to be
                returned for the request. If None, all fields are returned.
                Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the request record
            if found, otherwise None.
        """
        return self._find_record(
            table_name="sc_request", sys_id=sys_id, number=number, fields=fields
        )

    def get_team(
        self, name: str = None, sys_id: str = None, extra_fields: list[str] = None
    ) -> dict | None:
        """Retrieves a single team (user group) record from the 'sys_user_group' table.

        This method finds a team by its 'name' or 'sys_id'. If both are provided,
        'sys_id' takes precedence. Default fields 'sys_id' and 'name' are always
        fetched, and 'extra_fields' can be specified to retrieve more.

        Args:
            name (Optional[str], optional): The name of the team (user group).
                Used if 'sys_id' is not provided. Defaults to None.
            sys_id (Optional[str], optional): The unique system ID of the team.
                Takes precedence over 'name'. Defaults to None.
            extra_fields (Optional[List[str]], optional): A list of additional field names
                to retrieve for the team. Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the team record
            if found, including default and any specified extra fields.
            Returns None if no matching team is found or an error occurs.

        Raises:
            ValueError: If neither 'name' nor 'sys_id' is provided.
        """
        if not name and not sys_id:
            logging.error("Either name or sys_id must be provided to get team details.")
            raise ValueError(
                "Either name or sys_id must be provided to get team details."
            )

        table_name = "sys_user_group"
        fields_to_fetch = {"sys_id", "name"}

        if extra_fields:
            fields_to_fetch.update(extra_fields)

        fields_list = list(fields_to_fetch)

        record_data = None
        if sys_id:
            logging.debug(f"Fetching team from '{table_name}' by sys_id: '{sys_id}'")
            record_data = self._get_record(
                table_name=table_name, sys_id=sys_id, fields=fields_list
            )
        else:
            logging.debug(f"Fetching team from '{table_name}' by name: '{name}'")
            query = f"name={name}"
            records_list = self._get_record(
                table_name=table_name, query=query, fields=fields_list, limit=1
            )
            if records_list and isinstance(records_list, list):
                record_data = records_list[0]
            elif records_list and not isinstance(records_list, list):
                logging.warning(
                    f"Expected list from _get_record for name '{name}' in '{table_name}', received {type(records_list)}. Data: {records_list}"
                )

        if record_data:
            team_info = {
                key: record_data.get(key)
                for key in fields_list
                if record_data.get(key) is not None
            }
            team_info.setdefault("sys_id", record_data.get("sys_id"))
            team_info.setdefault("name", record_data.get("name"))
            logging.debug(f"Team found in '{table_name}': {team_info}")
            return team_info
        else:
            logging.debug(f"No team found in '{table_name}'")
            return None

    def get_ticket_journal_entries(
        self, sys_id: str, order_by_desc: bool = True, limit: int = None
    ) -> list[dict] | None:
        """Retrieves journal entries (e.g., comments, work notes) for a specific ticket.

        This method queries the 'sys_journal_field' table for entries related to
        the provided ticket 'sys_id', specifically filtering for elements like
        'comments' and 'work_notes'.

        Args:
            sys_id (str): The sys_id of the parent ticket (e.g., Incident, RITM)
                          for which journal entries are to be retrieved.
            order_by_desc (bool, optional): If True, orders entries by their creation
                date in descending order (newest first). If False, orders in
                ascending order (oldest first). Defaults to True.
            limit (Optional[int], optional): The maximum number of journal entries to return.
                If None, ServiceNow's default limit applies. Defaults to None.

        Returns:
            self (Optional[List[Dict[str, Any]]], optional): A list of dictionaries, where each dictionary
            represents a journal entry. Returns an empty list if no matching journal
            entries are found for the ticket. Returns None if an API error occurs during
            the retrieval process.

        Raises:
            ValueError: If 'sys_id' is not provided or is empty.
        """
        if not sys_id:
            raise ValueError("Ticket sys_id must be provided.")

        query_parts = [f"element_id={sys_id}"]
        query_parts.append(f"elementINcomments,work_notes")  # comments, work_notes

        if order_by_desc:
            query_parts.append("ORDERBYDESCsys_created_on")
        else:
            query_parts.append("ORDERBYsys_created_on")

        final_query = "^".join(query_parts)

        fields_to_fetch = [
            "sys_id",
            "element_id",
            "element",
            "value",
            "sys_created_on",
            "sys_created_by",
            "name",  # 'name' is the table of the parent ticket
        ]

        logging.debug(
            f"Fetching journal entries for ticket sys_id '{sys_id}' using query: '{final_query}'"
        )

        journal_entries_result = self._get_record(
            table_name="sys_journal_field",
            query=final_query,
            fields=fields_to_fetch,
            limit=limit,
        )

        # _get_record with a query returns a list of records or None if an error occurred.
        # If no records are found by the query but the query itself was valid,
        if journal_entries_result is None:
            logging.error(f"Failed to retrieve journal entries for ticket '{sys_id}'.")
            return None

        # If journal_entries_result is an empty list, it means no entries matched.
        # If it's not a list at all (shouldn't happen if _get_record is consistent for queries), log warning.
        if not isinstance(journal_entries_result, list):
            logging.warning(
                f"Expected a list of journal entries from _get_record, but received type {type(journal_entries_result)}. Data: {journal_entries_result}"
            )
            return []

        if not journal_entries_result:  # Catches empty list
            logging.info(
                f"No journal entries found for ticket '{sys_id}' matching the criteria."
            )

        return journal_entries_result

    def update_ticket(self, table_name: str, sys_id: str, payload: dict) -> dict | None:
        """Updates an existing record (e.g., a ticket) in the specified ServiceNow table.

        Args:
            table_name (str): The ServiceNow table name where the record exists
                              (e.g., "incident", "sc_req_item").
            sys_id (str): The sys_id of the record to be updated.
            payload (Dict[str, Any]): A dictionary containing the fields and their new
                                      values to update on the record.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the updated record's state
            (typically contains all fields of the updated record as returned by ServiceNow).
            Returns None if the update fails, the record is not found, or an API error occurs.

        Raises:
            ValueError: If 'table_name', 'sys_id' is not provided or is empty,
                        or if 'payload' is empty or not a dictionary.
        """

        if not table_name:
            logging.error("Table name must be provided for updating a ticket.")
            raise ValueError("Table name must be provided for updating a ticket.")
        if not sys_id:
            logging.error("Sys ID must be provided for updating a ticket.")
            raise ValueError("Sys ID must be provided for updating a ticket.")

        logging.info(
            f"Attempting to update ticket in table '{table_name}', sys_id: '{sys_id}'."
        )
        logging.debug(f"Payload: {payload}")

        endpoint_segment = f"table/{table_name}/{sys_id}"
        response_data = self._make_request("PUT", endpoint_segment, payload=payload)

        if response_data and "result" in response_data:
            updated_record = response_data["result"]
            logging.info(
                f"Successfully updated ticket sys_id: {updated_record.get('sys_id')} in '{table_name}'."
            )
            return updated_record
        elif response_data:
            logging.warning(
                f"Update for ticket sys_id: {sys_id} in '{table_name}' returned an unexpected response structure: {response_data}"
            )
            return response_data  # Return what was received
        else:  # No response_data, weird
            logging.error(
                f"Failed to update ticket sys_id: {sys_id} in '{table_name}'. No valid response data from API call."
            )
            return None

    def add_attachment(
        self, table_name: str, sys_id: str, file_path: str, file_name: str = None
    ) -> dict | None:
        """Attaches a local file to a specified ServiceNow record using the Attachment API.

        Args:
            table_name (str): The name of the table the target record belongs to
                              (e.g., "incident", "sc_req_item").
            sys_id (str): The sys_id of the record to which the file will be attached.
            file_path (str): The local path to the file to be uploaded.
            file_name (Optional[str], optional): The desired name for the file once uploaded
                to ServiceNow. If None, the original file name from 'file_path'
                is used. Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary containing metadata of the successfully
            uploaded attachment (typically from the 'result' field of the API response).
            Returns None if the attachment upload fails or an error occurs.

        Raises:
            FileNotFoundError: If the file at 'file_path' does not exist or is not accessible.
            ValueError: If 'table_name' or 'sys_id' is not provided or is empty.
            IOError: If an error occurs while reading the file.
        """
        if not table_name or not sys_id:
            logging.error(
                "Table name and sys_id are required for adding an attachment."
            )
            raise ValueError("Table name and sys_id must be provided.")
        if not os.path.exists(file_path):
            logging.error(f"File not found at path for attachment: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        attachment_name = file_name if file_name else os.path.basename(file_path)

        logging.info(
            f"Attempting to attach file '{attachment_name}' from path '{file_path}' to record '{sys_id}' in table '{table_name}'."
        )

        attachment_api_url = f"{self.url}{self.api_path}/attachment/file"

        params = {
            "table_name": table_name,
            "table_sys_id": sys_id,
            "file_name": attachment_name,
        }

        # Determine the content type of the file
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = (
                "application/octet-stream"  # Default if type can't be guessed
            )

        # Prepare headers for this specific request
        # These will override session headers
        request_headers = self.session.headers.copy()  # Start with session headers
        request_headers["Content-Type"] = content_type
        request_headers["Accept"] = "application/json"

        response_data = None
        try:
            with open(file_path, "rb") as f_binary:
                file_content = f_binary.read()

            # Send raw file bytes in the 'data' parameter
            response_data = self._execute_http_request(
                method="POST",
                request_url=attachment_api_url,
                params=params,
                headers=request_headers,  # Pass the specific headers for this request
                data=file_content,  # Pass raw file content
            )
        except IOError as e:
            logging.error(f"IOError reading file for attachment {file_path}: {e}")
        except Exception as e:
            logging.error(
                f"Unexpected error preparing or sending attachment for {file_path}: {e}",
                exc_info=True,
            )

        if response_data:
            if isinstance(response_data, dict) and "result" in response_data:
                attachment_meta = response_data["result"]
                logging.info(
                    f"Successfully attached file. Attachment sys_id: {attachment_meta.get('sys_id') if isinstance(attachment_meta, dict) else 'N/A'}"
                )
                return attachment_meta
            else:
                # If the response is not as expected, log and return it
                logging.warning(
                    f"File attachment successful, but response format was unexpected: {response_data}"
                )
                return response_data
        else:
            logging.error(
                f"Failed to attach file '{attachment_name}' to {sys_id} in {table_name}."
            )
            return None
        

class ServiceNowIntegrationClient(ServiceNowClient):
    def __init__(
        self, url: str, username: str, password: str, integration_path: str
    ):
        """Initializes the ServiceNowIntegrationClient.

        Args:
            url (str): The base URL of the ServiceNow instance
                       (e.g., "https://instance.service-now.com").
            username (str): ServiceNow username for API authentication.
            password (str): ServiceNow password for API authentication.
            integration_base_path (str): The specific base path for this set of
                custom integrations, relative to the instance URL
                (e.g., "api/my_company/integration_helper_v1").
                Leading/trailing slashes will be removed.

        Raises:
            ValueError: If 'integration_base_path' is empty or not provided.
        """
        super().__init__(url, username, password)
        if not integration_path:
            raise ValueError(
                "Integration base path cannot be empty for ServiceNowIntegrationClient."
            )
        self.integration_base_path = integration_path.lstrip("/")
        self.integration_base_path = integration_path.rstrip("/")

    def _build_integration_url(self) -> str:
        """Constructs the full URL for the configured integration endpoint.

        This method combines the base instance URL with the specific
        `integration_base_path` defined for this client.

        Returns:
            str: The fully constructed URL for the integration endpoint.
        """
        return f"{self.url}/{self.integration_base_path}"

    def _make_integration_request(
        self, method: str, payload: dict = None
    ) -> dict | None:
        """Makes an HTTP request to the configured integration endpoint.

        This is a convenience method that uses the client's `integration_base_path`
        to target a specific custom integration endpoint. It leverages the
        `_execute_http_request` method from the parent `ServiceNowClient` for
        actual HTTP communication and error handling.

        Args:
            method (str): The HTTP method to use (e.g., "POST", "GET").
            payload (Optional[Dict[str, Any]], optional): A dictionary to be sent as
                the JSON payload in the request body. Defaults to None.
            params (Optional[Dict[str, Any]], optional): URL parameters for the request.
                Defaults to None.

        Returns:
            self (Optional[Dict[str, Any]], optional): The JSON response parsed into a Python dictionary,
            a success message dictionary, or None if an error occurred during the request.
        """
        integration_url = self._build_integration_url()
        return self._execute_http_request(
            method=method, request_url=integration_url, payload=payload
        )

    def create_requested_item(
        self,
        assignment_group: str = None,
        short_description: str = "Automated RITM Creation",
        description: str = "Base item created via integration helper.",
    ) -> dict | None:
        """Creates a Requested Item (RITM) using a specific custom integration endpoint.

        This method sends a POST request to the configured integration endpoint
        to initiate the creation of an RITM. The structure of the payload and
        the response (especially the path to the created RITM number) are
        dependent on the specific custom integration being called. After successful
        creation via the helper, it attempts to fetch the full RITM details using
        the standard API.

        Args:
            assignment_group (Optional[str], optional): Identifier for the assignment group.
                This example assumes the custom endpoint maps this to a 'requested_for'
                or similar field. Adjust as per your integration's needs. Defaults to None.
            summary (str, optional): A brief summary for the RITM.
                Defaults to "Automated RITM Creation".
            description (str, optional): A detailed description for the RITM.
                Defaults to "Base item created via integration helper.".
            extra_payload_fields (Optional[Dict[str, Any]], optional): Any additional
                key-value pairs to include in the root of the JSON payload sent to
                the integration endpoint. Defaults to None.


        Returns:
            self (Optional[Dict[str, Any]], optional): A dictionary representing the full details of the
            newly created Requested Item (RITM) if successful, fetched using its number.
            Returns None if the creation via the integration helper fails.
        """

        payload = {
            "requested_for": assignment_group,
            "summary": short_description,
            "description": description,
        }

        try:
            response = self._make_integration_request(method="POST", payload=payload)
        except Exception as e:
            logging.error(f"Error creating RITM via integration helper: {e}")
            return None

        if response and "result" in response:
            created_ritm = response["result"]["requestItemNumber"]
            logging.info(
                f"Successfully created RITM via integration helper. RITM number: {created_ritm}"
            )
            result = self.get_requested_item(number=created_ritm)
            return result
