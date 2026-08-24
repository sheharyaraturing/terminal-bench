#!/usr/bin/python3
################################################################################
#
# Copyright (c) 2024 Qumulo, Inc. All rights reserved.
#
# NOTICE: All information and intellectual property contained herein is the
# confidential property of Qumulo, Inc. Reproduction or dissemination of the
# information or intellectual property contained herein is strictly forbidden,
# unless separate prior written permission has been obtained from Qumulo, Inc.
#
# Name:     qfs_filelock.py
# Date:     2024-08-16
# Author:   kmac@qumulo.com
#
# Version:  20241126.1219
#
# Description:
# - This script monitors a specified directory or file on a Qumulo cluster for 
#   changes, such as file additions or ACL modifications, using the Qumulo API.
# - When a change is detected, the script attempts to apply a Write Once Read 
#   Many (WORM) lock to the affected file. This is achieved by setting a file 
#   lock with a specified retention period.
# - The script can operate in a recursive mode to monitor all subdirectories.
# - Debug mode is available for detailed logging, and the script supports 
#   configurable polling intervals.
# - Added support for specifying retention using days, date, or years.
# - Added interactive configuration file generation.
# - Added daemon mode functionality.
#
################################################################################

import argparse
import configparser
import daemon
import getpass
import inspect
import json
import logging
import os
import re
import requests
import signal
import sys
import time
import urllib3
import warnings
from datetime import datetime, timedelta
from urllib3.exceptions import InsecureRequestWarning
from contextlib import redirect_stdout

from qumulo.rest_client import RestClient
import qumulo.rest.fs as fs

warnings.simplefilter('ignore', InsecureRequestWarning)
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

interval = None

################################################################################
# function load_config - Load configuration from a file
################################################################################
def load_config(config_file_path):
    try:
        config = configparser.ConfigParser()
        config.read(config_file_path)
        if 'DEFAULT' not in config:
            raise ValueError(f"Configuration file {config_file_path} is missing the DEFAULT section.")
        return config
    except Exception as e:
        logging.error(f"Failed to load configuration file: {config_file_path}")
        logging.debug(f"Exception details: {e}")
        raise

################################################################################
# function setup_logging - Set up logging configuration with optional file output
################################################################################
def setup_logging(is_debug, log_file=None):  
    log_level = logging.DEBUG if is_debug else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file: 
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s', handlers=handlers)
    logging.debug("Logging setup complete. Logging is now active.")

################################################################################
# function parse_args - Parse command line arguments
################################################################################
def parse_args():
    try:
        parser = argparse.ArgumentParser(description='Process Qumulo notifications.')
        parser.add_argument('--file-num', type=str, help='The file number to monitor for changes')
        parser.add_argument('--directory-path', type=str, help='The directory path to monitor for changes')
        parser.add_argument('--debug', action='store_true', help='Enable debug mode')
        parser.add_argument('--config-file', type=str, default='qfs_filelock_config.ini', help='Path to the configuration file')
        parser.add_argument('--interval', type=int, default=15, help='Interval for polling notifications')
        parser.add_argument('--output', type=str, help='Output file to save notifications')
        parser.add_argument('--recursive', action='store_true', help='Monitor directories recursively')
        parser.add_argument('--retention', type=str, help='Retention period (e.g., 7d for days, 6m for months, 2y for years, 2023-12-31 for a specific date)')
        parser.add_argument('--legal-hold', action='store_true', help='Apply a legal hold')
        parser.add_argument('--configure', action='store_true', help='Prompt for configuration and create the config file')
        parser.add_argument('--run-as-daemon', action='store_true', help='Run the script as a daemon (not yet implemented)')

        args = parser.parse_args()

        if not args.file_num and not args.directory_path and not args.configure:
            parser.error('No action requested, add --file-num or --directory-path or use --configure to create a configuration file')

        if not args.configure and not args.legal_hold and not args.retention:
            logging.warning("Neither legal hold nor a valid retention period was set. The file lock will not be effective. Try again.")

        return args
    except Exception as e:
        logging.error("Error parsing arguments.")
        logging.debug(f"Exception details: {e}")
        sys.exit(1)

def display_header(args, config, file_number=None, file_path=None):
    try:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        width = 65
        border = '#'

        attributes = {
            "directory_path": "Directory:",
            "file_num": "File Number:",
            "interval": "Polling Interval:",
            "recursive": "Recursive:",
            "config_file": "Config File:",
            "output": "Output File:",
            "retention": "Retention Period:",
            "legal_hold": "Legal Hold:",
            "api_host": "API Host:",
            "api_port": "API Port:",
            "username": "Username:",
        }

        values = {
            "directory_path": file_path or getattr(args, 'directory_path', None),
            "file_num": file_number or getattr(args, 'file_num', None),
            "interval": f"{args.interval} secs" if args.interval is not None else None,
            "recursive": args.recursive,
            "config_file": args.config_file,
            "output": args.output,
            "retention": args.retention,
            "legal_hold": "True" if args.legal_hold else None,
            "api_host": config['DEFAULT']['API_HOST'],
            "api_port": config['DEFAULT']['API_PORT'],
            "username": config['DEFAULT']['USERNAME'],
        }

        max_label_length = max(len(label) for label in attributes.values())

        header = [
            f"{border * width}",
            f"{border}{'QFS File Lock Script'.center(width - 2)}{border}",
            f"{border}{current_time_str.center(width - 2)}{border}",
            f"{border * width}"
        ]

        for attr, label in attributes.items():
            value = values[attr]
            if value is not None:
                header.append(f'{border} {label}{" " * (max_label_length - len(label) + 1)}{str(value).ljust(width - max_label_length - 4)}{border}')

        header.append(f"{border * width}")

        for line in header:
            print(line, flush=True)
            if args.output:
                with open(args.output, 'a') as log_file:
                    log_file.write(line + '\n')
    except Exception as e:
        logging.error("Failed to display header.")
        logging.debug(f"Exception details: {e}")


################################################################################
# function parse_retention - Parse the retention period
################################################################################
def parse_retention(retention_period):
    logging.debug(f"{inspect.currentframe().f_code.co_name} Retention argument is: {retention_period}.")

    if retention_period is None:
        logging.error("Retention is set to None, no retention period will be set.")
        return None
    
    try:
        if retention_period.endswith('d'):
            days = int(retention_period[:-1])
            retention_date = datetime.utcnow() + timedelta(days=days)
        elif retention_period.endswith('m'):
            months = int(retention_period[:-1])
            retention_date = datetime.utcnow() + timedelta(days=months * 30)
        elif retention_period.endswith('y'):
            years = int(retention_period[:-1])
            retention_date = datetime.utcnow() + timedelta(days=years * 365)
        else:
            retention_date = datetime.strptime(retention_period, "%Y-%m-%d")
        return retention_date.replace(microsecond=0).isoformat() + 'Z'
    except Exception as e:
        logging.error("Failed to parse retention period.")
        logging.debug(f"Exception details: {e}")
        return None
################################################################################
# function lock_file - Lock a file using Qumulo API's modify_file_lock method
################################################################################

recent_locks = {}

def lock_file(rest_client, args, full_path, file_number, debug, cooldown=5):
    logging.debug(f"{inspect.currentframe().f_code.co_name}: Passed in: args is {args}, full_path is {full_path}, file_num is {file_number}")

    try:
        if not os.path.isabs(full_path):
            logging.error(f"Provided path is not absolute: {full_path}")
            return

        full_path = re.sub(r'/+', '/', full_path)

        current_time = time.time()
        if full_path in recent_locks and (current_time - recent_locks[full_path]) < cooldown:
            logging.debug(f"Skipping recently locked file: {full_path}")
            return

        try:
            logging.debug("Attempting to get file attributes...")
            file_attr = fs.get_file_attr(rest_client.conninfo, rest_client.credentials, path=full_path)
            logging.debug(f"File attributes: {file_attr}")

            if isinstance(file_attr, tuple):
                file_attr = file_attr[0]

            if not isinstance(file_attr, dict):
                logging.error("Unexpected format for file attributes. Skipping.")
                return

        except Exception as e:
            logging.debug("Failed to get file attributes. Reinitializing RestClient.")
            config = load_config(args.config_file)
            api_host = config['DEFAULT']['API_HOST']
            api_port = config['DEFAULT']['API_PORT']
            username = config['DEFAULT']['USERNAME']
            password = config['DEFAULT']['PASSWORD']

            rest_client = RestClient(api_host, api_port, timeout=120)
            rest_client.login(username, password)
            file_attr = fs.get_file_attr(rest_client.conninfo, rest_client.credentials, path=full_path)

            if isinstance(file_attr, tuple):
                file_attr = file_attr[0]
            if not isinstance(file_attr, dict):
                logging.error("Unexpected format for file attributes after reconnection. Skipping.")
                return

        if file_attr['type'] == 'FS_FILE_TYPE_DIRECTORY':
            logging.info(f"Skipping directory: {full_path}")
            return

        retention_period = None

        if hasattr(args, 'retention') and args.retention:
            retention_period = parse_retention(args.retention)
        else:
            logging.debug("Retention period not provided. No retention period will be set.")

        if not args.legal_hold and retention_period is None:
            logging.info("Neither legal hold nor a valid retention period was set. The lock will not be effective.")

        logging.debug(f"Attempting to lock the file: {full_path} with {'legal hold' if args.legal_hold else ''} {'and retention period' if retention_period else ''}")
        max_retries = 3
        attempt = 0

        while attempt < max_retries:
            try:
                response = fs.modify_file_lock(
                    conninfo=rest_client.conninfo,
                    _credentials=rest_client.credentials,
                    path=full_path,
                    retention_period=retention_period,
                    legal_hold=args.legal_hold
                )
                success_message = f"Successfully locked file: {full_path}"
                logging.info(success_message)
                if args.output:
                    with open(args.output, 'a') as log_file:
                        log_file.write(f"{datetime.now()} - INFO - {success_message}")
                logging.debug(f"Response: {response}")

                recent_locks[full_path] = current_time
                break

            except Exception as e:
                attempt += 1
                logging.error(f"Unexpected error when attempting to lock file: {full_path}. Error: {e}")
                time.sleep(2)

        if attempt == max_retries:
            logging.error(f"Max retries reached. Failed to lock file: {full_path}")

    except Exception as e:
        logging.error(f"Error in lock_file function: {e}.")
        logging.debug(f"Exception details: {e}")

    finally:
        logging.debug("RestClient connection management completed.")

################################################################################
# function configure_interactive - Interactive configuration file creation
################################################################################
def configure_interactive(config_file):
    try:
        config = configparser.ConfigParser()

        print("Configuring qfs_filelock_config.ini")
        config['DEFAULT'] = {
            'API_HOST': input('Enter API Host: '),
            'API_PORT': input('Enter API Port: '),
            'USERNAME': input('Enter Username: '),
            'PASSWORD': getpass.getpass('Enter Password: ')
        }

        with open(config_file, 'w') as configfile:
            config.write(configfile)

        print(f"Configuration saved to {config_file}")
    except Exception as e:
        logging.error("Failed to configure interactive settings.")
        logging.debug(f"Exception details: {e}")

################################################################################
# function get_fileinfo - Get file_num and fully qualified path
################################################################################
def get_fileinfo(rest_client, file_number=None, directory_path=None, debug=False):
    try:
        if file_number:
            response = fs.get_file_attr(rest_client.conninfo, rest_client.credentials, id_=file_number)
            if isinstance(response, tuple):
                response = response[0]
            absolute_path = response['path']
            logging.debug(f"file_num is {file_number} and absolute_path is {absolute_path}")

        elif directory_path:
            response = fs.get_file_attr(rest_client.conninfo, rest_client.credentials, path=directory_path)
            if isinstance(response, tuple):
                response = response[0]
            file_number = response['id']
            absolute_path = response['path']
            logging.debug(f"file_num is {file_number} and absolute_path is {absolute_path}")
        else:
            raise ValueError("Either file_num or directory_path must be provided")

        return file_number, absolute_path

    except ValueError as ve:
        logging.error("Invalid value provided for file Number or directory path.")
        logging.debug(f"ValueError details: {ve}")
        return "Error_ID", "Error_Path"

    except requests.exceptions.RequestException as re:
        logging.error("Request error occurred while retrieving file information.")
        logging.debug(f"RequestException details: {re}")
        return "Error_ID", "Error_Path"

    except Exception as e:
        logging.error("Unexpected error occurred while retrieving file information.")
        logging.debug(f"Exception details: {e}")
        return "Error_ID", "Error_Path"

################################################################################
# function stream_notifications - Stream notifications from Qumulo API
################################################################################
def stream_notifications(rest_client, args, debug=False, output_file=None):
    logging.debug(f"{inspect.currentframe().f_code.co_name}: Passed in: args is {args} and output_file is {output_file}")

    try:
        notification_types_to_handle = [
            "child_file_added"
        ]

        if args.file_num:
            file_number, file_path = get_fileinfo(rest_client, file_number=args.file_num, directory_path=args.directory_path, debug=debug)
            path = None
            id_ = file_number

        elif args.directory_path:
            file_number, file_path = get_fileinfo(rest_client, file_number=args.file_num, directory_path=args.directory_path, debug=debug)
            path = file_path
            id_ = None
        else:
            raise ValueError("Either file_num or directory_path must be provided")

        logging.debug(f"{inspect.currentframe().f_code.co_name}: file_num is {file_number} and full_path is {path}")

        changes_iterator = fs.get_change_notify_listener(
            conninfo=rest_client.conninfo,
            _credentials=rest_client.credentials,
            recursive=args.recursive,
            type_filter=notification_types_to_handle,
            path=path,
            id_=id_,
        ).data

        logging.info(f"Listening for change notifications on directory: {path} [file_num {file_number}] ")

        for change in changes_iterator:
            logging.debug(f"Received change object: {change}")

            if isinstance(change, list):
                for change_dict in change:
                    change_type = change_dict.get('type')
                    change_path = change_dict.get('path')

                    if change_type:
                        logging.debug(f"Detected change of type: {change_type} at path: {change_path}")

                    if change_type in notification_types_to_handle:
                        new_file_abs_path = (str(file_path) + '/' + str(change_path)).replace('//', '/')
                        notification_message = f"Received {change_type} notification for {new_file_abs_path} "
                        logging.debug(notification_message)
                        if args.output:
                            with open(args.output, 'a') as log_file:
                                log_file.write(f"{datetime.now()} - INFO - {notification_message}\n")
                        try:
                            if interval != 0:
                                print(f"Delay of {interval} seconds before locking the file...", end='', flush=True)

                        except BrokenPipeError:
                            logging.warning("BrokenPipeError: Output stream was closed unexpectedly: {BrokenPipeError}.")
                            break
                        for _ in range(interval):
                            time.sleep(1)
                            try:
                                print('.', end='', flush=True)
                            except BrokenPipeError:
                                logging.warning("BrokenPipeError: Output stream was closed unexpectedly: {BrokenPipeError}.")
                                break
                        try:
                            lock_file(rest_client, args, new_file_abs_path, file_number, debug)
                        except Exception as e:
                            print(f"lock_file: An error occurred in {inspect.currentframe().f_code.co_name}: {str(e)}")

                        message = f"Waiting for notifications..."

                        if args.output:
                            with open(args.output, 'a') as log_file:
                                log_file.write(f"{datetime.now()} - INFO - {message}\n")
                        else:
                            logging.debug(message)
                    else:
                        logging.debug(f"Ignored change of type: {change_type} at path: {change_path}")
            else:
                logging.warning(f"Unexpected change format: {change}")
    except Exception as e:
        logging.error(f"Error occurred while streaming notifications: {e}")
        if args.output:
            with open(args.output, 'a') as log_file:
                log_file.write(f"{datetime.now()} - ERROR - Error occurred while streaming notifications: {e}.\n")
        logging.debug(f"Exception details: {e}")

################################################################################
# function run_daemon - Function that runs as a daemon
################################################################################
def run_daemon(rest_client, args):
    try:
        logging.info("Daemon started, listening for changes...")
        while True:
            try:
                if args.file_num or args.directory_path:
                    file_number, full_path = get_fileinfo(rest_client, file_number=args.file_num, directory_path=args.directory_path, debug=args.debug)
                    display_header(args, file_number, full_path)
                    stream_notifications(rest_client, args, debug=args.debug, output_file=args.output)
                else:
                    logging.debug(f"{inspect.currentframe().f_code.co_name}: file_num is {file_number} and full_path is {full_path}")
                    raise ValueError("Either file_num or directory_path must be provided")
                time.sleep(args.interval)
            except Exception as e:
                logging.error("Daemon encountered an error.")
                logging.debug(f"Exception details: {e}")
                time.sleep(5)
    except Exception as e:
        logging.error("Error occurred in daemon process.")
        logging.debug(f"Exception details: {e}")

def main():
    try:
        args = parse_args()
        global interval
        setup_logging(args.debug, log_file=args.output)

        if args.configure:
            configure_interactive(args.config_file)
            return

        if not os.path.exists(args.config_file):
            logging.error(f"Configuration file {args.config_file} does not exist.")
            print(f"Error: Configuration file {args.config_file} not found.\n")
            sys.exit(1)

        try:
            config = load_config(args.config_file)
            api_host = config['DEFAULT']['API_HOST']
            api_port = config['DEFAULT']['API_PORT']
            username = config['DEFAULT']['USERNAME']
            password = config['DEFAULT']['PASSWORD']
            interval = args.interval if args.interval is not None else 15
            logging.debug(f"Configuration loaded. API Host: {api_host}, API Port: {api_port}")
        except ValueError as ve:
            logging.error("Error loading configuration file.", exc_info=True)
            return

        try:
            rc = RestClient(api_host, api_port)
            rc.login(username, password)
            logging.debug("Successfully logged in to Qumulo API")
        except Exception as e:
            logging.error("Failed to initialize RestClient or login.", exc_info=True)
            return

        if args.run_as_daemon:
            with daemon.DaemonContext(
                    stdout=open('/var/log/qfs_filelock_daemon.log', 'a+'),
                    stderr=open('/var/log/qfs_filelock_daemon_error.log', 'a+'),
                    working_directory='/',
                    umask=0o002,
                    pidfile=open('/var/run/qfs_filelock.pid', 'w+')):
                run_daemon(rc, args)
        else:
            if args.file_num or args.directory_path:
                file_number, full_path = get_fileinfo(rc, file_number=args.file_num, directory_path=args.directory_path, debug=args.debug)
                display_header(args, config, file_number, full_path)
                stream_notifications(rc, args, debug=args.debug, output_file=args.output)
            else:
                logging.debug(f"{inspect.currentframe().f_code.co_name}: file_num is {file_number} and full_path is {full_path}")
                raise ValueError("Either file_num or directory_path must be provided")
    except Exception as e:
        logging.error("An error occurred in the main function.", exc_info=True)
        logging.debug(f"Exception details: {e}")

if __name__ == '__main__':
    main()
