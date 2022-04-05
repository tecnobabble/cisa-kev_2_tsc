
# CISA KEV to Tenable.sc

CISA KEV to Tenable.sc is a way to parse vulnerability data from the CISA Catalog of Known Exploitable Vulnerabilities Catalog into [Tenable.sc](https://www.tenable.com/products/tenable-sc).

This integration automatically updates with the latest alerts from the CISA catalog and provides relative timelines for tracking and remedation.  Assets, Dashboards, Assurance Report Cards, and Queries can be created and updated automatically.

***This tool is not an officially supported Tenable project***

***Use of this tool is subject to the terms and conditions identified below, and is not subject to any license agreement you may have with Tenable***

## Requirements
* [Tenable.sc](https://www.tenable.com/products/tenable-sc) 5.20 or higher is required for proper CISA Cross Reference usage.
* Docker; though technically you can run the script standalone (not supported).
* Access to the [CISA Known Exploitable Vulnerabilities Catalog](https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json).  Offline support will be added in a future release
* Network access to your T.sc instance over the UI/API interface (default is TCP 443)

## Installation
Only running this as a docker image is supported; not a stand-alone script.

### Get the Docker Image

Use the pre-built docker image

```bash
docker pull tecnobabble/cisa-kev_2_tsc:latest
```

OR Manually Build Docker Image

1. Clone the GitHub repository to an empty folder on your local machine:
```bash
git clone https://github.com/tecnobabble/cisa-kev_2_tsc.git .
```
2. Build the container
```bash
docker build -t cisa-kev_2_tsc:latest .
```

Note - if you build the container locally, your image tag will need to be referenced when it's run; the examples below assume you're using the pre-built container image.

### Local Configuration
Setup a local .env file with the appropriate tenable.sc attributes (replace the attributes below with the ones specific to your environment). The container will read the .env file on the local file system to get the credentials/configuration for your local Tenable.sc environment. [Instructions to generate API keys on Tenable.sc.](https://docs.tenable.com/tenablesc/Content/GenerateAPIKey.htm)

```bash
SC_ADDRESS=10.0.0.102
SC_ACCESS_KEY=89b0aa234237ec13b06da8283919c0f7
SC_SECRET_KEY=8360bf971eb9a1e488d294d830a24eba
SC_PORT=443
```


#### Configuration Notes:
* SC_ADDRESS can be an IP or hostname.
* SC_PORT is optional; defaults to 443.
* The user who's API keys you select should be a part of the same primary group as the user who will use the objects created, though objects can be shared to other groups. 
* If desired to be used in multiple organizations within one [Tenable.sc](https://www.tenable.com/products/tenable-sc) console, run the script multiple times, specifiying different API keys for a user in each organization.
* This can be run directly from any host that supports docker and has network access to your Tenable.sc console; often it's easiest to run this directly from a Tenable Core instance.

##### To setup Docker on Tenable Core run:
* `sudo yum -y install docker`
* `sudo groupadd docker`
* `sudo usermod -aG docker $USER`
* `sudo systemctl start docker`
* `newgrp docker`
* `echo $USER | sudo tee -a /etc/cron.allow`
* `echo "00 07 * * * docker run --rm --env-file .env tecnobabble/cisa-kev_2_tsc:latest --feed cisa-kev --dashboard" | crontab -`
* `docker pull tecnobabble/cisa-kev_2_tsc:latest`

1. After following the steps above, create a local configuration file in the format noted above and put it in an appropriate directory in Tenable Core. 
2. Do a test run `docker run --rm --env-file .env tecnobabble/cisa-kev_2_tsc:latest --feed cisa-kev --dashboard`
3. Note that the crontab command above will automatically run the script at 7 am every morning; if you want this adjusted; adjust the cron settings.  Cron will also run out of the users root directory, so change the relative path of `.env` to the appropriate location. As written, it assumes `.env` is in the root of the Core user's home directory.

## Usage

Run the container, passing your .env file to the container and specify the feed you want to use, plus any additional content generation.

### Flags
 - `--feed cisa-kev`
	 - Generates queries based on the findings noted in the [CISA Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
	 - Takes 1 string argument; required.  
 -  `--asset`
	 - Creates a dynamic asset in Tenable.sc with the CVEs noted in the feed entry.
	 - No arguments, optional.
 - `--dashboard`
    - Creates a Dashboard named "CISA Known Exploited Vulns Status - Updated 2022-02-16" where the date is the last date that the script has updated the dashboard.
    - Attempts to update any custom dashboard with "CISA KEV" in the name, IF it's using the xref tags that the primary dashboard uses.
    - No arguments, optional
 -  `--arc`
	 - Creates an Assurance Report Card tracking by IPs for the date ranges specified.
	 - No arguments, optional.
	 
```
$ docker run --rm --env-file .env tecnobabble/cisa-kev_2_tsc:latest --feed cisa-kev --dashboard

Downloaded latest CISA KEVs from https://www.cisa.gov
Updating the existing query for CISA Past Due Vulns
Updating the existing query for CISA Vulns Due in the next 7 days
Updating the existing query for CISA Vulns Due in 7-14 days
Updating the existing query for CISA Vulns Due in 14-28 days
Updating the existing query for CISA Vulns Due in 4-8 weeks
Updating the existing query for CISA Vulns Due in 8-12 weeks
Updating the existing query for CISA Vulns Due in more than 12 weeks
Updating the existing dashboard for CISA Known Exploited Vulns Status - Updated 2022-02-16
Checking CISA KEV - Relative Due Dates...
Updated CISA KEV - Relative Due Dates
Checking CISA KEV - Top Actions to Remediation...
Checking CISA KEV - Vulnerability Summary...
Checking CISA KEV - 3-Month Trend...
Checking CISA KEV - Roadblocks Currently Gating Remediation...
Checking CISA KEV - Most Impacted Hosts...
Checking CISA KEV - Most Impacted Networks...
Updating the name of CISA Known Exploited Vulns Status - Updated 2022-02-16 to CISA Known Exploited Vulns Status - Updated 2022-02-17
Finished updating Tenable.sc with the latest available data from CISA.
```
![example vulnfeed_output](https://res.cloudinary.com/salted-security/image/upload/v1645112723/Github/cisa-kev-dashboard_krzshz.png)

### Offline Mode
1. Download the 'known_exploited_vulnerabilities.json' file from the [CISA Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog).  
2. Pull or build the docker image locally then [save it](https://docs.docker.com/engine/reference/commandline/save/).
3. Sneaker-net both files to your air-gapped or offline system that can access Tenable.sc.  
4. Run the docker command as above, substituting '~/Downloads/known_exploited_vulnerabilities.json' in the command below to the local path of the file downloaded in step 1.

```
docker run --rm --env-file labbox.env -v ~/Downloads/known_exploited_vulnerabilities.json:/home/vulnfeed/known_exploited_vulnerabilities.json tecnobabble/cisa-kev_2_tsc:latest --feed cisa-kev --dashboard
```

### Suggested operations
* Run the script on a daily basis.  This can be most easily accomplished through cron.
* Run the docker container with the `--rm` flag to auto delete the container after running.
* All queries, assets, and dashboard can be edited after generation by the Tenable.sc user.  If the object name is changed, the script may generate a new object with the original name.

### Basic workflow under the hood
1. Script is called and flags specified
2. Catalog is downloaded from CISA's website
3. Tenable.sc is queried to see if a Query already exists, if so, the relative date content is updated.
6. A query is created with the relative date title and associated content.
7. If additional objects are requested (assets, or dashboards, they are created.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please open a new issue to request support for new feeds.

## License
[GNU GPL](https://choosealicense.com/licenses/gpl-3.0/)
