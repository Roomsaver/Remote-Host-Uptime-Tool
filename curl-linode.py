#!/usr/bin/python3

from select import select
import sys
import requests
import json
import time
import paramiko
import re
import csv


########################### CLASS FOR STRING COLORS ###########################
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'



########################### CHECK IF LINODE SNAPSHOT HAS SUCCEEDED ###########################
def check_snapshot(id, backupID, bearerToken):
    # Set up headers
    bearer = "Bearer " + bearerToken
    headers = {"Authorization": bearer}

    # Set up URL 
    newUrl = "https://api.linode.com/v4/linode/instances/" + str(id) + "/backups/" + str(backupID)

    # GET request to Linode
    newResp = requests.get(newUrl, headers=headers)
    # Immediately cast to json
    newResp = newResp.json()

    # maximum wait 5 minutes or 40 times every 7.5 seconds
    timerMax = 40
    timerCounter = 0
    while str(newResp["status"]) != "successful" and str(newResp["status"]) != "needsPostProcessing":
        time.sleep(7.5)
        # GET request to Linode. This will continue requesting until the status is successful or needsPostProcessing (step right before success)
        newResp = requests.get(newUrl, headers=headers)
        newResp = newResp.json()
        timerCounter += 1
        if timerCounter >= timerMax:
            print('\nServer took too long to backup:\n\t' + str(newResp))
            break
    
    # If the last status was success or needsPostProcessing, return true, else return false
    if str(newResp["status"]) == "successful" or str(newResp["status"]) == "needsPostProcessing":
        return 1
    else:
        return 0



########################### ISSUE LINODE SNAPSHOT ON LINODE ID AND IMMEDIATELY CALL check_snapshot() ###########################
def create_snapshot(id, bearerToken):
    url = "https://api.linode.com/v4/linode/instances/" + str(id) + "/backups"

    success = 0
    try:
        # This is in a try except in case the Bearer token was not passed
        bearer = "Bearer " + bearerToken
        headers = {"Authorization": bearer, "Content-Type": "application/json"}
        body = {"label":"AnsibleUpdaterSnapshot"}
        success = 1
    except:
        headers = ""

    # Guard statement. We cannot create a snapshot if we don't have the Bearer token
    if not success:
        print("Needs argument for Bearer token")
        quit()
    
    resp = requests.post(url, headers=headers, json=body)
    resp = resp.json()

    try:
        # If we handed the wrong information to Linode or there was an error for any reason the backup ID won't be accessible
        backupID = resp["id"]
    except:
        print('\nServer did not respond correctly:\n\t' + str(resp))
        quit()
    
    
    return check_snapshot(id, backupID)



########################### APT UPDATE AND APT UPGRADE ALL HOSTS ###########################
def run_updates():
    # Each of these with statements opens the files devhosts, devhostsdocker, prodhosts, and prodhostsdocker
    # and assigns them to their own variables, then splits each line at newline to create an array of hostnames
    print("Reading devhosts")
    devHosts = ""
    with open('devhosts', 'r') as file:
        devHosts = file.read()
    devHosts = devHosts.split('\n')
    
    print("Reading devhostsdocker")
    devHostsDocker = ""
    with open('devhostsdocker','r') as file:
        devHostsDocker = file.read()
    devHostsDocker = devHostsDocker.split('\n')

    print("Reading prodhosts")
    prodHosts = ""
    with open('prodhosts', 'r') as file:
        prodHosts = file.read()
    prodHosts = prodHosts.split('\n')

    print("Reading prodhostsdocker")
    prodHostsDocker = ""
    with open('prodhostsdocker', 'r') as file:
        prodHostsDocker = file.read()
    prodHostsDocker = prodHostsDocker.split('\n')

    

    # This loops over each devhost and runs apt update & apt upgrade
    for index in devHosts:
        if len(devHosts) > 1:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(index, username='root', key_filename='~/.ssh/remote_rsa.pub')

            stdin, stdout, stderr = client.exec_command('apt update && apt upgrade -y')

            for line in stdout:
                print(line.replace('\n',''))

            client.close()

    # This loops over each devhost with docker and runs apt update & apt upgrade and checks if we have a config error
    for index in devHostsDocker:
        if len(devHostsDocker) > 1 and index == "50.116.60.147":
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(index, username='root', key_filename='.ssh/remote_rsa.pub')

            stdin, stdout, stderr = client.exec_command('apt update && apt upgrade -y && apt autoremove -y')

            for line in stdout:
                print(line.replace('\n',''))
                # If there is a config error, hand over control to the user to make a selection
                if line.startsWith('*** CONFIGFILE (Y/I/N/O/D/Z) [default=N] ?'):
                    userInput = input()
                    userInput = userInput.upper()
                    if userInput == 'Y' or userInput == 'I' or userInput == 'N' or userInput == 'O' or userInput == 'D' or userInput == 'Z' or userInput == '':
                        stdin.channel.send(userInput)
                        stdin.channel.shutdown_write() 

            client.close()



    return



########################### CHECK THAT ALL DREAMHOST HOSTS RESPOND WITH 200 OK ###########################
def check_200_DH(apiKey):
    # The following two comments are notes for debugging purposes
    # regex = '(?<=2331620\t)(.+)(?=\t.+\tA\t.+\t\t.+)'
    # https://api.dreamhost.com/?key=&cmd=dns-list_records

    # Set up our URL and headers
    url = "https://api.dreamhost.com/?key="
    success = 0
    try:
        url += apiKey
        url += '&cmd=dns-list_records'
        success = 1
    except:
        url = "https://api.dreamhost.com/?key="

    if not success:
        print("Needs argument for API key")
        quit()

    resp = requests.get(url)

    # If DreamHost reponds with a 200, immediately grab the contents of the response
    if resp.status_code == 200:
        resp = resp.content
    else:
        print(resp.status_code + ' error. Quitting.')
        quit()
    
    # Decode the response. It gets passed back from DreamHost and ingested as bytes initially. This will decode it into utf-8 for string manipulation
    resp = resp.decode('utf-8')
    # We then split the response into each line of the response
    resp = resp.splitlines()
    # We use the CSV reader to work with the CSV from DreamHost
    output = []
    for row in csv.reader(resp, delimiter="\t"):
        # DreamHost is rude and puts success at the top of the response so we have to parse this out
        if row[0] != "success":
            try:
                # Ignore headers
                if row[1] != "zone":
                    output.append(row[1])
            except:
                pass

    # Get unique values
    output = list(dict.fromkeys(output))

    # We now will loop over each output, run a GET request and check if the response is a 200 or not
    for index in output:
        index = 'http://' + index
        # If the server doesn't respond or doesn't respond in time it throws an actual error so we must supress that and handle it appropriately
        try:
            request = requests.get(index, timeout = 10)
        except Exception as e:
            # Custom response code 601 for 'server not implemented'
            if 'No address associated with hostname' in str(e):
                if('-p' in sys.argv):
                    print(f"601|{index}")
                else:
                    print(f"{bcolors.FAIL}601|{index}{bcolors.ENDC}")
            else:
                # Custom response code 603 for 'server not available'
                if('-p' in sys.argv):
                    print(f"603|{index}")
                else:
                    print(f"{bcolors.FAIL}603|{index}{bcolors.ENDC}")
            continue

        if('-p' in sys.argv):
            print(f"{request.status_code}|{index}")
        else:
            if request.status_code == 200:
                print(f"{bcolors.OKGREEN}{request.status_code}|{index}{bcolors.ENDC}")
            else:
                print(f"{bcolors.WARNING}{request.status_code}|{index}{bcolors.ENDC}")

    

    return



########################### CHECK THAT ALL LINODES RESPOND WITH 200 OK ###########################
def check_200():
    # These open the command file, devhostsdocker, and prodhostsdocker files
    # It then combines devhostsdocker and prodhostsdocker into one array
    if('-v' in sys.argv):
        print("Reading command")
    command = ""
    with open('command', 'r') as file:
        command = file.read()

    hosts = ""

    if('-v' in sys.argv):
        print("Reading devhostsdocker")
    devHostsDocker = ""
    with open('devhostsdocker', 'r') as file:
        devHostsDocker = file.read()
    devHostsDocker = devHostsDocker.split('\n')

    if('-v' in sys.argv):
        print("Reading prodhostsdocker")
    prodHostsDocker = ""
    with open('prodhostsdocker', 'r') as file:
        prodHostsDocker = file.read()
    prodHostsDocker = prodHostsDocker.split('\n')

    devHostsDocker.extend(prodHostsDocker)
    hosts = devHostsDocker


    # Read the baremetal-apache-command and baremetal-nginx-command files
    if('-v' in sys.argv):
        print("Reading baremetal-apache-command")
    apacheCommand = ""
    with open('baremetal-apache-command', 'r') as file:
        apacheCommand = file.read()

    if('-v' in sys.argv):
        print("Reading baremetal-nginx-command")
    nginxCommand = ""
    with open('baremetal-nginx-command', 'r') as file:
        nginxCommand = file.read()



    # Do the same as we did with devhostsdocker and prodhostsdocker but with devhosts and prodhosts
    baremetalHosts = ""

    if('-v' in sys.argv):
        print("Reading devhosts")
    devHosts = ""
    with open('devhosts', 'r') as file:
        devHosts = file.read()
    devHosts = devHosts.split('\n')

    if('-v' in sys.argv):
        print("Reading prodhosts")
    prodHosts = ""
    with open('prodhosts', 'r') as file:
        prodHosts = file.read()
    prodHosts = prodHosts.split('\n')

    devHosts.extend(prodHosts)
    baremetalHosts = devHosts

    
    # We now loop over each host, remote in, and run the appropriate command.
    if('-v' in sys.argv):
        print("SSH and cURL")
    for index in hosts:
        if len(hosts) > 1 and index != '':
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(index, username='root', key_filename='.ssh/remote_rsa.pub', timeout=10)
            except:
                try:
                    client.connect(index, username='root', key_filename='.ssh/remote_rsa.pub', timeout=10, port=23)
                except:
                    if('-p' in sys.argv):
                        print(f"603|{index}")
                    else:
                        print(f'{bcolors.FAIL}603|{index}{bcolors.ENDC}')
                    continue
            
            stdin, stdout, stderr = client.exec_command('/bin/bash')
            stdin.channel.send(command)
            stdin.channel.shutdown_write() 

            for line in stdout:
                line = line.replace('\n','')
                if('-p' in sys.argv):
                    print(f"{line}")
                else:
                    if line.startswith('200'):
                        print(f"{bcolors.OKGREEN}{line}{bcolors.ENDC}")
                    else:
                        print(f"{bcolors.WARNING}{line}{bcolors.ENDC}")
                    

            client.close()

    # We now loop over each baremetal host, ssh in, and execute the apache and nginx commands
    # only if they are running
    if('-v' in sys.argv):
        print('SSH and cURL baremetal')
    for index in baremetalHosts:
        if len(baremetalHosts) > 1 and index != '':
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(index, username='root', key_filename='.ssh/remote_rsa.pub', timeout=10)
            except:
                if('-p' in sys.argv):
                    print(f"603|{index}")
                else:
                    print(f'{bcolors.FAIL}603|{index}{bcolors.ENDC}')
                continue
            
            stdin, stdout, stderr = client.exec_command('/bin/bash')
            # Check if apache2 is installed
            stdin.channel.send('which apache2 >/dev/null 2>&1; [[ $? = 0 ]] && echo \'true\' || echo \'false\'')
            stdin.channel.shutdown_write()

            for line1 in stdout:
                line1 = line1.replace('\n','')
                # If apache2 is installed we ssh in, find the apache2 hosts, and curl them
                if line1 == 'true':
                    client.connect(index, username='root', key_filename='.ssh/remote_rsa.pub')
                    stdin, stdout, stderr = client.exec_command(apacheCommand)
                    for newLine in stdout:
                        newLine = newLine.replace('\n','')
                        if('-p' in sys.argv):
                            print(f"{newLine}")
                        else:
                            if newLine.startswith('200'):
                                print(f"{bcolors.OKGREEN}{newLine}{bcolors.ENDC}")
                            else:
                                print(f"{bcolors.WARNING}{newLine}{bcolors.ENDC}")

            client.close()
            client.connect(index, username='root', key_filename='.ssh/remote_rsa.pub')
            # Check if nginx is installed
            stdin, stdout, stderr = client.exec_command('which nginx >/dev/null 2>&1; [[ $? = 0 ]] && echo \'true\' || echo \'false\'')

            for line2 in stdout:
                line2 = line2.replace('\n','')
                # If nginx is installed we ssh in, find the nginx hosts, and curl them
                if line2 == 'true':
                    client.connect(index, username='root', key_filename='.ssh/remote_rsa.pub')
                    stdin, stdout, stderr = client.exec_command(nginxCommand)
                    for newLine2 in stdout:
                        newLine2 = newLine2.replace('\n','')
                        if('-p' in sys.argv):
                            print(f"{newLine2}")
                        else:
                            if newLine2.startswith('200'):
                                print(f"{bcolors.OKGREEN}{newLine2}{bcolors.ENDC}")
                            else:
                                print(f"{bcolors.WARNING}{newLine2}{bcolors.ENDC}")

            client.close()

            

    return



########################### GENERATE HOST FILES FOR USE WITH OTHER FUNCTIONS ###########################
def generate_hosts(bearerToken):
    # Set up our URL and headers
    url = "https://api.linode.com/v4/linode/instances"

    success = 0
    try:
        bearer = "Bearer " + bearerToken
        headers = {"Authorization": bearer}
        success = 1
    except:
        headers = ""


    if not success:
        print("Needs argument for Bearer token")
        quit()

    resp = requests.get(url, headers=headers)

    if resp.status_code == 200:
        resp = resp.json()
    else:
        print(resp.status_code + ' error. Quitting.')
        quit()

    getJson = resp["data"]
    lengthOfData = len(getJson)

    

    devFile = open('devhosts', 'a')
    prodFile = open('prodhosts', 'a')
    devFileDocker = open('devhostsdocker', 'a')
    prodFileDocker = open('prodhostsdocker', 'a')

    prod = []
    dev = []
    prodWithDocker = []
    devWithDocker = []


    for index in range(lengthOfData):
        ip = getJson[index]["ipv4"][0]
        
        if str(getJson[index]["status"]) == "running":
            if "Production" in getJson[index]["tags"]:
                if "Docker" in getJson[index]["tags"] and "Baremetal" in getJson[index]["tags"]:
                    prodWithDocker.append(ip)
                    prod.append(ip)
                elif "Docker" in getJson[index]["tags"]:
                    prodWithDocker.append(ip)
                elif "Baremetal" in getJson[index]["tags"]:
                    prod.append(ip)
            elif "Development" in getJson[index]["tags"]:
                if "Docker" in getJson[index]["tags"] and "Baremetal" in getJson[index]["tags"]:
                    devWithDocker.append(ip)
                    dev.append(ip)
                elif "Docker" in getJson[index]["tags"]:
                    devWithDocker.append(ip)
                elif "Baremetal" in getJson[index]["tags"]:
                    dev.append(ip)

    for address in range(len(prod)):
        prodFile.write(prod[address] + "\n")
    for address in range(len(prodWithDocker)):
        prodFileDocker.write(prodWithDocker[address] + "\n")

    for address in range(len(dev)):
        devFile.write(dev[address] + "\n")
    for address in range(len(devWithDocker)):
        devFileDocker.write(devWithDocker[address] + "\n")

    devFile.close()
    prodFile.close()

    return



########################### RUN FUNCTION BASED ON NUMBER PASSED. DIFFERENT FUNCTIONALITY IF CALLED FROM CLI OR MENU ###########################
def select_option(selection, cli = 0):
    match selection:
        case '0':
            sys.exit(0)
        case '1':
            check_200()
        case '2':
            if cli:
                try:
                    bearer = sys.argv[2]
                except:
                    print("Needs argument for Bearer token")
                    sys.exit(0)
            else:
                print('Enter Bearer token:')
                bearer = input()
            generate_hosts(bearer)
        case '3':
            if cli:
                try:
                    apiKey = sys.argv[2]
                except:
                    print('Needs argument for API key')
                    sys.exit(0)
            else:
                print('Enter API key:')
                apiKey = input()
            check_200_DH(apiKey)
        case '13':
            if cli:
                try:
                    apiKey = sys.argv[2]
                except:
                    print('Needs argument for API key')
                    sys.exit(0)
            else:
                print('Enter API key:')
                apiKey = input()
            check_200()
            check_200_DH(apiKey)
        case _:
            print('Option not recognized.')
            main()



########################### ENTRY TO PROGRAM ###########################
def main():
    # Checks if the script was called with arguments. If it was, proceed to selecting the option passed
    if len(sys.argv) > 1:
        try:
            selection = sys.argv[1]
            select_option(selection, 1)
            sys.exit(0)
        except Exception as e:
            print(e)
            sys.exit(0)
    else:
        # If it was not passed with arguments print a little menu with options
        print("Please enter the number of the function you would like to run:")
        print("1: check200, cURL each host to see if the webserver responds with a 200")
        print("2: generateHosts, connect to the Linode API to generate hosts files")
        print('3: check200DH, checks DreamHost URLs for 200')
        print('13: 1 and 3, runs 1 and 3 concurrently')
        print("0: Exit script")
        selection = input()
        select_option(selection)

        main()



########################### Start Script ###########################
main()