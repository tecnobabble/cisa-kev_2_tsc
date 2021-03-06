#!/usr/bin/env python
import re
from tenable.sc import TenableSC, ConnectionError
import os
from decouple import config, UndefinedValueError
import getopt, sys
import requests
import csv
import datetime
from jinja2 import Environment, FileSystemLoader, BaseLoader
from phpserialize import serialize, unserialize
import base64
import ast
from bs4 import BeautifulSoup
import html
import json
import logging
import warnings

warnings.filterwarnings('ignore')
warnings.warn('Starting an unauthenticated session')


# Set some variables that need setting (pulled from .env file passed to container or seen locally in the same folder as script)
try:
    sc_address = config('SC_ADDRESS')
    sc_access_key = config('SC_ACCESS_KEY')
    sc_secret_key = config('SC_SECRET_KEY')
    sc_port = config('SC_PORT', default=443)
    debug_set = config('DEBUG', cast=bool, default=False)
except UndefinedValueError as err:
    print("Please review the documentation and define the required connection details in an environment file.")
    print()
    raise SystemExit(err)

if debug_set is True:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.CRITICAL)
    #logging.basicConfig(level=logging.DEBUG)

report_request = False
alert_request = False
asset_request = False
arc_request = False
dashboard_request = False
feed_URL = ""
email_list = ""

# Handle arguments passed to script.  Note Help is defined but not yet supported.
full_cmd_arguments = sys.argv
argument_list = full_cmd_arguments[1:]
short_options = "hfre:"
long_options = ["help", "feed=", "report", "alert", "email=", "asset", "arc", "dashboard"]

try:
    arguments, values = getopt.getopt(argument_list, short_options, long_options)
except getopt.error as err:
    # Output error, and return with an error code
    print (str(err))
    sys.exit(2)

#####################
# Most of the code that does the actual work
#####################

# Login to Tenable.sc
def tsc_login():
    try:
        sc = TenableSC(sc_address, port=sc_port)
        sc.login(access_key=sc_access_key, secret_key=sc_secret_key)
    except (NameError) as err:
        print("Please verify connection details.")
        exit()
    except (ConnectionError) as err:
        raise SystemExit(err)
    return sc

## Pull all existing queries from T.sc that this API user can see.
def get_tsc_queries(sc):
    sc_queries = sc.queries.list()

# Pull all existing assets from T.sc that this API user can see.
def get_tsc_assets(sc):
    sc_assets = sc.asset_lists.list()

    
def convert_date(date):
    return date.replace("-","/")

# Main function to pull feeds and query tenable
def query_populate():
    #see if a file is local; if so, use that first
    if os.path.exists('known_exploited_vulnerabilities.json'):
        f = open('known_exploited_vulnerabilities.json')
        data = json.load(f)
        print('Loaded CISA KEVs from disk')
    else:
        try:
            with requests.Session() as s:
                download = s.get(feed_URL)
            data = json.loads(download.content.decode())
            print('Downloaded latest CISA KEVs from https://www.cisa.gov')
        except:
            print("Something went wrong with getting the CISA feed; check your internet connectivity or provide a local copy of the catalog.")
            exit()
    
    due_dates = set()
    for vuln in data['vulnerabilities']:
        due_dates.add(vuln['dueDate'])
    
    today = datetime.date.today()
    
    #Go through the dates and determine relative to today
    past_due = set()
    due_1_week = set()
    due_2_week = set()
    due_4_week = set()
    due_8_week = set()
    due_12_week = set()
    due_12plus_week = set()
    for date in due_dates:
        datetime2 = datetime.datetime.strptime(date, '%Y-%m-%d')
        #Pull out older dates
        if datetime2.date() < today:
            past_due.add(convert_date(date))
                  
        #Pull out 1 week dates
        elif abs((today - datetime2.date()).days) < 8:
            due_1_week.add(convert_date(date))
      
        #Pull out 2 week dates
        elif abs((today - datetime2.date()).days) < 15:
            due_2_week.add(convert_date(date))
            
        #Pull out 4 week dates
        elif abs((today - datetime2.date()).days) < 29:
            due_4_week.add(convert_date(date))
            
        #Pull out 8 week dates
        elif abs((today - datetime2.date()).days) < 57:
            due_8_week.add(convert_date(date))
            
        #Pull out 12 week dates
        elif abs((today - datetime2.date()).days) < 85:
            due_12_week.add(convert_date(date))
            
        #Pull out more than 12 week dates
        else:
            due_12plus_week.add(convert_date(date))
      
    #Collapse past due dates as much as possible
    past_due_optimize = set()
    this_month = int(today.strftime("%m"))
    this_year = int(today.strftime("%Y"))
    for date in past_due:
        due_year = datetime.datetime.strptime(date, '%Y/%m/%d').year
        due_month = datetime.datetime.strptime(date, '%Y/%m/%d').month
        # add previous years
        if due_year < this_year:
            past_due_optimize.add(str(due_year) + "/*")
        # add individual due dates for this month
        elif due_month == this_month:
            past_due_optimize.add(date)
    # add all previous months in this year
    for i in range (1, this_month):
        past_due_optimize.add(str(this_year) + "/" + (f"{i:02d}") + "/*")
        
    #Collapse far future due dates as much as possible
    due_12plus_week_optimize = set()
    for date in due_12plus_week:
        due_year = datetime.datetime.strptime(date, '%Y/%m/%d').year
        due_month = datetime.datetime.strptime(date, '%Y/%m/%d').month
        # add future years
        if due_year > this_year:
            due_12plus_week_optimize.add(str(due_year) + "/*")
        # add individual due dates for this month
        elif due_month < this_month + 4:
            due_12plus_week_optimize.add(date)
    # add all future months in this year beyond 12 weeks
    for i in range (this_month + 4, 13):
        due_12plus_week_optimize.add(str(this_year) + "/" + (f"{i:02d}") + "/*")

    relative_due_dates = {}
    relative_due_dates['CISA Past Due Vulns'] = past_due_optimize
    relative_due_dates['CISA Past Due Vulns'].add("past_due")
    relative_due_dates['CISA Vulns Due in the next 7 days'] = due_1_week
    relative_due_dates['CISA Vulns Due in the next 7 days'].add("due_1_week")
    relative_due_dates['CISA Vulns Due in 7-14 days'] = due_2_week
    relative_due_dates['CISA Vulns Due in 7-14 days'].add("due_2_week")
    relative_due_dates['CISA Vulns Due in 14-28 days'] = due_4_week
    relative_due_dates['CISA Vulns Due in 14-28 days'].add("due_4_week")
    relative_due_dates['CISA Vulns Due in 4-8 weeks'] = due_8_week
    relative_due_dates['CISA Vulns Due in 4-8 weeks'].add("due_8_week")
    relative_due_dates['CISA Vulns Due in 8-12 weeks'] = due_12_week
    relative_due_dates['CISA Vulns Due in 8-12 weeks'].add("due_12_week")
    relative_due_dates['CISA Vulns Due in more than 12 weeks'] = due_12plus_week_optimize
    relative_due_dates['CISA Vulns Due in more than 12 weeks'].add("due_12plus_week")

    #print(relative_due_dates)


    # Create the Query
    
    for key in relative_due_dates.keys():
        entry_title = key
        xref_string = ""
        asset_rules = ['any']    
    
        
        for entry in relative_due_dates[key]:
            xref_string += "CISA-KNOWN-EXPLOITED|" + entry + ","
            xref_asset_string = "CISA-KNOWN-EXPLOITED|" + entry
            asset_rules.append(('xref','eq',xref_asset_string))
        
        if xref_string == "":
            xref_string = "CISA-KNOWN-EXPLOITED|none"
            
        asset_rules = tuple(asset_rules)
        
        query_done = False
        for x in range(len(sc_queries['usable'])):
            if entry_title == sc_queries['usable'][x]['name']:
                print("Updating the existing query for", entry_title)
                query_id = sc_queries['usable'][x]['id']
                query_response = sc.queries.edit(query_id, 'sumid', 'vuln', filters=[{'filterName': 'xref', 'operator': '=', 'value': xref_string.rstrip(',') }], description="Updated on " + str(today))
                query_done = True
                break
    
        if query_done == False:
            query_response = sc.queries.create(entry_title, 'sumid', 'vuln', ('xref', '=', xref_string.rstrip(',')), tags="CISA KEV")
            query_id = query_response['id']
            print("Created a query for", entry_title)
    
        if asset_request is True:
            asset_done = False 
            for x in range(len(sc_assets['usable'])):
                if entry_title == sc_assets['usable'][x]['name']:
                    print("Updating the existing asset for", entry_title)
                    asset_id = sc_assets['usable'][x]['id']
                    gen_asset(entry_title, asset_rules, False, asset_id, today)
                    asset_done = True
                    break
            if asset_done is False:
                gen_asset(entry_title, asset_rules, True, 0, today)
                print("Created an asset for", entry_title)
    
    if dashboard_request is True:
        entry_description = ""

        skip_dashboard = False
    
        # Make the Dashboard Name usable (replace variables)
        dashboard_name = dashboard_template_name[0].replace("{{ Current_Date }}", str(today))

        for x in range(len(sc_dashboards['response']['usable'])):
            if "CISA Known Exploited Vulns Status - Updated" in sc_dashboards['response']['usable'][x]['name'] or "CISA KEV" in sc_dashboards['response']['usable'][x]['name']:
                print("Updating the existing dashboard for", sc_dashboards['response']['usable'][x]['name'])
                dashboard_id = sc_dashboards['response']['usable'][x]['id']
                dcomponent = json.loads(sc.get('dashboard/' + dashboard_id + '/component').text)
                for component in dcomponent['response']:
                    refresh_required = False
                    component_details = json.loads(sc.get('dashboard/' + dashboard_id + '/component/' + component['id']).text)['response']
                    print("Checking " + component_details['name'] + "...")
                    for datasources in component_details['definition']['allDataSources']:
                        query_detail = sc.queries.details(datasources['queryID'])
                        refresh_required = update_system_query(query_detail, relative_due_dates)
                    if refresh_required is True:
                        sc.post('dashboard/' + dashboard_id + '/component/' + component['id'] + '/refresh')
                        print("Updated "+ component_details['name'])
                if sc_dashboards['response']['usable'][x]['name'] != dashboard_name and "CISA KEV" not in sc_dashboards['response']['usable'][x]['name']:
                    data = { 'name' : dashboard_name }
                    sc.patch('dashboard/' + dashboard_id, params=data)
                    print("Updating the name of " + sc_dashboards['response']['usable'][x]['name'] + " to " + dashboard_name) 
                skip_dashboard = True
                
        if skip_dashboard is False:
            gen_dashboard(entry_title, entry_description, relative_due_dates, True, 0)
            print("Created a new dashboard for", dashboard_name)
    
    if arc_request is True:
        skip_arc = False
        skip_arc_entry = False
        cisa_past_due,cisa_7_day,cisa_14_day,cisa_28_day,cisa_8_week,cisa_12_week,cisa_12plus_week = enable_xrefs(relative_due_dates)
        arc_name = arc_template_name.replace("{{ Current_Date }}", str(today))
        
        for x in range(len(sc_arcs['response']['usable'])):
            if "CISA Known Exploited Vulns Status - Updated 2" in sc_arcs['response']['usable'][x]['name']:
                updated_arc_name = re.sub("(\d{4}-\d{2}-\d{2})", str(today), sc_arcs['response']['usable'][x]['name'])
                focus_filters = json.loads(sc.get('arc/' + sc_arcs['response']['usable'][x]['id']).text)['response']['focusFilters']
                print("Updating the existing ARC for", updated_arc_name)
                skip_arc = True
                updated_ps = []
                for y in range(len(sc_arcs['response']['usable'][x]['policyStatements'])):
                    cisa_arc_ps = json.loads(sc.get('arc/' + sc_arcs['response']['usable'][x]['id']).text)['response']['policyStatements']
                    for ps in cisa_arc_ps:
                        list_filters = update_policy_statement(ps, relative_due_dates)
                        ps['baseFilters'], ps['compliantFilters'], ps['drilldownFilters'] = list_filters
                        updated_ps.append(ps)
                    break
                updated_ps_all = { 'name': updated_arc_name, 'focusFilters': focus_filters, 'schedule': { "enabled": "true", "repeatRule": "FREQ=DAILY;INTERVAL=1", "start": "TZID=UTC:20220405T004100", "type": "ical" }, 'policyStatements': updated_ps}
                arc_url = "arc/" + ps['arcID']
                sc.patch(arc_url, json=updated_ps_all)

        if skip_arc is False:
            gen_arc(relative_due_dates, arc_name)
            print("Created an ARC for", arc_name)  
    
    print("Finished updating Tenable.sc with the latest available data from CISA.")
    exit()
   
# Generate an arc for the first time
def gen_arc(relative_due_dates, entry_title):
    Entry_Title = entry_title
    today = datetime.date.today()
    Current_Date = str(today)
    cisa_past_due,cisa_7_day,cisa_14_day,cisa_28_day,cisa_8_week,cisa_12_week,cisa_12plus_week = enable_xrefs(relative_due_dates)

    # Load the definition template as a jinja template
    env = Environment(loader = FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
    arc_template_def = env.get_template('arc_definition.txt')

    #Render the definition template with data and print the output
    arc_raw = arc_template_def.render(Current_Date=Current_Date, cisa_past_due=cisa_past_due, cisa_7_day=cisa_7_day, cisa_14_day=cisa_14_day, cisa_28_day=cisa_28_day, cisa_8_week=cisa_8_week, cisa_12_week=cisa_12_week, cisa_12plus_week=cisa_12plus_week)
    
    arc_template_file = open('templates/arc_working_template.txt')
    arc_xml = arc_template_file.read()

    for policy_statement in json.loads(arc_raw):
        policy_statement = ast.literal_eval(policy_statement)
        arc_def_output = base64.b64encode(serialize(policy_statement))
        arc_xml = arc_xml.replace("{{ arc_output }}", arc_def_output.decode('utf8'), 1)       

    arc_name = Entry_Title.replace(" ","").replace(":","-")[:15] + "_arc.xml"
    generated_tsc_arc_file = open(arc_name, "w")
    generated_tsc_arc_file.write(arc_xml)
    generated_tsc_arc_file.close()

    # Upload the arc to T.sc
    generated_tsc_arc_file = open(arc_name, "r")
    tsc_arc_file = sc.files.upload(generated_tsc_arc_file)
    arc_data = { "name":entry_title,"filename":str(tsc_arc_file), "order":"0" }
    arc_post = sc.post('arc/import', json=arc_data).text
    arc_post = json.loads(arc_post)
    global arc_id
    arc_id = arc_post['response']['id']
    generated_tsc_arc_file.close()

    #Grab a new copy of the ARCs in T.sc, cause we just created a new one
    global sc_arcs
    sc_arcs = sc.get('arc').text
    sc_arcs = json.loads(sc_arcs)


# Create a new arc policy statement
def gen_arc_policy(cve_s, arc_id, entry_title):
    Entry_Title = entry_title
    cve_list = cve_s
    arc_id = "arc/" + arc_id

    sc_arc_feed = sc.get(arc_id).text
    sc_arcs_feed = json.loads(sc_arc_feed)

    sc_arc_policies = sc_arcs_feed['response']['policyStatements']

    env = Environment(loader = FileSystemLoader('templates'), trim_blocks=True, lstrip_blocks=True)
    arc_template_def = env.get_template('arc_policy.txt')

    #Render the definition template with data and print the output
    arc_raw = arc_template_def.render(cve_list=cve_list, Entry_Title=Entry_Title)
    arc_raw = json.loads(arc_raw)
    sc_arc_policies.append(arc_raw)
    sc_arc_policies_post = { 'policyStatements': sc_arc_policies, 'focusFilters': [], "schedule":{"start":"TZID=UTC:20200707T193300","repeatRule":"FREQ=DAILY;INTERVAL=1","type":"ical","enabled":"true"} }
    arc_patch = sc.patch(arc_id, json=sc_arc_policies_post).text
    arc_patch = json.loads(arc_patch)

   
   
#Update a query 
def update_system_query(query_detail, relative_due_dates):
    component_updated = False
    cisa_past_due,cisa_7_day,cisa_14_day,cisa_28_day,cisa_8_week,cisa_12_week,cisa_12plus_week = enable_xrefs(relative_due_dates)
    for qfilter in query_detail['filters']:
        if 'CISA-KNOWN-EXPLOITED|past_due' in qfilter['value']:
            findex = query_detail['filters'].index(qfilter)
            query_detail['filters'][findex]['value'] = cisa_past_due
            component_updated = True
        elif 'CISA-KNOWN-EXPLOITED|due_1_week' in qfilter['value']:
            findex = query_detail['filters'].index(qfilter)
            query_detail['filters'][findex]['value'] = cisa_7_day
            component_updated = True
        elif 'CISA-KNOWN-EXPLOITED|due_2_week' in qfilter['value']:
            findex = query_detail['filters'].index(qfilter)
            query_detail['filters'][findex]['value'] = cisa_14_day
            component_updated = True
        elif 'CISA-KNOWN-EXPLOITED|due_4_week' in qfilter['value']:
            findex = query_detail['filters'].index(qfilter)
            query_detail['filters'][findex]['value'] = cisa_28_day
            component_updated = True
        elif 'CISA-KNOWN-EXPLOITED|due_8_week' in qfilter['value']:
            findex = query_detail['filters'].index(qfilter)
            query_detail['filters'][findex]['value'] = cisa_8_week
            component_updated = True
        elif 'CISA-KNOWN-EXPLOITED|due_12_week' in qfilter['value']:
            findex = query_detail['filters'].index(qfilter)
            query_detail['filters'][findex]['value'] = cisa_12_week
            component_updated = True
        elif 'CISA-KNOWN-EXPLOITED|due_12plus_week' in qfilter['value']:
            findex = query_detail['filters'].index(qfilter)
            query_detail['filters'][findex]['value'] = cisa_12plus_week
            component_updated = True
    sc.queries.edit(query_detail['id'], filters=query_detail['filters'])
    return component_updated

#Update an arc_policy_statement 
def update_policy_statement(ps_detail, relative_due_dates):
    ps_updated = False
    cisa_past_due,cisa_7_day,cisa_14_day,cisa_28_day,cisa_8_week,cisa_12_week,cisa_12plus_week = enable_xrefs(relative_due_dates)
    list_filters = [ ps_detail['baseFilters'], ps_detail['compliantFilters'], ps_detail['drilldownFilters'] ]

    for qfilter in list_filters:
        if not qfilter: continue
        for at_filter in qfilter:
            if 'CISA-KNOWN-EXPLOITED|past_due' in at_filter['value']:
                findex = list_filters.index(qfilter)
                gindex = qfilter.index(at_filter)
                list_filters[findex][gindex]['value'] = cisa_past_due
                ps_updated = True
            elif 'CISA-KNOWN-EXPLOITED|due_1_week' in at_filter['value']:
                findex = list_filters.index(qfilter)
                gindex = qfilter.index(at_filter)
                list_filters[findex][gindex]['value'] = cisa_7_day
                ps_updated = True
            elif 'CISA-KNOWN-EXPLOITED|due_2_week' in at_filter['value']:
                findex = list_filters.index(qfilter)
                gindex = qfilter.index(at_filter)
                list_filters[findex][gindex]['value'] = cisa_14_day
                ps_updated = True
            elif 'CISA-KNOWN-EXPLOITED|due_4_week' in at_filter['value']:
                findex = list_filters.index(qfilter)
                gindex = qfilter.index(at_filter)
                list_filters[findex][gindex]['value'] = cisa_28_day
                ps_updated = True
            elif 'CISA-KNOWN-EXPLOITED|due_8_week' in at_filter['value']:
                findex = list_filters.index(qfilter)
                gindex = qfilter.index(at_filter)
                list_filters[findex][gindex]['value'] = cisa_8_week
                ps_updated = True
            elif 'CISA-KNOWN-EXPLOITED|due_12_week' in at_filter['value']:
                findex = list_filters.index(qfilter)
                gindex = qfilter.index(at_filter)
                list_filters[findex][gindex]['value'] = cisa_12_week
                ps_updated = True
            elif 'CISA-KNOWN-EXPLOITED|due_12plus_week' in at_filter['value']:
                findex = list_filters.index(qfilter)
                gindex = qfilter.index(at_filter)
                list_filters[findex][gindex]['value'] = cisa_12plus_week
                ps_updated = True
    return list_filters
    
    
# make relative dates data xref filterable
def enable_xrefs(relative_due_dates):
    for key in relative_due_dates.keys():
        entry_title = key
        xref_string = ""

        for entry in relative_due_dates[key]:
            xref_string += "CISA-KNOWN-EXPLOITED|" + entry + ","
        
        if xref_string == "":
            xref_string = "CISA-KNOWN-EXPLOITED|none"
        if key == "CISA Past Due Vulns":
            cisa_past_due = xref_string.rstrip(",")
        elif key == "CISA Vulns Due in the next 7 days":
            cisa_7_day = xref_string.rstrip(",")
        elif key == "CISA Vulns Due in 7-14 days":
            cisa_14_day = xref_string.rstrip(",")
        elif key == "CISA Vulns Due in 14-28 days":
            cisa_28_day = xref_string.rstrip(",")
        elif key == "CISA Vulns Due in 4-8 weeks":
            cisa_8_week = xref_string.rstrip(",")
        elif key == "CISA Vulns Due in 8-12 weeks":
            cisa_12_week = xref_string.rstrip(",")
        elif key == "CISA Vulns Due in more than 12 weeks":
            cisa_12plus_week = xref_string.rstrip(",")
    return cisa_past_due,cisa_7_day,cisa_14_day,cisa_28_day,cisa_8_week,cisa_12_week,cisa_12plus_week

# Generate a canned t.sc dashboard about the entry
def gen_dashboard(entry_title, entry_description, relative_due_dates, new_dashboard, dashboard_id):
    Entry_Title = entry_title.replace("'","")
    #Entry_ShortDesc = "For more information, please see the full page at " + entry_link
    Entry_Summary = entry_description.replace("'","").replace("\\","/")
    today = datetime.date.today()
    Current_Date = str(today)
    cisa_past_due,cisa_7_day,cisa_14_day,cisa_28_day,cisa_8_week,cisa_12_week,cisa_12plus_week = enable_xrefs(relative_due_dates)
    
    dashboard_template_file = open('templates/sc_working_dashboard_template.txt', "r")
    dashboard_template_contents = dashboard_template_file.read()
    
    for x in range(len(re.findall("<definition>(.+)</definition>", str(dashboard_template_contents)))): 
        r_dashboard_component = Environment(loader=BaseLoader()).from_string(dashboard_components_list[x])
        component_render = r_dashboard_component.render(Current_Date=Current_Date, Entry_Title=Entry_Title, Entry_Summary=Entry_Summary, cisa_past_due=cisa_past_due, cisa_7_day=cisa_7_day, cisa_14_day=cisa_14_day, cisa_28_day=cisa_28_day, cisa_8_week=cisa_8_week, cisa_12_week=cisa_12_week, cisa_12plus_week=cisa_12plus_week)
        component_raw = ast.literal_eval(component_render)
        component_output = base64.b64encode(serialize(component_raw))

        dashboard_template_contents = str(dashboard_template_contents).replace('{{ dashboard_output }}', component_output.decode("utf8"), 1)
        #print(dashboard_template_contents)  
        #dashboard_template_contents.replace('re.findall("<definition>(.+)</definition>", str(dashboard_template_contents)[x])',dashboard_components_list[x])
 
    #print(dashboard_template_contents)       
    
    r_dashboard_full = Environment(loader=BaseLoader()).from_string(dashboard_template_contents)
    dashboard_full = r_dashboard_full.render(Current_Date=Current_Date, Entry_Title=Entry_Title, Entry_Summary=Entry_Summary, cisa_past_due=cisa_past_due, cisa_7_day=cisa_7_day, cisa_14_day=cisa_14_day, cisa_28_day=cisa_28_day, cisa_8_week=cisa_8_week, cisa_12_week=cisa_12_week, cisa_12plus_week=cisa_12plus_week)
    

    # Write the output to a file that we'll then upload to tsc.
    dashboard_name = Entry_Title.replace(" ","").replace(":","-")[:15] + "_dashboard.xml"
    generated_tsc_dashboard_file = open(dashboard_name, "w")
    generated_tsc_dashboard_file.write(dashboard_full)
    generated_tsc_dashboard_file.close()

    # Upload the dashboard to T.sc
    generated_tsc_dashboard_file = open(dashboard_name, "r")
    tsc_file = sc.files.upload(generated_tsc_dashboard_file)
    dashboard_data = { "name":"","order":"1","filename":str(tsc_file) }
    dashboard_post = sc.post('dashboard/import', json=dashboard_data).text
    dashboard_post = json.loads(dashboard_post)
    dashboard_id = dashboard_post['response']['id']
    generated_tsc_dashboard_file.close()

    return dashboard_id

# Generate an asset
def gen_asset(entry_title, asset_rules, new_asset, asset_id, today):
    asset_name = entry_title
    if new_asset is True:
        sc.asset_lists.create(name=asset_name,list_type="dynamic",tags="CISA KEV",rules=asset_rules,description="Updated at " + str(today))
    elif new_asset is False:
        sc.asset_lists.edit(id=asset_id,list_type="dynamic",tags="CISA KEV",rules=asset_rules,description="Updated at " + str(today))


# Actually handling the arguments that come into the container.
for current_argument, current_value in arguments:
    if current_argument in ("-h", "--help"):
        print ("To Do.  See README.") # TO DO: Turn into function
        exit()
    #elif current_argument in ("-s", "--t.sc"): # Not implemented until we have T.io functionality
        #print ("Pass to T.sc and attempt to create queries")
    if current_argument in ("--arc"):
        arc_request = True
    if current_argument in ("--asset"):
        asset_request = True
    if current_argument in ("--dashboard"):
        dashboard_request = True
    if current_argument in ("-f", "--feed"):
        feed = current_value.upper()
        if current_value == "cisa-kev":
            feed_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
        else:
            print("Input a valid feed")
            exit()

# Based on the data provided, decide what to do
if len(feed_URL) >= 10:
    sc = tsc_login()
    sc_queries = sc.queries.list()
    if asset_request is True:
        sc_assets = sc.asset_lists.list()
    if report_request is True:
        sc_reports = sc.get('reportDefinition').text
        sc_reports = json.loads(sc_reports)
        # Check to see if a custom template is provided
        if os.path.isfile('/templates/custom_sc_report.xml'):
            sc_template_path = '/templates/custom_sc_report.xml'
        else:
            sc_template_path = "/templates/sc_template.xml"

        # Let's read the base sc template and pull out the report definition and other info
        sc_template_file = open(sc_template_path, "r")
        template_contents = sc_template_file.read()
        template_def = re.search("<definition>(.+)</definition>", str(template_contents))
        template_report_name = re.search("<name>(.+)</name>", str(template_contents)).group(1)
        #template_report_desc = re.search("<description>(.+)</description>", str(template_contents))
        sc_template_file.close()

        # replace def with tag to be substituted later
        new_sc_template = re.sub("<definition>(.+)</definition>", "<definition>{{ report_output }}</definition>", str(template_contents))
        sc_working_template_file = open('templates/sc_working_template.txt', "w")
        sc_working_template_file.write(new_sc_template)
        sc_working_template_file.close()

        # Let's put the encoded report def into a format we can work with
        template_def = base64.b64decode(template_def.group(1))
        template_def = unserialize(template_def, decode_strings=True)

        # Replace the CVE placeholder with something we can swap out later
        template_def = str(template_def).replace("CVE-1990-0000", "{{ cve_list }}")

        # Write this definition template to a file
        template_def_file = open("templates/definition.txt", "w")
        template_def_file.write(template_def)
        template_def_file.close()
    if arc_request is True:
        sc_arcs = sc.get('arc').text
        sc_arcs = json.loads(sc_arcs)
        arc_name = feed + " Advisory Alerts"
        if os.path.isfile('templates/custom_arc_report.xml'):
            arc_template_path = 'templates/custom_arc_report.xml'
        else:
            arc_template_path = "templates/arc_template.xml"

        # Let's read the base sc template and pull out the report definition and other info
        arc_template_file = open(arc_template_path, "r")
        arc_template_contents = arc_template_file.read()
        arc_template_def = re.findall("<definition>(.+)</definition>", str(arc_template_contents))
        arc_template_name = re.search("<name>(.+)</name>", str(arc_template_contents)).group(1)
        arc_template_file.close()

        # replace def with tag to be substituted later
        new_arc_template = re.sub("<definition>(.+)</definition>", "<definition>{{ arc_output }}</definition>", str(arc_template_contents))
        arc_policy_def = re.search("(<policyStatement>.+</policyStatement>)", str(new_arc_template))
        arc_working_template_file = open('templates/arc_working_template.txt', "w")
        arc_working_template_file.write(new_arc_template)
        arc_working_template_file.close()

        # Let's put the encoded report def into a format we can work with
        arc_replaced = []
        for policy_statement in arc_template_def:
            arc_template_def = base64.b64decode(policy_statement)
            arc_template_def = unserialize(arc_template_def, decode_strings=True)

            # Replace the CVE placeholder with something we can swap out later
            arc_template_def = str(arc_template_def)\
                        .replace("CVE-1990-0000", "{{ cve_list }}")\
                        .replace("{{ CISA|Past_Due }}", "{{ cisa_past_due }}")\
                        .replace("{{ CISA|7_Days }}", "{{ cisa_7_day }}")\
                        .replace("{{ CISA|7-14_Days }}", "{{ cisa_14_day }}")\
                        .replace("{{ CISA|14-28_Days }}", "{{ cisa_28_day }}")\
                        .replace("{{ CISA|4-8_Weeks }}", "{{ cisa_8_week }}")\
                        .replace("{{ CISA|8-12_Weeks }}", "{{ cisa_12_week }}")\
                        .replace("{{ CISA|12+_Weeks }}", "{{ cisa_12plus_week }}")
            
            arc_replaced.append(arc_template_def)

        # Write this definition template to a file
        arc_template_def_file = open("templates/arc_definition.txt", "w")
        arc_template_def_file.write(str(arc_replaced))
        arc_template_def_file.close()

    if dashboard_request is True:
        sc_dashboards = sc.get('dashboard').text
        sc_dashboards = json.loads(sc_dashboards)
        # Check to see if a custom template is provided
        if os.path.isfile('templates/custom_sc_dashboard.xml'):
            sc_dashboard_template_path = 'templates/custom_sc_dashboard.xml'
        else:
            sc_dashboard_template_path = "templates/sc_dashboard_template.xml"

        # Let's read the base sc template and pull out the dashboard definitions and other info
        sc_dashboard_template_file = open(sc_dashboard_template_path, "r")
        dashboard_template_contents = sc_dashboard_template_file.read()
        dashboard_template_def = re.findall("<definition>(.+)</definition>", str(dashboard_template_contents))
        dashboard_template_name = re.findall("<name>(.+)</name>", str(dashboard_template_contents))
        dashboard_template_desc = re.findall("<description>(.+)</description>", str(dashboard_template_contents))
        sc_dashboard_template_file.close()

        # replace def with tag to be substituted later
        new_sc_dashboard_template = re.sub("<definition>(.+)</definition>", "<definition>{{ dashboard_output }}</definition>", str(dashboard_template_contents))
        sc_working_dashboard_template_file = open('templates/sc_working_dashboard_template.txt', "w")
        sc_working_dashboard_template_file.write(new_sc_dashboard_template)
        sc_working_dashboard_template_file.close()
        
        dashboard_components_list = []
        # Let's put the encoded dashboard def into a format we can work with
        for component_def in dashboard_template_def:
            component_template_def = base64.b64decode(component_def)
            component_template_def = unserialize(component_template_def, decode_strings=True)
            #print(component_template_def)
            # Replace the CVE placeholder with something we can swap out later
            component_template_def = str(component_template_def)\
                    .replace("CVE-1990-0000", "{{ cve_list }}")\
                    .replace("{{ CISA|Past_Due }}", "{{ cisa_past_due }}")\
                    .replace("{{ CISA|7_Days }}", "{{ cisa_7_day }}")\
                    .replace("{{ CISA|7-14_Days }}", "{{ cisa_14_day }}")\
                    .replace("{{ CISA|14-28_Days }}", "{{ cisa_28_day }}")\
                    .replace("{{ CISA|4-8_Weeks }}", "{{ cisa_8_week }}")\
                    .replace("{{ CISA|8-12_Weeks }}", "{{ cisa_12_week }}")\
                    .replace("{{ CISA|12+_Weeks }}", "{{ cisa_12plus_week }}")
            dashboard_components_list.append(component_template_def)


        # Write this definition template to a file
        #dashboard_template_def_file = open("/templates/dashboard_definition.txt", "w")
        #dashboard_template_def_file.write(str(dashboard_components_list))
        #dashboard_template_def_file.close()

    query_populate()
else:
    print("Please specify a feed or --help")
