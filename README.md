# ServiceNow ticket scheduler

# General description
This application automates the creation of scheduled tickets (specifically Requested Items - RITMs) in a ServiceNow instance. It uses a template-driven approach, where ticket structures and their schedules are defined in TOML configuration files. The application reads these templates, checks if a ticket is due based on its schedule (daily, weekly, monthly, quarterly), and then creates the corresponding ticket in ServiceNow via its API.

# Purpose
The primary purpose of this project is to:
- **Automate tasks:** Reduce manual effort in creating recurring ServiceNow tickets for routine checks, reporting, or other scheduled activities.
- **Ensure consistency:** Use predefined templates to ensure that all scheduled tickets are created with accurate and consistent information.
- **Improve reliability:** Minimize the risk of missed schedules or human error associated with manual ticket creation.
- **Provide flexibility:** Allow to easily define various details and complex schedules through simple TOML configuration files.

# Features
- **Template-driven:** Define ticket parameters (description, assignment group, etc.) in easy-to-manage TOML files.
- **Flexible scheduling:** Supports daily (weekdays), weekly, monthly, and quarterly ticket creation schedules.
- **Attachment support:** Automatically attach specified files to created tickets.
- **Configurable logging:** Detailed logging for monitoring and troubleshooting.
- **Secure credential management:** Uses environment variables for ServiceNow API credentials.
- **Modern project setup:** Recommends `uv` for fast dependency and virtual environment management.

# Prerequisites
**1. Software & Tools:**
- **Python:** Version 3.12 or higher.
- **`uv` (Recommended):** For efficient Python environment and package management. (Installation: [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv))

**2. ServiceNow Environment:**
- **Instance access:** Access to a ServiceNow instance (developer, test, or production) with the REST API enabled for managing Requested Items (`sc_req_item`) and attachments.

**3. ServiceNow user credentials:**
*A ServiceNow user account (or accounts) will need the following **core permissions** via the REST API:*
- Create and update Requested Items (`sc_req_item`).
- Add attachments to Requested Items.
- Access any custom integration helper endpoints (if these features are utilized by the tool).

-  **API user (Required):**
    - Credentials (username/password) possessing the **core permissions** for standard API operations.
- **Integration API user (Optional):**
    - Separate credentials (username/password) possessing the **core permissions**, intended for use with specific custom integration endpoints.
    - *Fallback: If not provided, the API user credentials will be used for integration-specific tasks.*

*Note: The reason for separate `API` and `Integration` credentials is that often permissions are locked down to specific inteface (at least in my experience) while other are available only from "normal" `API`.*

# Setup and installation
1.  **Clone the repository**
    ``` PowerShell
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Create a virtual environment and install dependencies using `uv`:**
    ``` PowerShell
    uv sync
    ```

# Running the application
Once the setup and configuration are complete:

1.  Set environment variables:
- **Required**: Ensure `SN_API_USER` and `SN_API_PASSWORD` are set in your terminal session or system environment. These are essential for connecting to ServiceNow.
- **Optional**: If you plan to use features that leverage a separate integration user, also set `SN_INTEGRATION_USER` and `SN_INTEGRATION_PASSWORD`. If these are not provided, the application will default to using the primary `SN_API_USER` credentials for those integration tasks.
2.  Navigate to project directory.

    Open your terminal or command prompt and change to the root directory of your project (i.e., the folder containing main.py and config.toml).
3.  Run application:
    ``` PowerShell
    uv python .\main.py
    ```
    The application will:
    * Load the `config.toml`.
    * Set up logging.
    * Find and process each ticket template file.
    * For each template, determine if a ticket is due based on the current date and its schedule.
    * If due, it will create the corresponding ticket(s) in ServiceNow.
    * Log its actions to the console and the configured log file.


# Configuration
This application relies on two main types of configuration:

1.  **Main application cnfiguration (`config.toml`):**
    
    Located in the root directory, defines settings for logging, ServiceNow instance connection details, and the path to your ticket template files.

2.  **Ticket template files (`*.toml`):**

    These files define the structure, content, and schedule for each type of ticket to be created. They are typically stored in a dedicated directory specified in `config.toml`.

3.  **(Required) ServiceNow API credentials (environment variables):**
    
    For security, ServiceNow API credentials should be set as environment variables:
    * `SN_API_USER`: Your ServiceNow API username.
    * `SN_API_PASSWORD`: Your ServiceNow API password.

    Set them in your shell before running the application:
    ```PowerShell
    $env:SN_API_USER='XXX'
    $env:SN_API_PASSWORD='YYY'
    ```

4.  **(Optional) ServiceNow integration credentials:**
    
    * `SN_INTEGRATION_USER`: Your ServiceNow API username.
    * `SN_INTEGRATION_PASSWORD`: Your ServiceNow API password.

    ```PowerShell
    $env:SN_INTEGRATION_USER='XXX'
    $env:SN_INTEGRATION_PASSWORD='YYY'
    ```


## Config
This file allows you to customize logging behavior, ServiceNow connection details, and template locations.

``` toml
[log]
level = "debug"
dir = "logs"
filename_template = "ScheduledTickets_%Y_%m_%d.log"

[servicenow]
instance_url = "https://dev12345.service-now.com"
integration_url = "api/aisa2/integration_helper/XXX/XXX"

[templates]
path = ".\\resources\\*.toml"
```

### Fields
#### `[log]`
Parameters related to logging.

- `level`: `str` (Optional)

    Sets the logging verbosity.
  - Default value: `"info"`
  - Allowed values: 
    - `"info"` (for standard operational messages),
    - `"debug"` (for detailed diagnostic information).

- `dir`: `str` (Optional)

    The directory where log files will be stored.
  - Default value: `"logs"`
  
    <u>Note</u>: Uses relative path; The directory will be created automatically if it does not already exist.

- `filename_template`: `str` (Optional)

    A template for naming log files. It uses strftime format codes for date/time substitution.
  - Default value: `"app_%Y_%m_%d.log"`

    <u>Note</u>: `%Y_%m_%d` will be replaced with the current date.

#### `[servicenow]`
Parameters for connecting to the ServiceNow instance.

- `instance_url`: `str` (Required)

    The base URL of your ServiceNow instance (e.g., https://company.servicenow.com).

- `integration_url`: `str` (Optional)
  
    The specific API endpoint path for the integration, relative to the `instance_url`. This will be appended to `instance_url` to form the full **Integration Helper** endpoint.
    If specified it'll create an `sn_integration_client`, else it will be skipped.

#### `[templates]`
Parameters for locating application templates.

- `path`: `str` (Required)

    The path to the directory containing TOML template files used by the application (e.g., for generating ticket structures).
    
    <u>Note</u>: Supports glob patterns (e.g., *.toml matches all TOML files in the specified directory).


## Templates
Ticket creation is driven by TOML template files. These templates define the parameters for scheduled, automated ticket generation in ServiceNow. Each `.toml` file placed in the directory specified by `templates.path` (in the main `config.toml`) is treated as a distinct template. The filename itself (e.g., `daily_check.toml`) can be used for identification and scheduling purposes.

Below are examples of template structures:

### Example 1: Daily ticket (Weekdays)
```toml
[ticket]
assignment_group = "Technical support"
short_description = "Daily report for Owner"
description = "Please collect the data for daily report and send the updates to the Owner."

[ticket.schedule]
# For "daily", ticket is created every weekday (Mon-Fri).
frequency = "daily"
```

### Example 2: Weekly ticket
``` toml
[ticket]
assignment_group = "Technical support"
short_description = "Weekly data quality check"
description = "Please check the data quality for weekly report (attached) and send the updates to the Owner."

[ticket.schedule]
frequency = "weekly"
# day_of_week = 0 means Monday (Monday=0, ..., Sunday=6)
day_of_week = 0

[ticket.attachments]
files = [
    { path = "D:\\...\\Attachments_1.txt", required = true },
    { path = "D:\\...\\Attachments_2.txt", required = false }
]
```

### Example 3: Monthly ticket
``` toml
[ticket]
assignment_group = "Technical support"
short_description = "Monthly something check"
description = """Please check something
and send the updates to someone."""

[ticket.schedule]
# Creates a ticket on the 15th day of every month.
frequency = "monthly"
day_of_month = 15

[ticket.attachments]
files = [
    { path = "D:\\...\\Attachments_1.txt", required = true },
    { path = "D:\\...\\Attachments_2.txt", required = true }
]
```

### Example 4: Quarterly ticket
``` toml
[ticket]
assignment_group = "Technical support"
short_description = "Quarterly something check"
description = "Please update servers inventory."

[ticket.schedule]
# Creates a ticket on the 10th day of January, April, July, and October.
frequency = "quarterly"
months = [1, 4, 7, 10]
day_of_month = 10

[ticket.attachments]
files = [
    { path = "D:\\...\\Something.zip", required = false }
]
```

### Fields
The following sections describe the fields available within a ticket template TOML file.


#### `[ticket]`
This is the main table containing general information for the ticket.

- `assignment_group`: `str` (Required)

    The name of the ServiceNow assignment group to which the generated ticket will be assigned.

- `short_description`: `str` (Required)
    
    A brief summary for the ticket.

- `description`: `str` (Required)
    
    The detailed description or body content for the ticket.


#### `[ticket.schedule]`
This table groups all parameters related to defining when the ticket should be created.

- `frequency`: `str` (Required)
    
    Determines the base recurrence pattern for the ticket.
    - Allowed values:
        - `"daily"`: The ticket will be scheduled to run every weekday (Monday to Friday).
        - `"weekly"`: The ticket will be scheduled for a specific day of the week. Requires the `day_of_week` field to be set.
        - `"monthly"`: The ticket will be scheduled for a specific day of the month. Requires the `day_of_month` field to be set.
        - `"quarterly"`: The ticket will be scheduled for a specific day within designated months of a quarter. Requires `months` and `day_of_month` fields to be set.

- `day_of_week`: `int`
  
    Specifies the day of the week for ticket creation when `frequency` is `"weekly"`.
    - Values: Monday = 0, Tuesday = 1, ..., Sunday = 6.
  
  <u>Note</u>: This field is only used if `frequency` is `"weekly"`. It must be present and valid for a weekly schedule to be active. Ignored for other frequencies.

- `day_of_month`: `int`
    
    Specifies the day of the month for ticket creation.
    - Values: An integer from 1 to 31.

    <u>Note</u>: This field is used if `frequency` is `"monthly"` or `"quarterly"`. It must be present and valid for these schedules to be active. Ignored for other frequencies. **Remember about months with fewer than 31 days (e.g., setting day 31 for February).**

- `months`: `list[int]`
    
    A list of month numbers used when `frequency` is `"quarterly"`.
    - Values: Each integer in the list should be from 1 (January) to 12 (December).

    <u>Note</u>: This field is only used if `frequency` is `"quarterly"`. It must be present and contain valid month numbers for a quarterly schedule to be active. Ignored for other frequencies.


#### `[ticket.attachments]`
This dictionary groups parameters related to file attachments for the ticket.

- `files`: `list[dict]` (Optional)
    
    A list defining files to be attached to the generated ticket. Each item in the list is a dict specifying an individual attachment.

    <u>Note</u>: If an attachment item has `required = true` and the specified file cannot be found/accessed, the ticket creation will fail. If this entire `files` list is omitted or empty, no files will be attached.
    
    Each attachment item dict (an element in the `files` list) has the following fields:

    - `path`: `str` (Required within each attachment item)
        
        The absolute or relative file path to the file that needs to be attached.

    - `required`: `bool` (Required within each attachment item)
        
        Specifies if the attachment is mandatory for ticket creation.
        - If `true`: The ticket will not be created if this specific attachment file is not found.
        - If `false`: The ticket will be created even if this specific attachment is missing (it will simply be omitted).

# Code examples

## Create requested item (RITM)
``` python
base_ticket = sn_integration_client.create_requested_item(requested_for="Technical support")
sn_client.update_ticket(
    table_name = "sc_req_item",
    sys_id = base_ticket["sys_id"],
    payload = {
        "short_description": "Updated short description",
        "description": "Updated description",
        "work_notes": "Test work note",
    }
)
```
In my case, RITMs unfortunately needed to be created via the **Integration Helper** and then updated via the API.

## Create incident (INC)
``` python
sn_client.create_incident(
    organization = "Global",
    business_service="XXX",
    area = "IT",
    service_group = "Automation",
    category="Client Software",
    subcategory="Superior",
    short_description="Test INC",
    description="Test description",
    assignment_group = "3f8..."
)
```
By default `urgency` and `impact` are both set to `3`; if that should be different, just add those fields to the function.

Note: In my case I had to specify the ID of the team for `assignment_group` , passing the name would not work.

``` python
sn_client.create_incident(
    ...
    urgency = 1,
    impact = 1
)
```

## Get team
``` python
team = sn_client.get_team(name="XXX")
team_sys_id = team["sys_id"]
```

## Add attachment
``` python
sn_client.add_attachment(
    table_name = "incident",
    sys_id = ticket["sys_id"],
    file_path = "D:\\...\\test1.zip"
)
```